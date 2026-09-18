"""Reading a Sales Invoice into the canonical model.

This is the only place that turns an ERPNext document into the shape the
rest of the app speaks. It reads and never writes, and it never calls the
document's own validation, because that can save and can set off hooks that
have nothing to do with us.

What it does not do is decide anything about money. Every amount is the one
ERPNext posted. The money rules check the result afterwards and say where it
does not add up, which is deliberately a separate job from producing it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import frappe

from uae_compliance.domain import scope
from uae_compliance.domain.canonical import CANONICAL_VERSION, SCENARIO_FLAGS
from uae_compliance.domain.encoding import NOT_APPLICABLE
from uae_compliance.domain.findings import Finding, Severity, SourceRef, Stage
from uae_compliance.erpnext import lines as line_reader
from uae_compliance.erpnext import masters, payment, taxes
from uae_compliance.erpnext.fingerprint import master_fingerprint, source_fingerprint
from uae_compliance.erpnext.numbers import Scales, as_date, as_timestamp, dec, zero
from uae_compliance.validation.artifacts import CUSTOMIZATION_ID, PINT_VERSION, PROFILE_ID

EXTRACTION_VERSION = "1"
JURISDICTION = "AE"
LOCAL_CURRENCY = "AED"

CODE_NO_PERMITTED_TYPE = "SCOPE-0006"
CODE_NO_CREDIT_REASON = "MAP-0007"

# A fixed namespace, so the same invoice on the same site always produces the
# same document identifier. P05 freezes it on the submission. Until then it is
# derived rather than stored, which keeps a second extraction of an unchanged
# invoice byte for byte identical.
UUID_NAMESPACE = uuid.UUID("6f4d2a4e-9c1f-5d3b-8a72-1f0c6b5e4d21")


def extract(invoice, *, environment: str = "Simulation") -> tuple[dict | None, list[Finding]]:
	"""Read one Sales Invoice.

	Returns the canonical document and everything worth reporting about it.
	A company nobody switched on returns nothing at all, because the app has
	no business describing an invoice it was never asked about.
	"""
	resolution = masters.resolve(invoice)
	if resolution.mode is scope.Mode.OFF:
		return None, []

	source = SourceRef(doctype="Sales Invoice", name=invoice.name)
	scales = Scales.of(invoice)
	credit_note = bool(invoice.is_return)

	rows = line_reader.extract(invoice, resolution, credit_note)
	vat_rows, charge_rows = taxes.split_tax_rows(invoice, resolution, source)
	attribution = line_reader.tax_by_row(invoice)
	breakdown = taxes.breakdown(invoice, rows, vat_rows, attribution, scales, credit_note)
	charges = taxes.charge_rows(charge_rows, invoice, scales, credit_note)

	tax_total = sum((group["tax_amount"] for group in breakdown), zero(scales.amount))
	totals = taxes.totals(invoice, charges, tax_total, scales, credit_note)

	awkward = taxes.discount_check(invoice, source)
	if awkward:
		resolution.note(awkward)

	paid_by, unstated = payment.means(invoice, source, resolution)
	if unstated:
		resolution.note(unstated)

	if credit_note:
		resolution.note(
			Finding(
				code=CODE_NO_CREDIT_REASON,
				severity=Severity.ERROR,
				stage=Stage.MAPPING,
				message="A credit note has to say why it was issued.",
				path="references.credit_reason_code",
				source=source,
				repair="Add the reason on the invoice's e-invoicing details.",
			)
		)

	document = {
		"provenance": _provenance(invoice, resolution),
		"context": _context(invoice, resolution, environment),
		"document": _document(invoice, rows, resolution, credit_note, source),
		"parties": {"seller": resolution.seller, "buyer": resolution.buyer},
		"lines": rows,
		"tax_breakdown": breakdown,
		"allowances": [],
		"charges": charges,
		"totals": totals,
		"references": _references(invoice),
		"payment": paid_by,
		"delivery": resolution.delivery,
		"scenario": dict.fromkeys(SCENARIO_FLAGS, False),
		"exchange_rates": _rates(invoice, scales),
	}
	return document, resolution.findings


def _provenance(invoice, resolution) -> dict:
	return {
		"schema_version": str(CANONICAL_VERSION),
		"extraction_version": EXTRACTION_VERSION,
		"extracted_at": as_timestamp(datetime.now(UTC)),
		"source_doctype": "Sales Invoice",
		"source_name": invoice.name,
		"company": invoice.company,
		"source_fingerprint": source_fingerprint(invoice),
		"master_fingerprint": master_fingerprint(resolution.revisions),
	}


def _context(invoice, resolution, environment: str) -> dict:
	return {
		"jurisdiction": JURISDICTION,
		"policy_revision": f"{resolution.seller_profile}@{resolution.effective_from or 'unset'}",
		"in_scope": True,
		"scope_reason": f"Company is in {resolution.mode}.",
		"environment": environment,
		"standards_version": PINT_VERSION,
		"customization_id": CUSTOMIZATION_ID,
		"profile_id": PROFILE_ID,
	}


def _document(invoice, rows, resolution, credit_note: bool, source: SourceRef) -> dict:
	currency = invoice.currency
	return {
		"number": invoice.name,
		"uuid": str(uuid.uuid5(UUID_NAMESPACE, f"{frappe.local.site}:Sales Invoice:{invoice.name}")),
		"type_code": _type_code(rows, resolution, credit_note, source),
		"issue_date": as_date(invoice.posting_date),
		"due_date": as_date(invoice.due_date) or NOT_APPLICABLE,
		"tax_point_date": NOT_APPLICABLE,
		"currency": currency,
		# The rules want the tax repeated in dirhams only when the invoice is
		# not already in them.
		"tax_currency": NOT_APPLICABLE if currency == LOCAL_CURRENCY else LOCAL_CURRENCY,
		"buyer_reference": invoice.po_no or None,
	}


def _type_code(rows, resolution, credit_note: bool, source: SourceRef) -> str | None:
	"""Pick within what the rules leave open.

	The matrix constrains rather than decides, so more than one type can be
	permitted. A registered seller issues the tax document, which is why it
	is preferred. No permitted type at all means the facts contradict each
	other and a person has to settle it.
	"""
	registered = bool((resolution.seller or {}).get("tax_registration"))
	categories = {row["tax_category"] for row in rows if row.get("tax_category")}
	permitted = scope.permitted_types(
		is_credit_note=credit_note, categories=categories, seller_registered=registered
	)
	if not permitted:
		resolution.note(
			Finding(
				code=CODE_NO_PERMITTED_TYPE,
				severity=Severity.ERROR,
				stage=Stage.SCOPE,
				message="No document type fits this invoice.",
				path="document.type_code",
				source=source,
				repair="Check the seller's registration and the tax categories on the lines.",
			)
		)
		return None
	return permitted[0]


def _references(invoice) -> dict:
	out = {}
	if invoice.return_against:
		issued = frappe.db.get_value("Sales Invoice", invoice.return_against, "posting_date")
		out["preceding"] = [{"number": invoice.return_against, "issue_date": as_date(issued)}]
	if invoice.po_no:
		out["purchase_order"] = invoice.po_no
	return out


def _rates(invoice, scales: Scales) -> dict:
	"""The rate the invoice was posted at, frozen.

	A rate looked up later must never change an old invoice, so the one
	recorded here is the one on the document and its source says so.
	"""
	out = {}
	company_currency = frappe.get_cached_value("Company", invoice.company, "default_currency")
	if invoice.currency != company_currency:
		out["to_company"] = {
			"from_currency": invoice.currency,
			"to_currency": company_currency,
			"rate": dec(invoice.conversion_rate, scales.rate),
			"date": as_date(invoice.posting_date),
			"source": "Rate on the invoice",
		}
	if invoice.currency != LOCAL_CURRENCY and company_currency == LOCAL_CURRENCY:
		out["to_aed"] = {
			"from_currency": invoice.currency,
			"to_currency": LOCAL_CURRENCY,
			"rate": dec(invoice.conversion_rate, scales.rate),
			"date": as_date(invoice.posting_date),
			"source": "Rate on the invoice",
		}
	return out
