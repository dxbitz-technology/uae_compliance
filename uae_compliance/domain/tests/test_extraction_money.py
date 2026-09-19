"""The money that comes out of a Sales Invoice, checked against the rules.

The tests in test_money.py hand the money rules a document somebody wrote out
by hand. These ones build the document the way the app does, from invoice rows
and posted tax rows, and then check both the figures and what the rules make
of them. That is where the signs, the scales and the currency conversion
actually live.

Every expected figure was worked out from spec 5.3 and from the pinned
controller at erpnext/controllers/taxes_and_totals.py. None of it was read
back out of this app.

No site and no database. A small stand in for a Frappe document is enough,
because extraction only ever reads.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from uae_compliance.domain.money import (
	CODE_LINE_NET,
	CODE_TAX_AMOUNT,
	CODE_TOTALS,
	check,
	check_lines,
	check_totals,
)
from uae_compliance.erpnext import lines as line_reader
from uae_compliance.erpnext import taxes
from uae_compliance.erpnext.numbers import Scales, zero

D = Decimal

# What a Frappe document answers when nothing sets the precision. Quantities
# keep three places and an exchange rate nine, the same as the framework.
DEFAULT_PRECISION = {"qty": 3, "conversion_rate": 9}

STANDARD = {"category": "S", "rate": 5}
ZERO_RATED = {"category": "Z", "rate": 0}


class Record:
	"""Enough of a Frappe document for the extraction to read.

	Attribute access, `get` and `precision`, and a field nobody set reads as
	None. That is the whole surface extraction touches, because it never
	writes and never calls the document's own methods.
	"""

	def __init__(self, **fields):
		self.__dict__.update(fields)

	def __getattr__(self, name):
		return None

	def get(self, name, default=None):
		return self.__dict__.get(name, default)

	def precision(self, fieldname):
		places = self.__dict__.get("_precision") or {}
		return places.get(fieldname, DEFAULT_PRECISION.get(fieldname, 2))


class Masters:
	"""The three master lookups, answered from a table the test sets out.

	Only the tax category matters to the money. The unit and the item type are
	answered with something valid so they do not get in the way.
	"""

	def __init__(self, by_account=None, by_template=None):
		self.by_account = by_account or {}
		self.by_template = by_template or {}

	def item_facts(self, item_code, item_group, resolution):
		return {"item_type": "Goods", "classifications": []}

	def uom_code(self, uom, resolution, source, row_id):
		return "H87"

	def tax_category(self, company, account, template, resolution, source, row_id=None):
		if template and template in self.by_template:
			return self.by_template[template]
		return self.by_account.get(account)


def item(name, *, qty, rate, net_rate=None, net_amount=None, discount=0, **extra):
	"""One Sales Invoice Item as the controller would have left it."""
	fields = {
		"name": name,
		"item_code": "ITEM",
		"item_name": "Item",
		"uom": "Nos",
		"qty": qty,
		"rate": rate,
		"amount": rate * qty,
		"net_rate": rate if net_rate is None else net_rate,
		"net_amount": rate * qty if net_amount is None else net_amount,
		"discount_amount": discount,
	}
	fields.update(extra)
	return Record(**fields)


def tax(name, *, account, amount, inclusive=0, description=None):
	"""One Sales Taxes and Charges row. The amount is in document currency."""
	return Record(
		name=name,
		account_head=account,
		tax_amount_after_discount_amount=amount,
		included_in_print_rate=inclusive,
		description=description,
	)


def detail(item_row, tax_row, *, rate, amount, taxable):
	"""One Item Wise Tax Detail row. Both amounts are in company currency."""
	return Record(item_row=item_row, tax_row=tax_row, rate=rate, amount=amount, taxable_amount=taxable)


def invoice(*, items, taxes=(), details=(), **fields):
	values = {
		"name": "SINV-0001",
		"company": "Demo",
		"currency": "AED",
		"conversion_rate": 1,
		"is_return": 0,
		"disable_rounded_total": 0,
		"total_advance": 0,
		"rounding_adjustment": 0,
		"discount_amount": 0,
		"items": list(items),
		"taxes": list(taxes),
		"item_wise_tax_details": list(details),
	}
	values.update(fields)
	return Record(**values)


def canonical(source, masters, credit_note=False):
	"""The money half of the extraction, with no site around it.

	This follows extract.extract step for step and leaves out everything that
	needs a database. If the order of these calls changes there, it changes
	here too.
	"""
	scales = Scales.of(source)
	with patch.object(line_reader, "mapping", masters), patch.object(taxes, "mapping", masters):
		rows = line_reader.extract(source, None, credit_note)
		vat_rows, charge_rows = taxes.split_tax_rows(source, None, None)
	attribution = line_reader.tax_by_row(source)
	breakdown = taxes.breakdown(source, rows, vat_rows, attribution, scales, credit_note)
	charges = taxes.charge_rows(charge_rows, source, scales, credit_note)
	tax_total = sum((group["tax_amount"] for group in breakdown), zero(scales.amount))
	return {
		"lines": rows,
		"tax_breakdown": breakdown,
		"allowances": [],
		"charges": charges,
		"totals": taxes.totals(source, charges, tax_total, scales, credit_note),
	}


def amounts(document, *names):
	return {name: document["totals"][name] for name in names}


def codes(findings):
	return sorted(f.code for f in findings)


class TheSixWorkedExamplesThroughTheExtraction(unittest.TestCase):
	"""Spec 5.3, built from invoice rows rather than written out by hand."""

	def test_two_units_at_100_with_a_line_discount_of_20(self):
		# ERPNext holds the discount per unit, so 20 off the line is 10 off
		# each of two units. Net 180, VAT at 5 per cent is 9, total 189.
		source = invoice(
			items=[item("r1", qty=2, rate=90, discount=10)],
			taxes=[tax("t1", account="VAT 5%", amount=9.00)],
			details=[detail("r1", "t1", rate=5, amount=9.00, taxable=180.00)],
			net_total=180.00,
			grand_total=189.00,
			rounded_total=189.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		line = document["lines"][0]
		self.assertEqual(line["quantity"], D("2.000"))
		self.assertEqual(line["net_price"], D("90.00"))
		self.assertEqual(line["net_amount"], D("180.00"))
		self.assertEqual(line["gross_price"], D("100.00"))
		self.assertEqual(line["price_discount"], D("10.00"))
		self.assertEqual(document["tax_breakdown"][0]["taxable_amount"], D("180.00"))
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("9.00"))
		self.assertEqual(
			amounts(document, "line_net", "tax", "tax_inclusive", "payable"),
			{
				"line_net": D("180.00"),
				"tax": D("9.00"),
				"tax_inclusive": D("189.00"),
				"payable": D("189.00"),
			},
		)
		self.assertEqual(check(document), [])

	def test_the_same_item_on_two_rows_keeps_each_rows_own_tax(self):
		# 100 and 50 at 5 per cent give 5.00 and 2.50, and the group is 7.50
		# on 150. The old field was keyed by item code and would have added
		# the two rows together with no way back to either.
		source = invoice(
			items=[item("r1", qty=1, rate=100), item("r2", qty=1, rate=50)],
			taxes=[tax("t1", account="VAT 5%", amount=7.50)],
			details=[
				detail("r1", "t1", rate=5, amount=5.00, taxable=100.00),
				detail("r2", "t1", rate=5, amount=2.50, taxable=50.00),
			],
			net_total=150.00,
			grand_total=157.50,
			rounded_total=158.00,
			rounding_adjustment=0.50,
		)
		attributed = line_reader.tax_by_row(source)
		self.assertEqual(attributed["r1"][0]["amount"], 5.00)
		self.assertEqual(attributed["r2"][0]["amount"], 2.50)

		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual([row["net_amount"] for row in document["lines"]], [D("100.00"), D("50.00")])
		self.assertEqual(len(document["tax_breakdown"]), 1)
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("7.50"))
		self.assertEqual(document["totals"]["tax_inclusive"], D("157.50"))
		self.assertEqual(check(document), [])

	def test_105_with_the_tax_already_inside_the_price(self):
		# The controller backs the tax out before anything else reads the row:
		# net amount 105 over 1.05 is 100, and the net rate follows it.
		source = invoice(
			items=[item("r1", qty=1, rate=105, net_rate=100.00, net_amount=100.00)],
			taxes=[tax("t1", account="VAT 5%", amount=5.00, inclusive=1)],
			details=[detail("r1", "t1", rate=5, amount=5.00, taxable=100.00)],
			net_total=100.00,
			grand_total=105.00,
			rounded_total=105.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["lines"][0]["net_price"], D("100.00"))
		self.assertEqual(document["lines"][0]["net_amount"], D("100.00"))
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("5.00"))
		self.assertEqual(document["totals"]["tax_exclusive"], D("100.00"))
		self.assertEqual(check(document), [])

	def test_200_net_with_a_document_discount_of_10(self):
		# The controller spreads the discount across the rows and rewrites the
		# net amount and the net rate, so the taxable base is 190 and there is
		# no allowance to state. VAT 9.50 and 199.50 after tax.
		source = invoice(
			items=[item("r1", qty=1, rate=200, net_rate=190.00, net_amount=190.00)],
			taxes=[tax("t1", account="VAT 5%", amount=9.50)],
			details=[detail("r1", "t1", rate=5, amount=9.50, taxable=190.00)],
			discount_amount=10,
			apply_discount_on="Net Total",
			net_total=190.00,
			grand_total=199.50,
			disable_rounded_total=1,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["allowances"], [])
		self.assertEqual(document["totals"]["allowances"], D("0.00"))
		self.assertEqual(document["lines"][0]["net_amount"], D("190.00"))
		self.assertEqual(document["tax_breakdown"][0]["taxable_amount"], D("190.00"))
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("9.50"))
		self.assertEqual(document["totals"]["tax_inclusive"], D("199.50"))
		self.assertEqual(check(document), [])

	def test_a_hundred_dollars_keeps_its_hundred_dollars(self):
		# The line stays 100 in the currency it was invoiced in. The per row
		# tax arrives in dirhams, 18.36 of them, and converting it back at the
		# same rate has to give the 5.00 that was posted in dollars.
		source = invoice(
			items=[item("r1", qty=1, rate=100)],
			taxes=[tax("t1", account="VAT 5%", amount=5.00)],
			details=[detail("r1", "t1", rate=5, amount=18.36, taxable=367.25)],
			currency="USD",
			conversion_rate=3.6725,
			net_total=100.00,
			grand_total=105.00,
			rounded_total=105.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["lines"][0]["net_amount"], D("100.00"))
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("5.00"))
		self.assertEqual(document["totals"]["tax_inclusive"], D("105.00"))
		self.assertEqual(check(document), [])
		# The dirham figure the rules want alongside it, worked out here so
		# the expected value is not taken from the app.
		self.assertEqual(D("100.00") * D("3.6725"), D("367.250000"))

	def test_money_collected_afterwards_does_not_reach_the_totals(self):
		# Payment is not part of the document. The advance frozen at issue is,
		# and it is the only one of the three the totals may read.
		rows = dict(
			items=[item("r1", qty=1, rate=100)],
			taxes=[tax("t1", account="VAT 5%", amount=5.00)],
			details=[detail("r1", "t1", rate=5, amount=5.00, taxable=100.00)],
			net_total=100.00,
			grand_total=105.00,
			rounded_total=105.00,
		)
		at_issue = canonical(invoice(**rows), Masters({"VAT 5%": STANDARD}))
		paid_later = canonical(
			invoice(outstanding_amount=0.00, paid_amount=105.00, **rows),
			Masters({"VAT 5%": STANDARD}),
		)
		self.assertEqual(at_issue, paid_later)


class CreditNoteSigns(unittest.TestCase):
	"""ERPNext posts a return negative. Every field that carries a sign turns
	once, and the ones that do not turn are the ones that never carried one."""

	def build(self, **fields):
		posted = {
			"items": [item("r1", qty=-2, rate=90, net_amount=-180.00)],
			"taxes": [tax("t1", account="VAT 5%", amount=-9.00)],
			"details": [detail("r1", "t1", rate=5, amount=-9.00, taxable=-180.00)],
			"is_return": 1,
			"net_total": -180.00,
			"grand_total": -189.00,
			"rounded_total": -189.00,
		}
		posted.update(fields)
		return canonical(invoice(**posted), Masters({"VAT 5%": STANDARD}), credit_note=True)

	def test_the_quantity_and_the_line_amount_turn_and_the_price_does_not(self):
		line = self.build()["lines"][0]
		self.assertEqual(line["quantity"], D("2.000"))
		self.assertEqual(line["net_amount"], D("180.00"))
		self.assertEqual(line["net_price"], D("90.00"))

	def test_the_tax_turns_once_and_the_taxable_amount_is_not_turned_twice(self):
		group = self.build()["tax_breakdown"][0]
		self.assertEqual(group["taxable_amount"], D("180.00"))
		self.assertEqual(group["tax_amount"], D("9.00"))

	def test_the_totals_come_out_positive_and_add_up(self):
		document = self.build()
		self.assertEqual(
			amounts(document, "line_net", "tax_exclusive", "tax", "tax_inclusive", "payable"),
			{
				"line_net": D("180.00"),
				"tax_exclusive": D("180.00"),
				"tax": D("9.00"),
				"tax_inclusive": D("189.00"),
				"payable": D("189.00"),
			},
		)
		self.assertEqual(check(document), [])

	def test_a_charge_that_is_not_tax_turns_with_everything_else(self):
		source = invoice(
			items=[item("r1", qty=-1, rate=100, net_amount=-100.00)],
			taxes=[
				tax("t1", account="Freight", amount=-20.00, description="Delivery"),
				tax("t2", account="VAT 5%", amount=-5.00),
			],
			details=[detail("r1", "t2", rate=5, amount=-5.00, taxable=-100.00)],
			is_return=1,
			net_total=-100.00,
			grand_total=-125.00,
			rounded_total=-125.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}), credit_note=True)
		self.assertEqual(document["charges"][0]["amount"], D("20.00"))
		self.assertEqual(document["totals"]["charges"], D("20.00"))
		self.assertEqual(document["totals"]["tax_exclusive"], D("120.00"))
		self.assertEqual(document["totals"]["tax_inclusive"], D("125.00"))
		self.assertEqual(check_totals(document), [])

	def test_the_rounding_turns_with_the_total_it_belongs_to(self):
		# The controller writes rounding_adjustment as rounded_total minus
		# grand_total, so a credit note of 111.30 rounded to 111.00 records
		# plus 0.30. Stated positively the credit note is 111.30 before
		# rounding and 111.00 after, so the rounding is minus 0.30. Leaving
		# it as it came out of ERPNext puts the amount due out by 0.60.
		document = self.build(
			items=[item("r1", qty=-1, rate=106, net_amount=-106.00)],
			taxes=[tax("t1", account="VAT 5%", amount=-5.30)],
			details=[detail("r1", "t1", rate=5, amount=-5.30, taxable=-106.00)],
			net_total=-106.00,
			grand_total=-111.30,
			rounded_total=-111.00,
			rounding_adjustment=0.30,
		)
		self.assertEqual(document["totals"]["rounding"], D("-0.30"))
		self.assertEqual(document["totals"]["tax_inclusive"], D("111.30"))
		self.assertEqual(document["totals"]["payable"], D("111.00"))
		self.assertEqual(check_totals(document), [])

	def test_an_advance_on_a_credit_note_turns_as_well(self):
		document = self.build(total_advance=-25.00)
		self.assertEqual(document["totals"]["prepaid"], D("25.00"))
		self.assertEqual(document["totals"]["payable"], D("164.00"))
		self.assertEqual(check_totals(document), [])


class WhatIsStillDue(unittest.TestCase):
	def test_an_advance_already_collected_comes_off_the_amount_due(self):
		# ERPNext keeps grand_total and rounded_total whole and records the
		# advance beside them. The amount due is 105 less the 25 collected,
		# and stating 105 next to a prepaid amount of 25 asks for the money
		# twice.
		source = invoice(
			items=[item("r1", qty=1, rate=100)],
			taxes=[tax("t1", account="VAT 5%", amount=5.00)],
			details=[detail("r1", "t1", rate=5, amount=5.00, taxable=100.00)],
			net_total=100.00,
			grand_total=105.00,
			rounded_total=105.00,
			total_advance=25.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["totals"]["prepaid"], D("25.00"))
		self.assertEqual(document["totals"]["tax_inclusive"], D("105.00"))
		self.assertEqual(document["totals"]["payable"], D("80.00"))
		self.assertEqual(check_totals(document), [])

	def test_the_rounded_total_is_the_amount_due_when_the_site_rounds(self):
		source = invoice(
			items=[item("r1", qty=1, rate=190)],
			taxes=[tax("t1", account="VAT 5%", amount=9.50)],
			details=[detail("r1", "t1", rate=5, amount=9.50, taxable=190.00)],
			net_total=190.00,
			grand_total=199.50,
			rounded_total=200.00,
			rounding_adjustment=0.50,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["totals"]["tax_inclusive"], D("199.50"))
		self.assertEqual(document["totals"]["rounding"], D("0.50"))
		self.assertEqual(document["totals"]["payable"], D("200.00"))
		self.assertEqual(check_totals(document), [])

	def test_the_grand_total_is_the_amount_due_when_rounding_is_switched_off(self):
		source = invoice(
			items=[item("r1", qty=1, rate=190)],
			taxes=[tax("t1", account="VAT 5%", amount=9.50)],
			details=[detail("r1", "t1", rate=5, amount=9.50, taxable=190.00)],
			net_total=190.00,
			grand_total=199.50,
			disable_rounded_total=1,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["totals"]["payable"], D("199.50"))
		self.assertEqual(check_totals(document), [])


class PriceAndDiscount(unittest.TestCase):
	def test_the_net_price_is_the_gross_price_less_the_discount(self):
		row = Record(net_rate=90.0, discount_amount=10.0)
		prices = line_reader._prices(row, Scales(2, 2, 3, 9), invoice(items=[], taxes=[]))
		self.assertEqual(prices["gross_price"] - prices["price_discount"], D("90.00"))

	def test_the_rule_still_holds_when_the_price_has_tax_inside_it(self):
		# The discount was taken off a figure that included tax, so restating
		# it without tax would be a number nobody posted. It is left off and
		# the gross price is the net price, which still satisfies the rule.
		row = Record(net_rate=90.0, discount_amount=10.0)
		source = invoice(items=[], taxes=[tax("t1", account="VAT 5%", amount=5.00, inclusive=1)])
		prices = line_reader._prices(row, Scales(2, 2, 3, 9), source)
		self.assertNotIn("price_discount", prices)
		self.assertEqual(prices["gross_price"], D("90.00"))
		self.assertEqual(prices["gross_price"] - D(0), D("90.00"))

	def test_a_discount_inside_the_price_is_never_taken_off_the_line_again(self):
		source = invoice(
			items=[item("r1", qty=2, rate=90, discount=10)],
			taxes=[tax("t1", account="VAT 5%", amount=9.00)],
			details=[detail("r1", "t1", rate=5, amount=9.00, taxable=180.00)],
			net_total=180.00,
			grand_total=189.00,
			rounded_total=189.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["lines"][0]["net_amount"], D("180.00"))
		self.assertEqual(check_lines(document), [])


class RoundingAndPrecision(unittest.TestCase):
	def test_a_three_decimal_currency_keeps_all_three(self):
		source = invoice(
			items=[item("r1", qty=1, rate=100.125, _precision={"rate": 3, "qty": 3})],
			taxes=[tax("t1", account="VAT 5%", amount=5.006)],
			details=[detail("r1", "t1", rate=5, amount=5.006, taxable=100.125)],
			currency="BHD",
			net_total=100.125,
			grand_total=105.131,
			rounded_total=105.131,
			_precision={"grand_total": 3},
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["lines"][0]["net_amount"], D("100.125"))
		self.assertEqual(document["lines"][0]["net_price"], D("100.125"))
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("5.006"))
		self.assertEqual(document["totals"]["tax_inclusive"], D("105.131"))
		self.assertEqual(check(document), [])

	def test_three_items_at_100_with_the_tax_inside_the_price_cannot_be_stated(self):
		# Three at 100 including tax. The controller divides 300 by 1.05 to
		# get a net amount of 285.71, then divides that by three units to get
		# a net rate of 95.24. Three at 95.24 is 285.72, so the line amount
		# and the price do not multiply out and ibr-147-ae refuses the
		# document. The mapping has no way to state this line, and the check
		# says so here with the figures on it.
		source = invoice(
			items=[item("r1", qty=3, rate=100, net_rate=95.24, net_amount=285.71)],
			taxes=[tax("t1", account="VAT 5%", amount=14.29, inclusive=1)],
			details=[detail("r1", "t1", rate=5, amount=14.29, taxable=285.71)],
			net_total=285.71,
			grand_total=300.00,
			rounded_total=300.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["lines"][0]["net_price"], D("95.24"))
		self.assertEqual(document["lines"][0]["net_amount"], D("285.71"))
		found = check_lines(document)
		self.assertEqual(codes(found), [CODE_LINE_NET])
		self.assertEqual(found[0].params, {"stated": "285.71", "expected": "285.72"})

	def test_a_discount_taken_off_twice_is_reported(self):
		# Two units at a net price of 90 is 180. A line stating 160 has had
		# the 20 taken off a second time.
		document = {"lines": [{"quantity": D("2.000"), "net_price": D("90.00"), "net_amount": D("160.00")}]}
		found = check_lines(document)
		self.assertEqual(codes(found), [CODE_LINE_NET])
		self.assertEqual(found[0].params["expected"], "180.00")

	def test_a_return_row_with_no_quantity_is_reported(self):
		# The controller gives a return row with no quantity an amount of
		# minus the rate, which is an amount with nothing behind it. There is
		# no quantity that produces it, so it is reported rather than sent.
		source = invoice(
			items=[item("r1", qty=0, rate=50, net_amount=-50.00)],
			taxes=[tax("t1", account="VAT 5%", amount=-2.50)],
			details=[detail("r1", "t1", rate=5, amount=-2.50, taxable=-50.00)],
			is_return=1,
			net_total=-50.00,
			grand_total=-52.50,
			disable_rounded_total=1,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}), credit_note=True)
		self.assertEqual(document["lines"][0]["quantity"], D("0.000"))
		self.assertEqual(document["lines"][0]["net_amount"], D("50.00"))
		self.assertIn(CODE_LINE_NET, codes(check_lines(document)))

	def test_a_negative_line_on_an_ordinary_invoice_keeps_its_sign(self):
		# A rebate row on a normal invoice is negative and stays negative.
		# Nothing about it is a credit note, so no sign turns.
		source = invoice(
			items=[item("r1", qty=1, rate=100), item("r2", qty=1, rate=-30)],
			taxes=[tax("t1", account="VAT 5%", amount=3.50)],
			details=[
				detail("r1", "t1", rate=5, amount=5.00, taxable=100.00),
				detail("r2", "t1", rate=5, amount=-1.50, taxable=-30.00),
			],
			net_total=70.00,
			grand_total=73.50,
			disable_rounded_total=1,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual([row["net_amount"] for row in document["lines"]], [D("100.00"), D("-30.00")])
		self.assertEqual(document["tax_breakdown"][0]["taxable_amount"], D("70.00"))
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("3.50"))
		self.assertEqual(check(document), [])

	def test_a_large_amount_keeps_every_digit(self):
		source = invoice(
			items=[item("r1", qty=1, rate=9876543210.99)],
			taxes=[tax("t1", account="VAT 5%", amount=493827160.55)],
			details=[detail("r1", "t1", rate=5, amount=493827160.55, taxable=9876543210.99)],
			net_total=9876543210.99,
			grand_total=10370370371.54,
			disable_rounded_total=1,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["lines"][0]["net_amount"], D("9876543210.99"))
		self.assertEqual(document["totals"]["tax_inclusive"], D("10370370371.54"))
		self.assertEqual(check(document), [])


class ForeignCurrency(unittest.TestCase):
	"""The per row tax arrives in the company's currency and has to come back
	into the invoice's, without the parts drifting from the posted total."""

	def rows(self, conversion_rate, per_row, posted, categories):
		items = []
		details = []
		for index, (net, company_tax) in enumerate(per_row, start=1):
			name = f"r{index}"
			items.append(item(name, qty=1, rate=net))
			details.append(
				detail(name, "t1", rate=categories[index - 1]["rate"], amount=company_tax, taxable=0)
			)
		net_total = sum(net for net, _ in per_row)
		return invoice(
			items=items,
			taxes=[tax("t1", account="VAT 5%", amount=posted)],
			details=details,
			currency="USD",
			conversion_rate=conversion_rate,
			net_total=net_total,
			grand_total=net_total + posted,
			disable_rounded_total=1,
		)

	def test_the_converted_parts_add_up_to_the_posted_total(self):
		# Two dollar lines at 5 per cent, 33.33 each, give 3.33 of tax. The
		# dirham figures the controller wrote are 6.13 and 6.10, and 12.23
		# over 3.6725 is 3.33 again.
		source = self.rows(3.6725, [(33.33, 6.13), (33.33, 6.10)], 3.33, [STANDARD, STANDARD])
		source.items[0].item_tax_template = None
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["tax_breakdown"][0]["taxable_amount"], D("66.66"))
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("3.33"))
		self.assertEqual(check(document), [])

	def test_a_group_carrying_no_tax_never_absorbs_the_leftover(self):
		# A small standard rated line beside a large zero rated one, at a rate
		# under one. The dirham figures both round to nothing, so a fils of
		# the posted tax has nowhere obvious to go. It belongs to the line
		# that was actually taxed. Put on the zero rated group it would say a
		# zero rated supply carried VAT.
		source = invoice(
			items=[
				item("r1", qty=1, rate=0.11, item_tax_template="Standard"),
				item("r2", qty=1, rate=500.00, item_tax_template="Zero"),
			],
			taxes=[tax("t1", account="VAT", amount=0.01)],
			details=[
				detail("r1", "t1", rate=5, amount=0.00, taxable=0.03),
				detail("r2", "t1", rate=0, amount=0.00, taxable=136.15),
			],
			currency="USD",
			conversion_rate=0.2723,
			net_total=500.11,
			grand_total=500.12,
			disable_rounded_total=1,
		)
		masters = Masters({"VAT": STANDARD}, {"Standard": STANDARD, "Zero": ZERO_RATED})
		document = canonical(source, masters)
		groups = {row["category"]: row["tax_amount"] for row in document["tax_breakdown"]}
		self.assertEqual(groups, {"S": D("0.01"), "Z": D("0.00")})
		self.assertNotIn(CODE_TAX_AMOUNT, codes(check(document)))

	def test_the_per_row_tax_is_converted_the_right_way_round(self):
		# Two taxed groups are needed to see this at all. With one group the
		# leftover is put back on that same group, so it ends up holding the
		# posted total whatever the conversion did to it. With two, the split
		# between them is the conversion's own answer.
		#
		# 100 and 200 dollars at 5 per cent are 5.00 and 10.00. The dirham
		# figures the controller wrote are 18.36 and 36.73, and those over
		# 3.6725 come back to 5.00 and 10.00 with nothing left over.
		source = invoice(
			items=[
				item("r1", qty=1, rate=100.00, item_tax_template="Standard"),
				item("r2", qty=1, rate=200.00, item_tax_template="Margin"),
			],
			taxes=[tax("t1", account="VAT 5%", amount=15.00)],
			details=[
				detail("r1", "t1", rate=5, amount=18.36, taxable=367.25),
				detail("r2", "t1", rate=5, amount=36.73, taxable=734.50),
			],
			currency="USD",
			conversion_rate=3.6725,
			net_total=300.00,
			grand_total=315.00,
			disable_rounded_total=1,
		)
		masters = Masters(
			{"VAT 5%": STANDARD},
			{"Standard": STANDARD, "Margin": {"category": "N", "rate": 5}},
		)
		document = canonical(source, masters)
		groups = {row["category"]: row["tax_amount"] for row in document["tax_breakdown"]}
		self.assertEqual(groups, {"N": D("10.00"), "S": D("5.00")})
		self.assertEqual(document["totals"]["tax"], D("15.00"))
		self.assertEqual(check(document), [])

	def test_the_invoice_currency_amounts_are_never_the_converted_ones(self):
		source = self.rows(3.6725, [(100.00, 18.36)], 5.00, [STANDARD])
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["lines"][0]["net_amount"], D("100.00"))
		self.assertEqual(document["totals"]["line_net"], D("100.00"))
		self.assertEqual(document["totals"]["tax"], D("5.00"))


class ChargesThatAreNotTax(unittest.TestCase):
	def test_a_charge_with_no_tax_mapping_is_carried_as_a_charge(self):
		source = invoice(
			items=[item("r1", qty=1, rate=100)],
			taxes=[
				tax("t1", account="VAT 5%", amount=5.00),
				tax("t2", account="Freight", amount=20.00, description="Delivery"),
			],
			details=[detail("r1", "t1", rate=5, amount=5.00, taxable=100.00)],
			net_total=100.00,
			grand_total=125.00,
			rounded_total=125.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["charges"][0]["amount"], D("20.00"))
		self.assertEqual(document["charges"][0]["reason"], "Delivery")
		self.assertEqual(document["totals"]["charges"], D("20.00"))
		self.assertEqual(document["totals"]["tax_exclusive"], D("120.00"))
		self.assertEqual(document["totals"]["tax"], D("5.00"))
		self.assertEqual(check_totals(document), [])

	def test_a_charge_the_tax_was_worked_out_on_is_reported(self):
		# Freight of 20 taken before a 5 per cent row gives 6.00 of VAT on a
		# base of 120. The group base is built from the lines alone, so it
		# says 100 and the tax does not match it. That is a real gap between
		# the model and the posting and it has to be said out loud.
		source = invoice(
			items=[item("r1", qty=1, rate=100)],
			taxes=[
				tax("t1", account="Freight", amount=20.00, description="Delivery"),
				tax("t2", account="VAT 5%", amount=6.00),
			],
			details=[detail("r1", "t2", rate=5, amount=6.00, taxable=120.00)],
			net_total=100.00,
			grand_total=126.00,
			rounded_total=126.00,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertEqual(document["tax_breakdown"][0]["taxable_amount"], D("100.00"))
		self.assertEqual(document["tax_breakdown"][0]["tax_amount"], D("6.00"))
		self.assertIn(CODE_TAX_AMOUNT, codes(check(document)))


class WhatTheChecksSayAboutTheseDocuments(unittest.TestCase):
	def test_an_invoice_whose_totals_do_not_follow_its_lines_is_reported(self):
		source = invoice(
			items=[item("r1", qty=1, rate=100)],
			taxes=[tax("t1", account="VAT 5%", amount=5.00)],
			details=[detail("r1", "t1", rate=5, amount=5.00, taxable=100.00)],
			net_total=140.00,
			grand_total=145.00,
			disable_rounded_total=1,
		)
		document = canonical(source, Masters({"VAT 5%": STANDARD}))
		self.assertIn(CODE_TOTALS, codes(check(document)))


if __name__ == "__main__":
	unittest.main()
