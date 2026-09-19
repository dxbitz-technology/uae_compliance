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

from decimal import ROUND_UP, Decimal

from uae_compliance.domain.findings import SourceRef
from uae_compliance.erpnext import mapping
from uae_compliance.erpnext.numbers import Scales, dec, flip, zero


def tax_by_row(invoice) -> dict[str, list[dict]]:
	"""Which taxes hit which row, from the table ERPNext fills in.

	Amounts in this table are in the company's currency. They are used for
	the split between categories, never as the amount on the document, which
	comes from the invoice's own currency.

	The saved table is empty while a document is being submitted, because
	the controller clears it and rebuilds it into a working attribute that
	is only written out afterwards. Reading a document mid-submit therefore
	has to look at the working one, or every line comes back with no tax and
	no category at the exact moment it matters most.
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
	if found:
		return found

	# The working attribute holds the documents themselves rather than their
	# names, because the names do not exist yet when it is built.
	for row in getattr(invoice, "_item_wise_tax_details", None) or []:
		item = getattr(row, "item", None)
		tax = getattr(row, "tax", None)
		if not item or not tax:
			continue
		found.setdefault(item.name, []).append(
			{
				"tax_row": tax.name,
				"rate": row.get("rate"),
				"amount": row.get("amount"),
				"taxable_amount": row.get("taxable_amount"),
			}
		)
	return found


def extract(invoice, resolution, credit_note: bool, conversion_rate=None) -> list[dict]:
	"""Every row of the invoice as a canonical line."""
	scales = Scales.of(invoice)
	source = SourceRef(doctype="Sales Invoice", name=invoice.name)
	attribution = tax_by_row(invoice)
	accounts = {row.name: row.account_head for row in invoice.get("taxes") or []}

	lines = []
	for position, row in enumerate(invoice.get("items") or [], start=1):
		lines.append(
			_line(
				row,
				position,
				invoice,
				resolution,
				scales,
				source,
				attribution,
				accounts,
				credit_note,
				conversion_rate,
			)
		)
	return lines


def _line(
	row,
	position,
	invoice,
	resolution,
	scales,
	source,
	attribution,
	accounts,
	credit_note,
	conversion_rate=None,
) -> dict:
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
		"tax_amount": _posted_tax(
			attribution.get(row.name) or [],
			accounts,
			treatment.get("account"),
			scales,
			credit_note,
			conversion_rate,
		),
		"tax_reason": treatment.get("reason"),
		"tax_reason_code": treatment.get("reason_code"),
	}
	line.update(_prices(row, scales, invoice))
	_settle_the_line(line, scales)
	if row.description and row.description != line["name"]:
		line["note"] = row.description
	return line


def _posted_tax(attributed, accounts, account, scales, credit_note, conversion_rate):
	"""The tax ERPNext actually posted against this line.

	Read, never worked out. Multiplying the line by its rate and rounding
	gives a figure that can disagree with the document total, and the
	document total is the one that was posted.

	Only the row that gave this line its treatment. A line can have several
	rows against it and only one of them is tax: freight before a VAT row
	put 20 and 6 against the same line, and adding both stated 26 of tax.

	The per row table holds company currency amounts, so an invoice in
	another currency converts them the same way the group totals do.
	"""
	if not attributed or not account:
		return None
	total = zero(scales.amount)
	for hit in attributed:
		if accounts.get(hit["tax_row"]) != account:
			continue
		amount = dec(hit["amount"], scales.amount)
		if amount is None:
			continue
		if conversion_rate and conversion_rate != 1:
			amount = dec(amount / Decimal(str(conversion_rate)), scales.amount)
		total += amount
	return flip(total) if credit_note else total


def _settle_the_line(line: dict, scales: Scales):
	"""State the fils that a divided price cannot carry.

	The rule is exact: the line amount must equal the quantity times the
	unit price, plus line charges, less line allowances. ERPNext works the
	other way round when tax is inside the price, taking the amount first
	and dividing to get the unit price, so three items at 100 with five
	percent inside give a net of 285.71 and a unit price of 95.24. Three of
	those is 285.72 and the rule fails by a fils.

	Nothing here is wrong. The amount, the price and the quantity are all
	what was posted, and an ordinary invoice was being refused with nothing
	anybody could change about it.

	So the difference is stated rather than hidden. The rule's own
	arithmetic makes room for it, and a reader sees a one fils adjustment
	with its reason instead of an invoice that will not go.
	"""
	price = line.get("net_price")
	quantity = line.get("quantity")
	amount = line.get("net_amount")
	if not all(isinstance(value, Decimal) for value in (price, quantity, amount)):
		return

	multiplied = dec(price * quantity, scales.amount)
	difference = dec(amount - multiplied, scales.amount)
	if not difference:
		return

	# Only a difference that rounding the unit price could actually have
	# produced. Rounding a price moves it by at most half a unit, so across
	# the quantity it can move the line by at most that much again.
	#
	# Anything larger is a real disagreement between the amount and the
	# price, such as a row with an amount and no quantity, and stating it as
	# an adjustment would hide exactly what the arithmetic check exists to
	# find.
	half = Decimal(1).scaleb(-scales.price) / 2
	allowed = (abs(quantity) * half).quantize(Decimal(1).scaleb(-scales.amount), rounding=ROUND_UP)
	if abs(difference) > allowed:
		return

	adjustment = {
		"amount": abs(difference),
		"reason": "Rounding on the unit price",
		"tax_category": line.get("tax_category"),
		"tax_rate": line.get("tax_rate"),
	}
	# More than the price times the quantity is a charge, less is an
	# allowance. Which way round follows the rule's own formula.
	line.setdefault("charges" if difference > 0 else "allowances", []).append(adjustment)


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
	# Every account this line's tax was posted to, in order. A line carrying
	# freight and then VAT has two, and only the second is a tax treatment.
	# Taking the first meant a line like that came back with no category at
	# all, and the invoice with no tax breakdown.
	touched = [accounts[hit["tax_row"]] for hit in attributed if hit["tax_row"] in accounts]

	# Asked one account at a time, so we know which one answered. Its own
	# row is the one carrying this line's tax, and the others are not tax.
	for account in touched:
		found = mapping.tax_category(
			invoice.company, account, row.item_tax_template, resolution, source, quiet=True
		)
		if found:
			return {**found, "account": account}

	# Nothing matched. Asked again without the quiet, so the finding says
	# every account it tried rather than only the last.
	found = mapping.tax_category(
		invoice.company,
		touched,
		row.item_tax_template,
		resolution,
		source,
		row_id=row.name,
	)
	return {**found, "account": None} if found else {}
