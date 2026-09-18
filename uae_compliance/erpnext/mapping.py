"""Turning what ERPNext holds into the codes the official rules ask for.

Three mappings live here: the unit a line is invoiced in, what the item is,
and which tax category a posted tax belongs to. All three follow the same
rule. If the answer is not recorded somewhere a person can see and correct,
the answer is a finding. None of them guesses, because a guess here changes
the tax on a legal document.
"""

from __future__ import annotations

import frappe

from uae_compliance.domain.findings import Finding, Severity, SourceRef, Stage

CODE_NO_UOM_CODE = "MAP-0001"
CODE_NO_TAX_MAPPING = "MAP-0002"
CODE_TWO_TAX_MAPPINGS = "MAP-0003"
CODE_NO_ITEM_TYPE = "MAP-0004"

TAX_CATEGORY_DOCTYPE = "UAE Peppol Tax Category"
ITEM_TYPE_FIELD = "uae_peppol_item_type"

# The scheme a classification is published under. Goods are classified by
# tariff heading, services by activity code. See decision D042.
HS_SCHEME = "HS"


def uom_code(uom: str | None, out, source: SourceRef, row_id: str | None) -> str | None:
	"""The UN/ECE code for the unit this line was invoiced in.

	The invoiced unit, not the stock unit. Selling a case of twelve and
	holding singles are different facts and the document carries the first.
	"""
	if not uom:
		return None
	code = frappe.db.get_value("UOM", uom, "common_code")
	out.seen("UOM", uom)
	if not code:
		out.note(
			Finding(
				code=CODE_NO_UOM_CODE,
				severity=Severity.ERROR,
				stage=Stage.MAPPING,
				message="This unit has no common code.",
				path="lines.uom_code",
				source=SourceRef(doctype=source.doctype, name=source.name, row_id=row_id),
				repair=f"Set the common code on unit {uom}.",
				params={"uom": uom},
			)
		)
		return None
	return code


def item_facts(item_code: str | None, item_group: str | None, out) -> dict:
	"""What the item is, and how it is classified.

	The type is never worked out from whether the item is stocked. A service
	can be stocked and a good can be non-stock, and reading one from the
	other has put the wrong category on invoices before.
	"""
	facts = {"item_type": None, "classifications": []}
	if not item_code:
		return facts

	values = frappe.db.get_value(
		"Item", item_code, ["customs_tariff_number", ITEM_TYPE_FIELD, "modified"], as_dict=True
	)
	if not values:
		return facts
	out.seen("Item", item_code, values.get("modified"))

	facts["item_type"] = values.get(ITEM_TYPE_FIELD) or _group_item_type(item_group, out)
	tariff = values.get("customs_tariff_number")
	if tariff:
		facts["classifications"].append({"scheme": HS_SCHEME, "value": tariff})
	return facts


def _group_item_type(item_group: str | None, out) -> str | None:
	"""The item group's suggestion, used only when the item is silent."""
	if not item_group:
		return None
	value = frappe.db.get_value("Item Group", item_group, ITEM_TYPE_FIELD)
	out.seen("Item Group", item_group)
	return value or None


def tax_category(
	company: str,
	account_head: str | None,
	item_tax_template: str | None,
	out,
	source: SourceRef,
	row_id: str | None = None,
) -> dict | None:
	"""Which official tax category a posted tax belongs to.

	The item's own tax template is the closer fact, so it is tried first. The
	tax account is the fallback. Two mappings that both match is refused
	rather than resolved, because picking the first would make the tax on an
	invoice depend on the order rows happen to sit in.
	"""
	where = SourceRef(doctype=source.doctype, name=source.name, row_id=row_id)

	for filters in _candidate_filters(company, account_head, item_tax_template):
		matches = frappe.get_all(
			TAX_CATEGORY_DOCTYPE,
			filters=filters,
			fields=["name", "category", "rate", "reason_code", "reason", "modified"],
		)
		if not matches:
			continue
		if len(matches) > 1:
			out.note(
				Finding(
					code=CODE_TWO_TAX_MAPPINGS,
					severity=Severity.ERROR,
					stage=Stage.MAPPING,
					message="More than one tax mapping matches this line.",
					path="lines.tax_category",
					source=where,
					repair="Remove one of the overlapping tax mappings.",
					params={"mappings": ", ".join(sorted(m["name"] for m in matches))},
				)
			)
			return None
		found = matches[0]
		out.seen(TAX_CATEGORY_DOCTYPE, found["name"], found.get("modified"))
		return {
			"category": found["category"],
			"rate": found["rate"],
			"reason_code": found.get("reason_code") or None,
			"reason": found.get("reason") or None,
		}

	out.note(
		Finding(
			code=CODE_NO_TAX_MAPPING,
			severity=Severity.ERROR,
			stage=Stage.MAPPING,
			message="No tax mapping covers this line.",
			path="lines.tax_category",
			source=where,
			repair="Add a tax mapping for this company and tax account.",
			params={"company": company, "account": account_head or ""},
		)
	)
	return None


def _candidate_filters(company: str, account_head: str | None, item_tax_template: str | None):
	"""The lookups to try, closest fact first.

	The template describes the item's own treatment. The account only says
	where the tax was posted, which several treatments can share, so it is
	the weaker of the two and is asked second.
	"""
	if item_tax_template:
		yield {"company": company, "item_tax_template": item_tax_template}
	if account_head:
		yield {"company": company, "account_head": account_head, "item_tax_template": ["in", ["", None]]}
