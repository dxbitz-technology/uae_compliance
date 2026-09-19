"""Turning a supplier's invoice into something in the books.

Deliberately two steps. First say what would happen, so a person can look at
it. Then, if they are happy, make a draft. Never a submitted document,
because posting somebody else's claim without anybody reading it is the
thing this whole approach exists to avoid.

Nothing is invented on the way. A supplier that does not exist is not
created, an item that matches nothing is not made up, and a tax the mapping
does not cover is reported rather than guessed. Where something cannot be
matched, the answer is to say so and stop.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

INBOUND_DOCTYPE = "UAE Peppol Inbound"
BINDING_DOCTYPE = "UAE Peppol Seller Company"
SELLER_DOCTYPE = "UAE Peppol Seller Profile"
TAX_CATEGORY_DOCTYPE = "UAE Peppol Tax Category"


@frappe.whitelist()
def plan(inbound: str) -> dict:
	"""What entering this document would produce, and what stands in the way.

	Read only. Nothing is created and nothing is changed by asking.
	"""
	doc = frappe.get_doc(INBOUND_DOCTYPE, inbound)
	doc.check_permission("read")

	blocks = []
	if doc.purchase_invoice:
		blocks.append(_("This has already been entered as {0}.").format(doc.purchase_invoice))
	if not doc.supplier:
		blocks.append(_("No supplier matches the sender, so there is nobody to owe."))
	if not doc.company:
		blocks.append(_("It is not clear which company this was sent to."))
	if doc.environment and doc.environment != "Production":
		blocks.append(
			_("This arrived through a {0} connection and cannot become a real purchase.").format(
				doc.environment.lower()
			)
		)

	from uae_compliance.validation.safe_xml import UnsafeDocument

	try:
		rows = _lines_of(doc)
	except UnsafeDocument as error:
		# Reading it is where a document somebody else wrote gets to decide
		# how much work we do. Refusing is the answer, not trying harder.
		rows = []
		blocks.append(_("This document cannot be read: {0}").format(error))

	order, order_note = _order_for(doc)
	if order and _fully_billed(order):
		blocks.append(_("It names order {0}, which is already fully billed.").format(order))

	if order:
		# The draft comes from the order itself, so the document's own lines
		# are not matched against our items. A person compares the two.
		matched, unmatched, taxes, missing_tax = [], [], [], []
	else:
		fallback = _fallback(doc.company) if doc.company else {}
		matched, unmatched = _match_lines(rows, doc.supplier, fallback)
		taxes, missing_tax = _match_taxes(rows, doc.company)

		if unmatched:
			blocks.append(
				_("{0} lines match nothing of ours and no fallback item is set.").format(len(unmatched))
			)
		for category, rate in missing_tax:
			blocks.append(_("No tax mapping covers category {0} at {1} percent.").format(category, rate))

	return {
		"inbound": doc.name,
		"supplier": doc.supplier,
		"company": doc.company,
		"their_number": doc.document_number,
		"currency": doc.currency,
		"payable": doc.payable,
		"order": order,
		"order_note": order_note,
		"open_orders": [] if order else _open_orders(doc),
		"lines": matched,
		"unmatched": unmatched,
		"taxes": taxes,
		"blocks": blocks,
		"can_enter": not blocks,
	}


@frappe.whitelist()
def create_draft(inbound: str) -> str:
	"""Make the draft purchase invoice. A person submits it, not this.

	Everything is checked again here rather than trusting what the plan said,
	because the plan was a moment ago and this is now.
	"""
	doc = frappe.get_doc(INBOUND_DOCTYPE, inbound)
	doc.check_permission("write")

	# Being allowed to handle arrived documents is not being allowed to put
	# something in the books. This used to insert past permissions, which
	# let anybody who could open an inbound document create a purchase
	# invoice in a company they had no access to.
	if not frappe.has_permission("Purchase Invoice", "create"):
		raise frappe.PermissionError(_("You are not allowed to create a purchase invoice."))

	found = plan(inbound)
	if not found["can_enter"]:
		frappe.throw("<br>".join(found["blocks"]), title=_("Cannot enter this yet"))

	invoice = _order_draft(doc, found["order"]) if found["order"] else _standalone_draft(doc, found)
	frappe.db.set_value(
		INBOUND_DOCTYPE,
		doc.name,
		{"purchase_invoice": invoice.name, "state": "Accepted"},
		update_modified=False,
	)
	return invoice.name


def _order_draft(doc, order: str):
	"""The draft from the order itself, through the framework's own mapping.

	That path carries each row's link back to the order line, so the order's
	billed quantities move and a second billing of the same order shows up as
	over billing rather than as a fresh claim. Building the rows by hand from
	the document skipped all of that, which is how a supplier could have been
	paid twice: once against the arrived invoice and once against the order.
	"""
	from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice

	invoice = make_purchase_invoice(order)
	# Their number and their date, kept as theirs. The rest is the order's.
	invoice.bill_no = doc.document_number
	invoice.bill_date = doc.issue_date
	# Inserted as the person, so the company on the document is checked
	# against what they are allowed to see as well.
	invoice.insert()
	return invoice


def _standalone_draft(doc, found: dict):
	"""The draft built from the document alone, when it names no order of ours."""
	invoice = frappe.new_doc("Purchase Invoice")
	invoice.company = doc.company
	invoice.supplier = doc.supplier
	invoice.currency = doc.currency
	# Their number and their date, kept as theirs. ERPNext gives these their
	# own fields precisely so the supplier's document stays identifiable.
	invoice.bill_no = doc.document_number
	invoice.bill_date = doc.issue_date
	invoice.posting_date = frappe.utils.nowdate()
	invoice.set_posting_time = 0

	cost_center = frappe.db.get_value("Cost Center", {"company": doc.company, "is_group": 0}, "name")
	for row in found["lines"]:
		invoice.append(
			"items",
			{
				"item_code": row["item_code"],
				"item_name": row["name"][:140] if row["name"] else None,
				"description": row["description"] or row["name"],
				"qty": flt(row["quantity"]),
				"uom": _our_uom(row.get("uom_code"), row["item_code"]),
				"rate": flt(row["net_price"]),
				"expense_account": row["expense_account"],
				"cost_center": cost_center,
			},
		)

	for tax in found["taxes"]:
		invoice.append(
			"taxes",
			{
				"charge_type": "On Net Total",
				"account_head": tax["account_head"],
				"description": tax["description"],
				"rate": flt(tax["rate"]),
				"category": "Total",
			},
		)

	# Inserted as the person, so the company on the document is checked
	# against what they are allowed to see as well.
	invoice.insert()
	return invoice


def _order_for(doc) -> tuple[str | None, str | None]:
	"""The purchase order the document names, when it is really ours.

	Matched only on our own order number, for this supplier and this company.
	A reference that matches nothing does not block the document forever: the
	sender may be quoting their own numbering, so it is said plainly and the
	document is entered on its own, in front of a person either way.
	"""
	reference = (doc.order_reference or "").strip()
	if not reference or not doc.supplier or not doc.company:
		return None, None
	name = frappe.db.get_value(
		"Purchase Order",
		{"name": reference, "supplier": doc.supplier, "company": doc.company, "docstatus": 1},
		"name",
	)
	if not name:
		return None, _(
			"It names order {0}, which matches none of ours for this supplier. It will be entered on its own."
		).format(reference)
	return name, None


def _fully_billed(order: str) -> bool:
	return flt(frappe.db.get_value("Purchase Order", order, "per_billed")) >= 100


def _open_orders(doc) -> list[dict]:
	"""The orders this document could be answering, for the person to look at.

	Through get_list, so a caller sees only orders they may see anyway.
	"""
	if not doc.supplier or not doc.company:
		return []
	return frappe.get_list(
		"Purchase Order",
		filters={
			"supplier": doc.supplier,
			"company": doc.company,
			"docstatus": 1,
			"per_billed": ["<", 100],
		},
		fields=["name", "transaction_date", "grand_total", "per_billed"],
		order_by="transaction_date desc",
		limit=5,
	)


def _our_uom(code: str | None, item_code: str) -> str | None:
	"""Their unit code, turned back into one of ours.

	The same native field the selling side reads, used the other way. Where
	no unit carries that code, the item's own stock unit answers, because
	refusing a whole invoice over a unit nobody has mapped helps nobody.
	"""
	if code:
		found = frappe.db.get_value("UOM", {"common_code": code}, "name")
		if found:
			return found
	return frappe.db.get_value("Item", item_code, "stock_uom")


def _lines_of(doc) -> list[dict]:
	"""Read the lines back out of the document we kept."""
	from uae_compliance.validation.reader import lines

	if not doc.payload_file:
		return []
	content = frappe.get_doc("File", doc.payload_file).get_content()
	if isinstance(content, str):
		content = content.encode("utf-8")
	return lines(content)


def _fallback(company: str) -> dict:
	row = frappe.db.get_value(
		BINDING_DOCTYPE,
		{"company": company, "parenttype": SELLER_DOCTYPE},
		["inbound_item", "inbound_expense_account"],
		as_dict=True,
	)
	return dict(row or {})


def _match_lines(rows: list[dict], supplier: str | None, fallback: dict):
	"""Line by line, ours or nothing.

	A supplier's part number is the strongest signal, because somebody has
	already said it means this item. An exact item code is the next best. A
	name is never a match: two things called Bracket are not the same thing.
	"""
	matched, unmatched = [], []
	for row in rows:
		item = _find_item(row["their_code"], supplier)
		if item:
			matched.append({**row, "item_code": item, "expense_account": None, "matched_on": "our records"})
			continue
		if fallback.get("inbound_item"):
			matched.append(
				{
					**row,
					"item_code": fallback["inbound_item"],
					"expense_account": fallback.get("inbound_expense_account"),
					"matched_on": "the fallback item",
				}
			)
			continue
		unmatched.append(row)
	return matched, unmatched


def _find_item(their_code: str | None, supplier: str | None) -> str | None:
	if not their_code:
		return None
	if supplier:
		found = frappe.db.get_value(
			"Item Supplier",
			{"supplier": supplier, "supplier_part_no": their_code, "parenttype": "Item"},
			"parent",
		)
		if found:
			return found
	return frappe.db.get_value("Item", {"item_code": their_code}, "name")


def _match_taxes(rows: list[dict], company: str | None):
	"""Which of our accounts each tax on their document belongs to.

	The same mapping the selling side uses, read the other way. A category
	and rate we have never mapped is reported rather than posted to
	something plausible.
	"""
	if not company:
		return [], []

	wanted = {}
	for row in rows:
		category = row.get("tax_category")
		rate = row.get("tax_rate")
		if category and rate is not None:
			wanted[(category, str(rate))] = flt(rate)

	taxes, missing = [], []
	for (category, rate_text), rate in wanted.items():
		account = frappe.db.get_value(
			TAX_CATEGORY_DOCTYPE, {"company": company, "category": category, "rate": rate}, "account_head"
		)
		if not account:
			missing.append((category, rate_text))
			continue
		taxes.append(
			{
				"account_head": account,
				"rate": rate,
				"description": _("{0} at {1} percent").format(category, rate_text),
			}
		)
	return taxes, missing
