"""How a canonical field is described, and how a document is checked against it.

The canonical model is written as data rather than as classes. One place then
states each field's type, whether it is required, and how many decimal places
it may carry, and the same declaration gives the path used when something is
wrong. The field list itself lives in its own module; this is the machinery it
is written in.

Three states have to stay apart, because they mean different things on an
invoice:

- absent, the key is not there at all, so nothing is known
- zero, a real amount that happens to be nothing
- not applicable, a deliberate statement that the field does not apply here

A key left out is absent. Zero is an ordinary value. Not applicable is the
NOT_APPLICABLE marker below, allowed only where the schema says so. None is
never used, because it reads as any of the three.

A check reports everything it finds in one pass. Stopping at the first problem
would send someone round the loop once per missing field.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Decimal
from enum import StrEnum

from uae_compliance.domain.findings import Finding, Severity, Stage

SCHEMA_VERSION = 1


class SchemaError(ValueError):
	"""The schema itself is wrong. This is our bug, not the document's."""


class NotApplicable:
	"""A field that deliberately does not apply here.

	It is a distinct value, not a missing key and not an empty string, so a
	reader can tell a considered "does not apply" from "nobody filled this in".
	"""

	_instance = None

	def __new__(cls):
		if cls._instance is None:
			cls._instance = super().__new__(cls)
		return cls._instance

	def __repr__(self):
		return "NOT_APPLICABLE"


NOT_APPLICABLE = NotApplicable()


class Kind(StrEnum):
	TEXT = "text"
	CODE = "code"
	DECIMAL = "decimal"
	DATE = "date"
	CURRENCY = "currency"
	COUNTRY = "country"
	BOOLEAN = "boolean"
	IDENTIFIER = "identifier"
	OBJECT = "object"
	ARRAY = "array"


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")

# One code per problem, so the interface can group and translate them.
CODE_MISSING = "CANON-0001"
CODE_UNKNOWN = "CANON-0002"
CODE_TYPE = "CANON-0003"
CODE_SHAPE = "CANON-0004"
CODE_SCALE = "CANON-0005"
CODE_VALUE = "CANON-0006"
CODE_NOT_APPLICABLE = "CANON-0007"
CODE_EMPTY = "CANON-0008"


@dataclass(frozen=True)
class Field:
	"""One canonical field.

	`scale` is the number of decimal places a decimal may carry. It is the
	documented representation, so a value with more places is refused rather
	than quietly rounded here; rounding belongs to the money rules, where it
	is deliberate.
	"""

	kind: Kind
	required: bool = False
	scale: int | None = None
	allowed: tuple[str, ...] | None = None
	fields: Mapping[str, "Field"] | None = None
	of: "Field | None" = None
	may_be_not_applicable: bool = False
	signed: bool = True

	def __post_init__(self):
		if self.kind is Kind.OBJECT and not self.fields:
			raise SchemaError("an object field must list its fields")
		if self.kind is Kind.ARRAY and self.of is None:
			raise SchemaError("an array field must say what it holds")
		if self.kind is not Kind.DECIMAL and self.scale is not None:
			raise SchemaError("only a decimal field has a scale")
		if self.kind is Kind.DECIMAL and self.scale is None:
			raise SchemaError("a decimal field must state its scale")
		if self.kind is Kind.DECIMAL and self.scale < 0:
			raise SchemaError("a scale cannot be negative")
		if self.allowed is not None and self.kind is not Kind.CODE:
			raise SchemaError("only a code field lists allowed values")
		if self.kind is Kind.CODE and not self.allowed:
			raise SchemaError("a code field must list its allowed values")


@dataclass(frozen=True)
class Schema:
	name: str
	version: int
	fields: Mapping[str, Field]
	extensions: Mapping[str, Field] = dataclass_field(default_factory=dict)

	def __post_init__(self):
		if not self.fields:
			raise SchemaError(f"{self.name}: a schema needs at least one field")
		clash = set(self.fields) & set(self.extensions)
		if clash:
			raise SchemaError(f"{self.name}: extension reuses a core name: {sorted(clash)}")

	def known(self) -> dict[str, Field]:
		return {**self.fields, **self.extensions}


def _finding(code: str, path: str, message: str, repair: str, **params) -> Finding:
	return Finding(
		code=code,
		severity=Severity.ERROR,
		stage=Stage.CANONICAL,
		message=message,
		path=path or "document",
		repair=repair,
		params={k: str(v) for k, v in params.items()},
	)


def check(document: Mapping, schema: Schema) -> list[Finding]:
	"""Read a document against a schema and report everything that is wrong."""
	if not isinstance(document, Mapping):
		return [_finding(CODE_TYPE, "", "The document is not a set of fields.", "rebuild_document")]
	return _check_fields(document, schema.known(), "")


def _check_fields(value: Mapping, fields: Mapping[str, Field], path: str) -> list[Finding]:
	found: list[Finding] = []
	for name in sorted(set(value) - set(fields)):
		here = f"{path}.{name}" if path else name
		found.append(
			_finding(
				CODE_UNKNOWN,
				here,
				"This field is not part of the canonical model.",
				"remove_field",
				field=name,
			)
		)
	for name in sorted(fields):
		spec = fields[name]
		here = f"{path}.{name}" if path else name
		if name not in value:
			if spec.required:
				found.append(
					_finding(CODE_MISSING, here, "This value is required.", "supply_value", field=name)
				)
			continue
		found.extend(_check_one(value[name], spec, here))
	return found


def _check_one(value, spec: Field, path: str) -> list[Finding]:
	if value is None:
		return [
			_finding(
				CODE_EMPTY,
				path,
				"Leave the field out when nothing is known, rather than emptying it.",
				"remove_field",
			)
		]
	if isinstance(value, NotApplicable):
		if spec.may_be_not_applicable:
			return []
		return [
			_finding(
				CODE_NOT_APPLICABLE,
				path,
				"This field cannot be marked as not applicable.",
				"supply_value",
			)
		]
	checker = _CHECKERS[spec.kind]
	return checker(value, spec, path)


def _text(value, spec: Field, path: str) -> list[Finding]:
	if not isinstance(value, str):
		return [_wrong_type(path, "text", value)]
	if not value.strip():
		return [
			_finding(
				CODE_EMPTY,
				path,
				"Leave the field out when nothing is known, rather than emptying it.",
				"remove_field",
			)
		]
	return []


def _code(value, spec: Field, path: str) -> list[Finding]:
	if not isinstance(value, str):
		return [_wrong_type(path, "code", value)]
	if value not in (spec.allowed or ()):
		return [
			_finding(
				CODE_VALUE,
				path,
				"This value is not in the permitted list.",
				"choose_permitted_value",
				value=value,
			)
		]
	return []


def _decimal(value, spec: Field, path: str) -> list[Finding]:
	if isinstance(value, bool) or not isinstance(value, Decimal):
		return [_wrong_type(path, "decimal", value)]
	if not value.is_finite():
		return [_wrong_type(path, "decimal", value)]
	places = -value.as_tuple().exponent
	if places > (spec.scale or 0):
		return [
			_finding(
				CODE_SCALE,
				path,
				"This number carries more decimal places than the model allows.",
				"round_before_sending",
				places=places,
				allowed=spec.scale,
			)
		]
	if not spec.signed and value < 0:
		return [_finding(CODE_VALUE, path, "This value cannot be negative.", "correct_sign", value=value)]
	return []


def _pattern(pattern: re.Pattern, label: str, hint: str):
	def checker(value, spec: Field, path: str) -> list[Finding]:
		if not isinstance(value, str):
			return [_wrong_type(path, label, value)]
		if not pattern.match(value):
			return [_finding(CODE_SHAPE, path, hint, "correct_format", value=value)]
		return []

	return checker


def _boolean(value, spec: Field, path: str) -> list[Finding]:
	if not isinstance(value, bool):
		return [_wrong_type(path, "true or false", value)]
	return []


def _identifier(value, spec: Field, path: str) -> list[Finding]:
	if not isinstance(value, Mapping):
		return [_wrong_type(path, "identifier", value)]
	found = []
	for part in ("scheme", "value"):
		if part not in value or not isinstance(value[part], str) or not value[part].strip():
			found.append(
				_finding(
					CODE_MISSING,
					f"{path}.{part}",
					"An identifier needs both the scheme and the value.",
					"supply_value",
					field=part,
				)
			)
	for extra in sorted(set(value) - {"scheme", "value"}):
		found.append(
			_finding(
				CODE_UNKNOWN,
				f"{path}.{extra}",
				"This field is not part of the canonical model.",
				"remove_field",
				field=extra,
			)
		)
	return found


def _object(value, spec: Field, path: str) -> list[Finding]:
	if not isinstance(value, Mapping):
		return [_wrong_type(path, "a set of fields", value)]
	return _check_fields(value, spec.fields or {}, path)


def _array(value, spec: Field, path: str) -> list[Finding]:
	if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
		return [_wrong_type(path, "a list", value)]
	found = []
	for index, item in enumerate(value):
		found.extend(_check_one(item, spec.of, f"{path}[{index}]"))
	return found


def _wrong_type(path: str, expected: str, value) -> Finding:
	return _finding(
		CODE_TYPE,
		path,
		f"This value should be {expected}.",
		"correct_type",
		got=type(value).__name__,
	)


_CHECKERS = {
	Kind.TEXT: _text,
	Kind.CODE: _code,
	Kind.DECIMAL: _decimal,
	Kind.DATE: _pattern(DATE_PATTERN, "a date", "A date is written as four digits, month, day."),
	Kind.CURRENCY: _pattern(CURRENCY_PATTERN, "a currency", "A currency is three capital letters."),
	Kind.COUNTRY: _pattern(COUNTRY_PATTERN, "a country", "A country is two capital letters."),
	Kind.BOOLEAN: _boolean,
	Kind.IDENTIFIER: _identifier,
	Kind.OBJECT: _object,
	Kind.ARRAY: _array,
}
