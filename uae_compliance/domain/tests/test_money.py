"""The money rules, built around the six worked examples in the specification.

Each expected figure here was worked out by hand from the specification table,
not taken from what the code produces. If a number in this file ever changes,
something about the rules changed with it.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from uae_compliance.domain.encoding import business_hash, canonical_bytes
from uae_compliance.domain.findings import Severity, Stage
from uae_compliance.domain.money import (
	CODE_AED,
	CODE_AED_TOTAL,
	CODE_GROUP_MISSING,
	CODE_GROUP_UNKNOWN,
	CODE_LINE_NET,
	CODE_RATE_MISSING,
	CODE_TAX_AMOUNT,
	CODE_TAX_BASE,
	CODE_TOTALS,
	check,
	check_currency,
	check_lines,
	check_tax_breakdown,
	check_totals,
)

D = Decimal


def line(net_amount, *, quantity="1", net_price=None, category="S", rate="5", **extra):
	row = {
		"id": extra.pop("id", "1"),
		"source_row": "row-1",
		"name": "Item",
		"quantity": D(quantity),
		"uom_code": "H87",
		"net_price": D(net_price if net_price is not None else net_amount),
		"net_amount": D(net_amount),
		"tax_category": category,
		"tax_rate": D(rate),
	}
	row.update(extra)
	return row


def tax_row(taxable, tax, *, category="S", rate="5", **extra):
	row = {
		"category": category,
		"rate": D(rate),
		"taxable_amount": D(taxable),
		"tax_amount": D(tax),
	}
	row.update(extra)
	return row


def totals(line_net, tax_exclusive, tax, tax_inclusive, payable, **extra):
	row = {
		"line_net": D(line_net),
		"allowances": D("0.00"),
		"charges": D("0.00"),
		"tax_exclusive": D(tax_exclusive),
		"tax": D(tax),
		"tax_inclusive": D(tax_inclusive),
		"payable": D(payable),
	}
	row.update(extra)
	return row


def codes(findings):
	return sorted(f.code for f in findings)


class TheSixWorkedExamples(unittest.TestCase):
	"""Straight from the table in the specification."""

	def test_two_units_at_100_with_a_20_discount(self):
		# Two at 100 less 20 gives net 180, VAT at 5 per cent is 9, total 189.
		invoice = {
			"lines": [line("180.00", quantity="2", net_price="90.00")],
			"tax_breakdown": [tax_row("180.00", "9.00")],
			"totals": totals("180.00", "180.00", "9.00", "189.00", "189.00"),
		}
		self.assertEqual(check(invoice), [])

	def test_the_same_item_on_two_rows_at_different_prices(self):
		# 100 and 50 at 5 per cent give 5.00 and 2.50. Total 157.50.
		# The two rows keep their own identity; nothing is merged by item code.
		invoice = {
			"lines": [
				line("100.00", id="1"),
				line("50.00", id="2"),
			],
			"tax_breakdown": [tax_row("150.00", "7.50")],
			"totals": totals("150.00", "150.00", "7.50", "157.50", "157.50"),
		}
		self.assertEqual(check(invoice), [])
		self.assertEqual(
			(D("100.00") * D(5) / D(100), D("50.00") * D(5) / D(100)),
			(D("5.00"), D("2.50")),
		)

	def test_105_inclusive_of_tax_at_five_per_cent(self):
		# The source has already backed the tax out: net 100, tax 5.
		invoice = {
			"lines": [line("100.00")],
			"tax_breakdown": [tax_row("100.00", "5.00")],
			"totals": totals("100.00", "100.00", "5.00", "105.00", "105.00"),
		}
		self.assertEqual(check(invoice), [])

	def test_200_net_with_a_document_allowance_of_10(self):
		# Taxable 190, VAT 9.50, total 199.50.
		invoice = {
			"lines": [line("200.00")],
			"allowances": [
				{"amount": D("10.00"), "tax_category": "S", "tax_rate": D(5), "reason": "Goodwill"}
			],
			"tax_breakdown": [tax_row("190.00", "9.50")],
			"totals": totals("200.00", "190.00", "9.50", "199.50", "199.50", allowances=D("10.00")),
		}
		self.assertEqual(check(invoice), [])

	def test_a_hundred_dollars_at_the_example_rate(self):
		# The dollar amount stays 100. The dirham figure follows the rate.
		invoice = {
			"lines": [line("100.00")],
			"tax_breakdown": [tax_row("100.00", "5.00", tax_amount_aed=D("18.3625"))],
			"totals": totals("100.00", "100.00", "5.00", "105.00", "105.00"),
			"exchange_rates": {
				"to_aed": {
					"from_currency": "USD",
					"to_currency": "AED",
					"rate": D("3.6725"),
					"date": "2026-09-17",
					"source": "Currency Exchange",
				}
			},
		}
		self.assertEqual(check(invoice), [])
		self.assertEqual(D("100.00") * D("3.6725"), D("367.250000"))

	def test_an_invoice_paid_later_keeps_its_bytes_and_its_hash(self):
		# Payment collected afterwards is not part of the document at all, so
		# there is nothing that could move.
		invoice = {
			"lines": [line("180.00", quantity="2", net_price="90.00")],
			"tax_breakdown": [tax_row("180.00", "9.00")],
			"totals": totals("180.00", "180.00", "9.00", "189.00", "189.00"),
		}
		before = canonical_bytes(invoice)
		before_hash = business_hash(invoice)
		# The client pays. Nothing about the issued document changes.
		self.assertEqual(canonical_bytes(invoice), before)
		self.assertEqual(business_hash(invoice), before_hash)
		self.assertNotIn(b"outstanding", before)


class TheThreeIdentities(unittest.TestCase):
	def test_a_wrong_line_total_is_reported(self):
		invoice = {
			"lines": [line("100.00"), line("50.00", id="2")],
			"totals": totals("140.00", "140.00", "7.00", "147.00", "147.00"),
		}
		self.assertIn(CODE_TOTALS, codes(check_totals(invoice)))

	def test_a_wrong_amount_before_tax_is_reported(self):
		invoice = {
			"lines": [line("200.00")],
			"allowances": [{"amount": D("10.00"), "tax_category": "S", "tax_rate": D(5)}],
			"totals": totals("200.00", "200.00", "10.00", "210.00", "210.00"),
		}
		found = check_totals(invoice)
		self.assertIn(CODE_TOTALS, codes(found))
		self.assertEqual(found[0].params["expected"], "190.00")

	def test_a_wrong_amount_after_tax_is_reported(self):
		invoice = {
			"lines": [line("100.00")],
			"totals": totals("100.00", "100.00", "5.00", "106.00", "106.00"),
		}
		self.assertIn(CODE_TOTALS, codes(check_totals(invoice)))

	def test_payable_takes_the_prepaid_amount_off(self):
		invoice = {
			"lines": [line("100.00")],
			"totals": totals("100.00", "100.00", "5.00", "105.00", "80.00", prepaid=D("25.00")),
		}
		self.assertEqual(check_totals(invoice), [])

	def test_rounding_is_its_own_field_and_closes_the_gap(self):
		invoice = {
			"lines": [line("100.00")],
			"totals": totals("100.00", "100.00", "5.00", "105.00", "105.02", rounding=D("0.02")),
		}
		self.assertEqual(check_totals(invoice), [])

	def test_a_gap_with_no_rounding_to_explain_it_is_an_error(self):
		invoice = {
			"lines": [line("100.00")],
			"totals": totals("100.00", "100.00", "5.00", "105.00", "105.02"),
		}
		self.assertIn(CODE_TOTALS, codes(check_totals(invoice)))


class TaxGrouping(unittest.TestCase):
	def test_groups_are_category_and_rate_together_not_rate_alone(self):
		# Zero rated and exempt both carry no tax and are not the same thing.
		invoice = {
			"lines": [
				line("100.00", category="Z", rate="0", id="1"),
				line("50.00", category="E", rate="0", id="2"),
			],
			"tax_breakdown": [
				tax_row("100.00", "0.00", category="Z", rate="0"),
				tax_row("50.00", "0.00", category="E", rate="0"),
			],
		}
		self.assertEqual(check_tax_breakdown(invoice), [])

	def test_merging_two_categories_at_the_same_rate_is_reported(self):
		invoice = {
			"lines": [
				line("100.00", category="Z", rate="0", id="1"),
				line("50.00", category="E", rate="0", id="2"),
			],
			"tax_breakdown": [tax_row("150.00", "0.00", category="Z", rate="0")],
		}
		found = check_tax_breakdown(invoice)
		self.assertIn(CODE_GROUP_MISSING, codes(found))
		self.assertIn(CODE_TAX_BASE, codes(found))

	def test_a_group_the_invoice_never_uses_is_reported(self):
		invoice = {
			"lines": [line("100.00")],
			"tax_breakdown": [
				tax_row("100.00", "5.00"),
				tax_row("40.00", "0.00", category="Z", rate="0"),
			],
		}
		self.assertIn(CODE_GROUP_UNKNOWN, codes(check_tax_breakdown(invoice)))

	def test_a_group_used_but_not_declared_is_reported(self):
		invoice = {
			"lines": [line("100.00"), line("40.00", category="Z", rate="0", id="2")],
			"tax_breakdown": [tax_row("100.00", "5.00")],
		}
		self.assertIn(CODE_GROUP_MISSING, codes(check_tax_breakdown(invoice)))

	def test_a_document_allowance_reduces_its_own_group(self):
		invoice = {
			"lines": [line("200.00")],
			"allowances": [{"amount": D("10.00"), "tax_category": "S", "tax_rate": D(5)}],
			"tax_breakdown": [tax_row("190.00", "9.50")],
		}
		self.assertEqual(check_tax_breakdown(invoice), [])

	def test_a_document_charge_adds_to_its_own_group(self):
		invoice = {
			"lines": [line("200.00")],
			"charges": [{"amount": D("20.00"), "tax_category": "S", "tax_rate": D(5)}],
			"tax_breakdown": [tax_row("220.00", "11.00")],
		}
		self.assertEqual(check_tax_breakdown(invoice), [])

	def test_tax_that_does_not_match_its_base_at_its_rate_is_reported(self):
		invoice = {
			"lines": [line("100.00")],
			"tax_breakdown": [tax_row("100.00", "4.00")],
		}
		found = check_tax_breakdown(invoice)
		self.assertIn(CODE_TAX_AMOUNT, codes(found))
		self.assertEqual(found[0].params["expected"], "5.00")


class LineAmounts(unittest.TestCase):
	def test_quantity_times_price_gives_the_line_amount(self):
		invoice = {"lines": [line("180.00", quantity="2", net_price="90.00")]}
		self.assertEqual(check_lines(invoice), [])

	def test_a_line_that_does_not_multiply_out_is_reported(self):
		invoice = {"lines": [line("200.00", quantity="2", net_price="90.00")]}
		found = check_lines(invoice)
		self.assertIn(CODE_LINE_NET, codes(found))
		self.assertEqual(found[0].params["expected"], "180.00")

	def test_a_discount_already_in_the_price_is_not_taken_off_again(self):
		# Gross 100, discount 10, net price 90. Two units make 180, not 160.
		invoice = {
			"lines": [
				line(
					"180.00",
					quantity="2",
					net_price="90.00",
					gross_price=D("100.00"),
					price_discount=D("10.00"),
				)
			]
		}
		self.assertEqual(check_lines(invoice), [])

	def test_a_price_for_a_batch_divides_by_its_base_quantity(self):
		# 12.00 per box of 10, three units, gives 3.60.
		invoice = {"lines": [line("3.60", quantity="3", net_price="12.00", base_quantity=D("10"))]}
		self.assertEqual(check_lines(invoice), [])

	def test_line_allowances_and_charges_land_on_the_line(self):
		invoice = {
			"lines": [
				line(
					"95.00",
					quantity="1",
					net_price="100.00",
					allowances=[{"amount": D("10.00"), "tax_category": "S", "tax_rate": D(5)}],
					charges=[{"amount": D("5.00"), "tax_category": "S", "tax_rate": D(5)}],
				)
			]
		}
		self.assertEqual(check_lines(invoice), [])


class ForeignCurrency(unittest.TestCase):
	def test_dirham_amounts_without_a_rate_are_reported(self):
		invoice = {"tax_breakdown": [tax_row("100.00", "5.00", tax_amount_aed=D("18.36"))]}
		self.assertIn(CODE_RATE_MISSING, codes(check_currency(invoice)))

	def test_a_dirham_total_that_says_more_than_the_breakdown_is_reported(self):
		# The classic way it goes wrong: a freight charge posted through the
		# taxes table lands in the total but belongs to no VAT group.
		invoice = {
			"tax_breakdown": [tax_row("100.00", "5.00", tax_amount_aed=D("18.36"))],
			"totals": {"tax_in_aed": D("91.81")},
		}
		self.assertIn(CODE_AED_TOTAL, codes(check_currency(invoice)))

	def test_a_dirham_total_that_matches_the_breakdown_is_clean(self):
		invoice = {
			"tax_breakdown": [
				tax_row("100.00", "5.00", tax_amount_aed=D("18.36")),
				tax_row("50.00", "2.50", tax_amount_aed=D("9.18")),
			],
			"totals": {"tax_in_aed": D("27.54")},
			"exchange_rates": {"to_aed": {"rate": D("3.6725")}},
		}
		self.assertNotIn(CODE_AED_TOTAL, codes(check_currency(invoice)))

	def test_a_dirham_amount_that_does_not_follow_the_rate_is_reported(self):
		invoice = {
			"tax_breakdown": [tax_row("100.00", "5.00", tax_amount_aed=D("20.0000"))],
			"exchange_rates": {
				"to_aed": {
					"from_currency": "USD",
					"to_currency": "AED",
					"rate": D("3.6725"),
					"date": "2026-09-17",
					"source": "Currency Exchange",
				}
			},
		}
		found = check_currency(invoice)
		self.assertIn(CODE_AED, codes(found))
		self.assertEqual(found[0].params["expected"], "18.3625")

	def test_an_invoice_with_no_dirham_figures_needs_no_rate(self):
		self.assertEqual(check_currency({"tax_breakdown": [tax_row("100.00", "5.00")]}), [])


class WhatTheseChecksAre(unittest.TestCase):
	def test_every_finding_belongs_to_the_arithmetic_stage_and_names_a_repair(self):
		invoice = {
			"lines": [line("100.00")],
			"totals": totals("999.00", "999.00", "5.00", "105.00", "105.00"),
		}
		found = check(invoice)
		self.assertTrue(found)
		for item in found:
			self.assertIs(item.stage, Stage.ARITHMETIC)
			self.assertIs(item.severity, Severity.ERROR)
			self.assertTrue(item.repair)
			self.assertTrue(item.path)

	def test_nothing_here_rewrites_the_invoice(self):
		invoice = {
			"lines": [line("100.00")],
			"totals": totals("999.00", "999.00", "5.00", "105.00", "105.00"),
		}
		before = canonical_bytes(invoice)
		check(invoice)
		self.assertEqual(canonical_bytes(invoice), before)


if __name__ == "__main__":
	unittest.main(verbosity=2)
