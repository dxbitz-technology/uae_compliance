"""Invoice rows, turned into canonical lines.

The tax on a line comes from the per row table ERPNext v16 keeps, not from
the item code. The old field was a map keyed by item code, so two rows of the
same item were added together and there was no way back to either one. The
table that replaced it holds the invoice row and the tax row by name, which
is exactly what a per line category needs.

Nothing here recalculates an amount. Every figure is the one ERPNext posted.
What this file does is decide which official category each posted figure
belongs to, and say so plainly when it cannot.
"""

from __future__ import annotations

from uae_compliance.domain.findings import SourceRef
from uae_compliance.erpnext import mapping
from uae_compliance.erpnext.numbers import Scales, dec, flip


def tax_by_row(invoice) -> dict[str, list[dict]]:
	"""Which taxes hit which row, from the table ERPNext fills in.

	Amounts in this table are in the company's currency. They are used for
	the split between categories, never as the amount on the document, which
	comes from the invoice's own currency.
	"""
	found: dict[str, list[dict]] = {}
	for row in invoice.get("item_wise_tax_details") or []:
		found.setdefault(row.item_row, []).append(
			{
				"tax_row": row.tax_row,
				"rate": row.rate,
				"amount": row.amount,
				"taxable_amount": row.taxable_amount,
			}
		)
	return found


def extract(invoice, resolution, credit_note: bool) -> list[dict]:
	"""Every row of the invoice as a canonical line."""
	scales = Scales.of(invoice)
	source = SourceRef(doctype="Sales Invoice", name=invoice.name)
	attribution = tax_by_row(invoice)
	accounts = {row.name: row.account_head for row in invoice.get("taxes") or []}

	lines = []
	for position, row in enumerate(invoice.get("items") or [], start=1):
		lines.append(
			_line(row, position, invoice, resolution, scales, source, attribution, accounts, credit_note)
		)
	return lines


def _line(row, position, invoice, resolution, scales, source, attribution, accounts, credit_note) -> dict:
	facts = mapping.item_facts(row.item_code, row.item_group, resolution)
	treatment = _treatment(row, attribution.get(row.name) or [], accounts, invoice, resolution, source)

	quantity = dec(row.qty, scales.quantity)
	net_amount = dec(row.net_amount, scales.amount)
	if credit_note:
		# ERPNext posts a return with negative quantities and amounts. The
		# rules want a credit note stated positively under its own document
		# type, so the sign turns once, here.
		quantity = flip(quantity)
		net_amount = flip(net_amount)

	line = {
		"id": str(position),
		"source_row": row.name,
		"item_code": row.item_code or None,
		"name": row.item_name or row.description or row.item_code,
		"item_type": facts["item_type"],
		"classifications": facts["classifications"],
		"quantity": quantity,
		"uom_code": mapping.uom_code(row.uom, resolution, source, row.name),
		# ERPNext prices per invoiced unit, so the price always refers to one.
		"base_quantity": dec(1, scales.quantity),
		"net_price": dec(row.net_rate, scales.price),
		"net_amount": net_amount,
		"tax_category": treatment.get("category"),
		"tax_rate": dec(treatment.get("rate"), scales.price),
		"tax_reason": treatment.get("reason"),
		"tax_reason_code": treatment.get("reason_code"),
	}
	line.update(_prices(row, scales, invoice))
	if row.description and row.description != line["name"]:
		line["note"] = row.description
	return line


def _prices(row, scales, invoice) -> dict:
	"""The unit price, and the discount only where it can be stated exactly.

	The rules require the net price to equal the gross price less the
	discount, to the last decimal. When a row is priced with tax inside it,
	ERPNext takes the discount off the tax inclusive figure, so restating
	that discount without tax would be this app calculating a number nobody
	posted. In that case the gross price is the net price and the discount is
	left off. It is already inside the net price either way, and the rules
	forbid taking it off a second time.
	"""
	net_price = dec(row.net_rate, scales.price)
	discount = dec(row.discount_amount, scales.price)
	if not discount or _priced_with_tax_inside(invoice):
		return {"gross_price": net_price}
	return {"gross_price": net_price + discount, "price_discount": discount}


def _priced_with_tax_inside(invoice) -> bool:
	return any(row.included_in_print_rate for row in invoice.get("taxes") or [])


def _treatment(row, attributed, accounts, invoice, resolution, source) -> dict:
	"""Which official category this row's tax belongs to.

	The item's own tax template is asked first because it is the closer fact.
	Where the row carries no template, the account the tax posted to answers
	instead. A row with no tax at all still needs a category, so the lookup
	runs either way and reports when nothing covers it.
	"""
	account = None
	for hit in attributed:
		account = accounts.get(hit["tax_row"]) or account
		if account:
			break

	found = mapping.tax_category(
		invoice.company,
		account,
		row.item_tax_template,
		resolution,
		source,
		row_id=row.name,
	)
	return found or {}
