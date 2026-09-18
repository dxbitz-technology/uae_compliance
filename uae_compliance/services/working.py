"""Keeping one working record alongside each invoice.

Called from the invoice's own save, inside its transaction, so the record and
the invoice arrive together or not at all.

Three rules shape it. One record per invoice, ever. It is never created for a
company that is switched off, because an app nobody asked for should leave no
trace. And it never writes back to the invoice that is calling it, which
would put the save into a loop.
"""

from __future__ import annotations

import frappe

from uae_compliance.domain.scope import Mode, mode_of

WORKING_DOCTYPE = "UAE Peppol Invoice"
SELLER_COMPANY_DOCTYPE = "UAE Peppol Seller Company"
SELLER_DOCTYPE = "UAE Peppol Seller Profile"


def mode_for(company: str) -> Mode:
	"""What this company is switched to. Anything unbound reads as Off."""
	value = frappe.db.get_value(
		SELLER_COMPANY_DOCTYPE,
		{"company": company, "parenttype": SELLER_DOCTYPE},
		"mode",
	)
	return mode_of(value)


def upsert(invoice) -> str | None:
	"""Make sure this draft has its working record, and that it is current.

	Runs on every save of a draft, so it has to be safe to run again and
	cheap when nothing has changed. Returns the record name, or nothing when
	the company is switched off.
	"""
	if invoice.docstatus != 0:
		# Submission and cancellation have their own paths. This one is only
		# about drafts.
		return None

	mode = mode_for(invoice.company)
	existing = frappe.db.get_value(WORKING_DOCTYPE, {"sales_invoice": invoice.name}, "name")

	if mode is Mode.OFF:
		# A record that already exists is left alone. Switching a company off
		# stops new work; it does not erase what somebody already recorded.
		return existing

	if existing:
		_refresh(existing, invoice, mode)
		return existing
	return _create(invoice, mode)


def _create(invoice, mode: Mode) -> str:
	doc = frappe.new_doc(WORKING_DOCTYPE)
	doc.sales_invoice = invoice.name
	doc.company = invoice.company
	doc.flags.from_check = True
	doc.mode = mode.value
	doc.in_scope = 1
	doc.scope_reason = f"Company is in {mode.value}."
	doc.readiness = "Not checked"
	doc.insert(ignore_permissions=True)
	return doc.name


def _refresh(name: str, invoice, mode: Mode):
	"""Bring the record's scope up to date without touching what a person put in.

	A mode change or an edit to the invoice makes any earlier result stale.
	Saying so is the whole point of the record, so it is marked rather than
	rechecked here. Checking happens where somebody asked for it.
	"""
	current = frappe.db.get_value(
		WORKING_DOCTYPE, name, ["mode", "readiness", "source_fingerprint"], as_dict=True
	)
	if not current:
		return

	from uae_compliance.erpnext.fingerprint import source_fingerprint

	now = source_fingerprint(invoice)
	changed = {}
	if current.mode != mode.value:
		changed["mode"] = mode.value
		changed["scope_reason"] = f"Company is in {mode.value}."
	if current.source_fingerprint and current.source_fingerprint != now:
		changed["readiness"] = "Stale"
	if not changed:
		return
	frappe.db.set_value(WORKING_DOCTYPE, name, changed, update_modified=False)


def on_invoice_update(invoice, method=None):
	"""Hook. Runs on every save of a Sales Invoice.

	`on_update` also runs on insert and on submit, so the guard inside upsert
	is what keeps this to drafts. It must never throw: a compliance gap is
	not a reason an invoice cannot be saved.
	"""
	try:
		upsert(invoice)
	except Exception:
		frappe.log_error(
			title="UAE e-invoicing working record",
			reference_doctype="Sales Invoice",
			reference_name=invoice.name,
		)


def on_invoice_cancel(invoice, method=None):
	"""Hook. Keeps the record and marks it, rather than removing it.

	A cancelled invoice still has a history worth reading, and anything
	already sent keeps its own frozen copy regardless.
	"""
	name = frappe.db.get_value(WORKING_DOCTYPE, {"sales_invoice": invoice.name}, "name")
	if name:
		frappe.db.set_value(
			WORKING_DOCTYPE, name, {"readiness": "Out of scope", "scope_reason": "The invoice was cancelled."}
		)
