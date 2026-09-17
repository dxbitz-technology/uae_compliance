"""Turn a canonical document into the same bytes every time, and hash them.

Two documents that mean the same thing must produce the same bytes, on any
machine, in any Python run. A submission freezes these hashes, so a later
change to the rules below changes what a stored hash means. Raise
ENCODING_VERSION when that happens and treat it as a contract change.

The rules:

- Output is UTF-8 with no byte order mark. Non-ASCII characters are written
  as themselves, not as escapes, so the bytes stay readable.
- Object keys are sorted by their Unicode code points. The order a caller
  built the mapping in does not matter.
- Array order is kept as given. Order carries meaning in a canonical
  document, for example invoice lines, so this module never sorts an array.
- Numbers are Decimal, written as plain strings. Floats are refused.
- A key whose value is None is left out entirely. None means the value is
  absent.
- A value that is present but does not apply is the NOT_APPLICABLE marker,
  written as {"not_applicable":true}. It is its own thing: not a missing key,
  not a null, and not zero. A reader turns it back with read_not_applicable.
- Separators carry no spaces, so nothing depends on pretty printing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

ENCODING_VERSION = 1

# What a hash covers, so a stored hash can say which rule produced it.
BUSINESS_HASH_LABEL = f"business-v{ENCODING_VERSION}"
PAYLOAD_HASH_LABEL = f"payload-v{ENCODING_VERSION}"


class EncodingError(ValueError):
	"""The input cannot be encoded in a way that stays stable."""


class NotApplicable:
	"""A value that is present and deliberately does not apply here.

	It lives with the encoding rather than with the schema, because what
	matters about it is how it is written down and read back. A missing key
	means nobody knows. Zero is an amount. This is a considered statement that
	the field has no meaning for this document.
	"""

	_instance = None

	def __new__(cls):
		if cls._instance is None:
			cls._instance = super().__new__(cls)
		return cls._instance

	def __repr__(self):
		return "NOT_APPLICABLE"


NOT_APPLICABLE = NotApplicable()

# How the marker is written. A single reserved key, so it cannot be confused
# with an ordinary object and a reader can recognise it without guessing.
NOT_APPLICABLE_KEY = "not_applicable"
NOT_APPLICABLE_FORM = {NOT_APPLICABLE_KEY: True}


def read_not_applicable(value):
	"""Turn the written form back into the marker, leaving anything else alone."""
	if isinstance(value, Mapping) and dict(value) == NOT_APPLICABLE_FORM:
		return NOT_APPLICABLE
	return value


def canonical_decimal(value: Decimal) -> str:
	"""Write a Decimal as a plain string, with no exponent and no stray sign.

	The scale is kept as given, so 180 and 180.00 are different strings. The
	caller decides the scale and must apply it the same way every time.
	"""
	if not isinstance(value, Decimal):
		raise EncodingError(f"expected Decimal, got {type(value).__name__}")
	if not value.is_finite():
		raise EncodingError(f"{value} is not a finite number")
	text = format(value, "f")
	# Decimal keeps the sign on a negative zero. A signed zero would make two
	# equal amounts hash differently, so drop it.
	if text.startswith("-") and not any(ch in "123456789" for ch in text):
		text = text[1:]
	return text


def _encodable(value, path: str):
	"""Return the value in a form json.dumps can write, or explain the refusal."""
	if value is None or isinstance(value, (str, bool)):
		return value
	if isinstance(value, NotApplicable):
		return dict(NOT_APPLICABLE_FORM)
	if isinstance(value, Decimal):
		return canonical_decimal(value)
	if isinstance(value, float):
		raise EncodingError(f"{path or 'value'}: float is not allowed in a canonical document; use Decimal")
	if isinstance(value, int):
		# bool is an int, and it was handled above.
		return value
	if isinstance(value, Mapping):
		out = {}
		for key in value:
			if not isinstance(key, str):
				raise EncodingError(f"{path or 'document'}: keys must be strings, got {key!r}")
			item = value[key]
			if item is None:
				continue
			out[key] = _encodable(item, f"{path}.{key}" if path else key)
		return out
	if isinstance(value, (bytes, bytearray)):
		raise EncodingError(f"{path or 'value'}: raw bytes have no canonical form; use a string")
	if isinstance(value, Sequence):
		return [_encodable(item, f"{path}[{i}]") for i, item in enumerate(value)]
	if isinstance(value, (set, frozenset)):
		raise EncodingError(f"{path or 'value'}: a set has no stable order; use a list")
	raise EncodingError(f"{path or 'value'}: {type(value).__name__} has no canonical form")


def canonical_bytes(document: Mapping) -> bytes:
	"""Encode a canonical document to the bytes that get hashed and stored."""
	if not isinstance(document, Mapping):
		raise EncodingError(f"expected a mapping, got {type(document).__name__}")
	prepared = _encodable(document, "")
	text = json.dumps(
		prepared,
		ensure_ascii=False,
		sort_keys=True,
		separators=(",", ":"),
		allow_nan=False,
	)
	return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
	if not isinstance(data, (bytes, bytearray)):
		raise EncodingError(f"expected bytes, got {type(data).__name__}")
	return hashlib.sha256(data).hexdigest()


def without_paths(document: Mapping, paths: Iterable[str]) -> dict:
	"""Copy the document with the named paths removed.

	A path is dotted, for example "context.checked_at". A path that names
	nothing is an error, so a renamed field cannot quietly stop being
	excluded from the business hash.
	"""
	wanted = {p for p in paths}
	for path in wanted:
		if not path or path.startswith(".") or path.endswith(".") or ".." in path:
			raise EncodingError(f"{path!r} is not a usable path")
	matched: set[str] = set()
	result = _strip(document, wanted, matched, "")
	missed = wanted - matched
	if missed:
		raise EncodingError("these paths matched nothing: " + ", ".join(sorted(missed)))
	return result


def _strip(value, wanted: set[str], matched: set[str], prefix: str):
	if isinstance(value, Mapping):
		out = {}
		for key, item in value.items():
			here = f"{prefix}.{key}" if prefix else key
			if here in wanted:
				# Record the match and keep looking, because the same path
				# applies again in every later row of a list.
				matched.add(here)
				continue
			out[key] = _strip(item, wanted, matched, here)
		return out
	if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
		# One path applies to the same field in every row, so the index is not
		# part of it. Removing "lines.note" removes the note from every line.
		return [_strip(item, wanted, matched, prefix) for item in value]
	return value


def business_hash(document: Mapping, volatile_paths: Iterable[str] = ()) -> str:
	"""Hash what the document says, ignoring the parts that move on their own.

	The caller passes the volatile paths, because which fields are volatile
	belongs to the canonical model, not to the encoder.
	"""
	subject = without_paths(document, volatile_paths) if volatile_paths else document
	return sha256_hex(canonical_bytes(subject))


def payload_hash(raw: bytes) -> str:
	"""Hash the exact bytes that went to a provider, whatever is inside them."""
	return sha256_hex(raw)
