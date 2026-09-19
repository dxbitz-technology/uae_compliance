"""What the browser is allowed to ask for.

Three rules hold across every method here. The company, the mode and any
status are worked out on the server from the document, never taken from the
caller. Every call checks the permission on the source invoice, because a
person who cannot read an invoice cannot read its findings either. And
anything that changes something says which revision it expected, so two
people editing at once find out rather than overwrite each other.

Nothing here reaches the network.
"""

from __future__ import annotations

import frappe
from frappe import _

from uae_compliance.domain.findings import Level
from uae_compliance.services import validation
from uae_compliance.services.working import WORKING_DOCTYPE

# A form sends one invoice. A list sends a screenful. Both are bounded so a
# crafted call cannot ask for the whole table.
MAX_BATCH = 100


@frappe.whitelist()
def preview_invoice(source_name: str, level: str = "Fast", inputs: str | None = None) -> dict:
	"""Check an invoice and return what was found. Nothing is written.

	Takes the invoice as it is saved. Details a person has typed but not yet
	saved come in through `inputs` and are used for this check only.
	"""
	invoice = _readable(source_name)
	wanted = Level.FULL if level == "Full" else Level.FAST
	result = validation.check(invoice, wanted, overrides=_allowed_inputs(inputs) if inputs else None)
	return _as_reply(result)


@frappe.whitelist()
def check_and_record(source_name: str, level: str = "Full") -> dict:
	"""Check an invoice and keep the result on its working record."""
	invoice = _readable(source_name, write=True)
	wanted = Level.FULL if level == "Full" else Level.FAST
	result = validation.check(invoice, wanted)
	validation.record_result(invoice.name, result)
	return _as_reply(result)


@frappe.whitelist()
def save_invoice_inputs(source_name: str, expected_revision: int, inputs: str) -> dict:
	"""Save the details a person supplies about an invoice.

	Only on a draft, and only when the revision is still the one they had in
	front of them.
	"""
	invoice = _readable(source_name, write=True)
	if invoice.docstatus != 0:
		frappe.throw(_("This invoice is no longer a draft."))

	name = frappe.db.get_value(WORKING_DOCTYPE, {"sales_invoice": invoice.name}, "name")
	if not name:
		frappe.throw(_("This invoice has no e-invoicing record yet. Save the invoice first."))

	doc = frappe.get_doc(WORKING_DOCTYPE, name)
	doc.check_permission("write")
	if int(expected_revision) != (doc.input_revision or 0):
		frappe.throw(
			_("Somebody else changed these details. Reload and try again."),
			title=_("Changed elsewhere"),
		)

	for field, value in _allowed_inputs(inputs).items():
		doc.set(field, value)
	doc.save()
	return {"input_revision": doc.input_revision}


@frappe.whitelist()
def get_readiness_batch(source_names: str) -> dict:
	"""Readiness for a screenful of invoices, filtered by what the caller may read."""
	names = frappe.parse_json(source_names)
	if not isinstance(names, list):
		frappe.throw(_("Expected a list of invoices."))
	# Names, not whatever the caller felt like nesting. A list with a dict
	# in it reaches the query builder as something other than a name.
	names = [name for name in names if isinstance(name, str)][:MAX_BATCH]
	if not names:
		return {}

	# A filter, not a gate. Somebody who may read none of these gets none
	# of them back rather than an error, because this answers a list
	# screen and a screen showing nothing is the right answer.
	if not frappe.has_permission("Sales Invoice", "read"):
		return {}

	allowed = [
		row.name for row in frappe.get_list("Sales Invoice", filters={"name": ["in", names]}, fields=["name"])
	]
	rows = frappe.get_list(
		WORKING_DOCTYPE,
		filters={"sales_invoice": ["in", allowed]},
		fields=["sales_invoice", "readiness", "errors", "warnings", "mode", "input_revision"],
	)
	return {row.sales_invoice: row for row in rows}


def _readable(source_name: str, write: bool = False):
	invoice = frappe.get_doc("Sales Invoice", source_name)
	invoice.check_permission("write" if write else "read")
	return invoice


def _allowed_inputs(inputs: str) -> dict:
	"""Only the fields a person is allowed to set, and nothing else.

	Taking the whole payload would let a caller write the readiness or the
	fingerprints through this door.
	"""
	from uae_compliance.uae_e_invoicing.doctype.uae_peppol_invoice.uae_peppol_invoice import (
		INPUT_FIELDS,
	)

	supplied = frappe.parse_json(inputs) or {}
	return {field: supplied[field] for field in INPUT_FIELDS if field in supplied}


def _as_reply(result) -> dict:
	return {
		"readiness": result.readiness.value,
		"level": result.level.value,
		"checked_at": result.checked_at,
		"in_scope": result.in_scope,
		"stages": [
			{"stage": s.stage.value, "state": s.state.value, "reason": s.reason} for s in result.stages
		],
		"findings": [validation.plain_finding(f) for f in result.actionable()],
	}
