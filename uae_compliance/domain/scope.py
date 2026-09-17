"""What a company mode allows, and which document type the rules permit.

Two decisions that both have to be made before an invoice goes anywhere, and
neither of which is obvious enough to leave scattered around the app.

The document type is the interesting one. It is tempting to say a credit note
is a credit note and be done, but the published rules tie the four codes to
the tax categories on the lines and to whether the seller is registered. A
seller with no registration cannot issue a tax invoice at all. So the rules
here constrain the choice rather than making it, and they say plainly when a
document contradicts itself.

Every rule below cites the published rule it comes from, so a reader can go
and check rather than trusting this file.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from uae_compliance.domain.findings import Finding, Severity, Stage

CODE_COMMERCIAL_CATEGORY = "SCOPE-0001"
CODE_TAX_CATEGORY = "SCOPE-0002"
CODE_SELLER_NOT_REGISTERED = "SCOPE-0003"
CODE_COMMERCIAL_FLAG = "SCOPE-0004"
CODE_TYPE_DIRECTION = "SCOPE-0005"

TAX_INVOICE = "380"
COMMERCIAL_INVOICE = "480"
TAX_CREDIT_NOTE = "381"
COMMERCIAL_CREDIT_NOTE = "81"

INVOICE_TYPES = (TAX_INVOICE, COMMERCIAL_INVOICE)
CREDIT_NOTE_TYPES = (TAX_CREDIT_NOTE, COMMERCIAL_CREDIT_NOTE)
TAX_TYPES = (TAX_INVOICE, TAX_CREDIT_NOTE)
COMMERCIAL_TYPES = (COMMERCIAL_INVOICE, COMMERCIAL_CREDIT_NOTE)

# ibr-122-ae: with a commercial document every category must be one of these.
CATEGORIES_ALLOWED_ON_COMMERCIAL = frozenset({"E", "O", "Z"})
# ibr-151-ae: a tax document may not be made up only of these.
CATEGORIES_INSUFFICIENT_FOR_TAX = frozenset({"E", "O"})
# ibr-157-ae: a commercial document cannot carry these scenarios.
FLAGS_BARRED_FROM_COMMERCIAL = ("deemed_supply", "margin_scheme", "summary")


class Mode(StrEnum):
	"""How much this company has switched on. Missing configuration is Off."""

	OFF = "Off"
	PREPARATION = "Preparation"
	LIVE = "Live"


class Enforcement(StrEnum):
	NONE = "None"
	ADVISORY = "Advisory"
	BLOCKING = "Blocking"


def mode_of(value) -> Mode:
	"""Read a stored mode. Anything unset or unrecognised means Off.

	A company that was never configured must behave exactly as it did before
	the app was installed, so an unknown value is never treated as switched on.
	"""
	try:
		return Mode(value)
	except ValueError:
		return Mode.OFF


def enforcement_for(mode: Mode) -> Enforcement:
	if mode is Mode.LIVE:
		return Enforcement.BLOCKING
	if mode is Mode.PREPARATION:
		return Enforcement.ADVISORY
	return Enforcement.NONE


def may_create_intent(mode: Mode) -> bool:
	"""Whether saving an invoice may create work that could be transmitted."""
	return mode is Mode.LIVE


def blocks_submission(
	mode: Mode,
	*,
	in_scope: bool,
	has_errors: bool,
	validation_unavailable: bool,
) -> bool:
	"""Whether this invoice may not be submitted in ERPNext.

	Only a live company blocks, and only for an invoice in scope. Validation
	that could not run blocks just as a failure does: not knowing is not the
	same as being fine.
	"""
	if mode is not Mode.LIVE or not in_scope:
		return False
	return has_errors or validation_unavailable


def _finding(code: str, path: str, message: str, repair: str, rule: str, **params) -> Finding:
	return Finding(
		code=code,
		severity=Severity.ERROR,
		stage=Stage.SCOPE,
		message=message,
		path=path,
		repair=repair,
		rule_id=rule,
		params={k: str(v) for k, v in params.items()},
	)


def categories_on(document: Mapping) -> set[str]:
	"""Every tax category the document uses, lines and adjustments alike."""
	found = set()
	for line in document.get("lines") or []:
		category = line.get("tax_category")
		if isinstance(category, str):
			found.add(category)
	for group in ("allowances", "charges"):
		for row in document.get(group) or []:
			category = row.get("tax_category")
			if isinstance(category, str):
				found.add(category)
	return found


def permitted_types(
	*, is_credit_note: bool, categories: set[str], seller_registered: bool
) -> tuple[str, ...]:
	"""Which document types the rules leave open for these facts.

	More than one may be permitted. Extraction chooses within this, and an
	empty result means the facts contradict each other.
	"""
	candidates = CREDIT_NOTE_TYPES if is_credit_note else INVOICE_TYPES
	allowed = []
	for code in candidates:
		if code in COMMERCIAL_TYPES:
			if categories and not categories <= CATEGORIES_ALLOWED_ON_COMMERCIAL:
				continue
		else:
			if not seller_registered:
				continue
			if categories and categories <= CATEGORIES_INSUFFICIENT_FOR_TAX:
				continue
		allowed.append(code)
	return tuple(allowed)


def check_document_type(document: Mapping, *, seller_registered: bool) -> list[Finding]:
	"""Say where the stated document type contradicts the rest of the document."""
	stated = (document.get("document") or {}).get("type_code")
	if stated not in (*INVOICE_TYPES, *CREDIT_NOTE_TYPES):
		return []
	found: list[Finding] = []
	categories = categories_on(document)
	path = "document.type_code"

	if stated in COMMERCIAL_TYPES:
		wrong = sorted(categories - CATEGORIES_ALLOWED_ON_COMMERCIAL)
		if wrong:
			found.append(
				_finding(
					CODE_COMMERCIAL_CATEGORY,
					path,
					"A commercial document cannot carry this tax category.",
					"change_document_type_or_category",
					"ibr-122-ae",
					type_code=stated,
					categories=", ".join(wrong),
				)
			)
		scenario = document.get("scenario") or {}
		set_flags = [name for name in FLAGS_BARRED_FROM_COMMERCIAL if scenario.get(name)]
		if set_flags:
			found.append(
				_finding(
					CODE_COMMERCIAL_FLAG,
					"scenario",
					"A commercial document cannot carry this scenario.",
					"change_document_type_or_scenario",
					"ibr-157-ae",
					type_code=stated,
					flags=", ".join(set_flags),
				)
			)
	else:
		if not seller_registered:
			found.append(
				_finding(
					CODE_SELLER_NOT_REGISTERED,
					path,
					"A seller with no tax registration cannot issue a tax document.",
					"open_seller_profile",
					"ibr-134-ae",
					type_code=stated,
				)
			)
		if categories and categories <= CATEGORIES_INSUFFICIENT_FOR_TAX:
			found.append(
				_finding(
					CODE_TAX_CATEGORY,
					path,
					"A tax document cannot be made up only of exempt and out of scope lines.",
					"change_document_type_or_category",
					"ibr-151-ae",
					type_code=stated,
					categories=", ".join(sorted(categories)),
				)
			)
	return found


def check_direction(document: Mapping, *, is_credit_note: bool) -> list[Finding]:
	"""The document type has to agree about whether this is a credit note."""
	stated = (document.get("document") or {}).get("type_code")
	if stated not in (*INVOICE_TYPES, *CREDIT_NOTE_TYPES):
		return []
	if is_credit_note and stated not in CREDIT_NOTE_TYPES:
		return [
			_finding(
				CODE_TYPE_DIRECTION,
				"document.type_code",
				"This is a credit note but carries an invoice type.",
				"correct_document_type",
				"ibr-cl-01",
				type_code=stated,
			)
		]
	if not is_credit_note and stated not in INVOICE_TYPES:
		return [
			_finding(
				CODE_TYPE_DIRECTION,
				"document.type_code",
				"This is an invoice but carries a credit note type.",
				"correct_document_type",
				"ibr-cl-01",
				type_code=stated,
			)
		]
	return []


def check(document: Mapping, *, seller_registered: bool, is_credit_note: bool) -> list[Finding]:
	return [
		*check_direction(document, is_credit_note=is_credit_note),
		*check_document_type(document, seller_registered=seller_registered),
	]
