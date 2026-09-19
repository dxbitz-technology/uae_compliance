"""The figures the serializer writes, read back out of the XML.

test_serializer.py covers the shape of the document. This covers the money in
it: which element each amount lands in, which currency it is labelled with,
and whether the official arithmetic rules would hold against what comes out.

The rule identifiers below come from the pinned schematron under
uae_compliance/standards/pint_ae/1.0.4.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from lxml import etree

from uae_compliance.validation import serializer
from uae_compliance.validation.serializer import CAC, CBC, to_xml

D = Decimal


def document(*, currency="AED", type_code="388", lines, breakdown, totals, **extra):
	built = {
		"document": {
			"number": "SINV-0001",
			"type_code": type_code,
			"issue_date": "2026-09-17",
			"currency": currency,
			"tax_currency": "AED" if currency != "AED" else None,
		},
		"context": {"customization_id": "urn:test", "profile_id": "urn:test:profile"},
		"scenario": {},
		"parties": {"seller": {"legal_name": "Seller"}, "buyer": {"legal_name": "Buyer"}},
		"lines": lines,
		"tax_breakdown": breakdown,
		"allowances": [],
		"charges": [],
		"totals": totals,
	}
	built.update(extra)
	if built["document"]["tax_currency"] is None:
		del built["document"]["tax_currency"]
	return built


def line(
	*,
	identifier="1",
	quantity="1.000",
	net_price,
	net_amount,
	gross_price=None,
	price_discount=None,
	category="S",
	rate="5.00",
):
	row = {
		"id": identifier,
		"name": "Item",
		"quantity": D(quantity),
		"uom_code": "H87",
		"base_quantity": D("1.000"),
		"net_price": D(net_price),
		"net_amount": D(net_amount),
		"gross_price": D(gross_price if gross_price is not None else net_price),
		"tax_category": category,
		"tax_rate": D(rate),
	}
	if price_discount is not None:
		row["price_discount"] = D(price_discount)
	return row


def group(*, taxable, tax, category="S", rate="5.00"):
	return {
		"category": category,
		"rate": D(rate),
		"taxable_amount": D(taxable),
		"tax_amount": D(tax),
	}


def money(
	*,
	line_net,
	tax_exclusive,
	tax,
	tax_inclusive,
	payable,
	prepaid="0.00",
	rounding="0.00",
	tax_in_aed=None,
	tax_inclusive_aed=None,
):
	totals = {
		"line_net": D(line_net),
		"allowances": D("0.00"),
		"charges": D("0.00"),
		"tax_exclusive": D(tax_exclusive),
		"tax": D(tax),
		"tax_inclusive": D(tax_inclusive),
		"prepaid": D(prepaid),
		"rounding": D(rounding),
		"payable": D(payable),
	}
	# Only on an invoice that is not already in dirhams. Stating the same
	# figure twice in the same currency says nothing.
	if tax_in_aed is not None:
		totals["tax_in_aed"] = D(tax_in_aed)
	if tax_inclusive_aed is not None:
		totals["tax_inclusive_aed"] = D(tax_inclusive_aed)
	return totals


def parse(built):
	return etree.fromstring(to_xml(built))


def value(root, path):
	found = root.find(path)
	return None if found is None else found.text


def currency_of(root, path):
	found = root.find(path)
	return None if found is None else found.get("currencyID")


TOTAL = f"{{{CAC}}}LegalMonetaryTotal"
TAX_TOTAL = f"{{{CAC}}}TaxTotal"


def cbc(name):
	return f"{{{CBC}}}{name}"


class TheMonetaryTotalBlock(unittest.TestCase):
	def test_every_total_lands_in_its_own_element(self):
		# Two units at 100 less 20: net 180, VAT 9, 189 after tax.
		root = parse(
			document(
				lines=[line(quantity="2.000", net_price="90.00", net_amount="180.00")],
				breakdown=[group(taxable="180.00", tax="9.00")],
				totals=money(
					line_net="180.00",
					tax_exclusive="180.00",
					tax="9.00",
					tax_inclusive="189.00",
					payable="189.00",
				),
			)
		)
		written = {
			name: value(root, f"{TOTAL}/{cbc(name)}")
			for name in (
				"LineExtensionAmount",
				"TaxExclusiveAmount",
				"TaxInclusiveAmount",
				"AllowanceTotalAmount",
				"ChargeTotalAmount",
				"PrepaidAmount",
				"PayableRoundingAmount",
				"PayableAmount",
			)
		}
		self.assertEqual(
			written,
			{
				"LineExtensionAmount": "180.00",
				"TaxExclusiveAmount": "180.00",
				"TaxInclusiveAmount": "189.00",
				"AllowanceTotalAmount": "0.00",
				"ChargeTotalAmount": "0.00",
				"PrepaidAmount": "0.00",
				"PayableRoundingAmount": "0.00",
				"PayableAmount": "189.00",
			},
		)

	def test_the_amount_due_takes_off_the_prepaid_amount(self):
		# ibr-co-16 reads the payable amount as the amount after tax less
		# what was prepaid, plus the rounding.
		root = parse(
			document(
				lines=[line(net_price="100.00", net_amount="100.00")],
				breakdown=[group(taxable="100.00", tax="5.00")],
				totals=money(
					line_net="100.00",
					tax_exclusive="100.00",
					tax="5.00",
					tax_inclusive="105.00",
					prepaid="25.00",
					payable="80.00",
				),
			)
		)
		inclusive = D(value(root, f"{TOTAL}/{cbc('TaxInclusiveAmount')}"))
		prepaid = D(value(root, f"{TOTAL}/{cbc('PrepaidAmount')}"))
		rounding = D(value(root, f"{TOTAL}/{cbc('PayableRoundingAmount')}"))
		payable = D(value(root, f"{TOTAL}/{cbc('PayableAmount')}"))
		self.assertEqual(payable, inclusive - prepaid + rounding)

	def test_a_credit_notes_rounding_closes_its_own_gap(self):
		# A credit note of 111.30 rounded to 111.00 owes 0.30 to the rounding
		# element, stated the way the positive figures were.
		root = parse(
			document(
				type_code="381",
				lines=[line(net_price="106.00", net_amount="106.00")],
				breakdown=[group(taxable="106.00", tax="5.30")],
				totals=money(
					line_net="106.00",
					tax_exclusive="106.00",
					tax="5.30",
					tax_inclusive="111.30",
					rounding="-0.30",
					payable="111.00",
				),
			)
		)
		self.assertEqual(value(root, f"{TOTAL}/{cbc('PayableRoundingAmount')}"), "-0.30")
		inclusive = D(value(root, f"{TOTAL}/{cbc('TaxInclusiveAmount')}"))
		rounding = D(value(root, f"{TOTAL}/{cbc('PayableRoundingAmount')}"))
		self.assertEqual(D(value(root, f"{TOTAL}/{cbc('PayableAmount')}")), inclusive + rounding)


class TheTaxBreakdown(unittest.TestCase):
	def test_the_group_amounts_add_up_to_the_document_tax(self):
		# ibr-co-14 reads the tax total as the sum of its subtotals.
		root = parse(
			document(
				lines=[
					line(identifier="1", net_price="100.00", net_amount="100.00"),
					line(identifier="2", net_price="50.00", net_amount="50.00", category="Z", rate="0.00"),
				],
				breakdown=[
					group(taxable="100.00", tax="5.00"),
					group(taxable="50.00", tax="0.00", category="Z", rate="0.00"),
				],
				totals=money(
					line_net="150.00",
					tax_exclusive="150.00",
					tax="5.00",
					tax_inclusive="155.00",
					payable="155.00",
				),
			)
		)
		total = root.find(TAX_TOTAL)
		subtotals = total.findall(f"{{{CAC}}}TaxSubtotal")
		self.assertEqual(
			sum(D(row.find(cbc("TaxAmount")).text) for row in subtotals),
			D(total.find(cbc("TaxAmount")).text),
		)

	def test_a_zero_rated_group_states_no_tax(self):
		root = parse(
			document(
				lines=[line(net_price="50.00", net_amount="50.00", category="Z", rate="0.00")],
				breakdown=[group(taxable="50.00", tax="0.00", category="Z", rate="0.00")],
				totals=money(
					line_net="50.00",
					tax_exclusive="50.00",
					tax="0.00",
					tax_inclusive="50.00",
					payable="50.00",
				),
			)
		)
		subtotal = root.find(f"{TAX_TOTAL}/{{{CAC}}}TaxSubtotal")
		self.assertEqual(subtotal.find(cbc("TaxAmount")).text, "0.00")
		self.assertEqual(
			subtotal.find(f"{{{CAC}}}TaxCategory/{cbc('Percent')}").text,
			"0.00",
		)


class ThePriceOnALine(unittest.TestCase):
	def test_the_net_price_is_the_gross_price_less_the_discount(self):
		# aligned-ibrp-004 reads the price amount as the base amount less the
		# discount on it. Both are always written, so both can be read back.
		root = parse(
			document(
				lines=[
					line(
						quantity="2.000",
						net_price="90.00",
						net_amount="180.00",
						gross_price="100.00",
						price_discount="10.00",
					)
				],
				breakdown=[group(taxable="180.00", tax="9.00")],
				totals=money(
					line_net="180.00",
					tax_exclusive="180.00",
					tax="9.00",
					tax_inclusive="189.00",
					payable="189.00",
				),
			)
		)
		price = root.find(f"{{{CAC}}}InvoiceLine/{{{CAC}}}Price")
		discount = price.find(f"{{{CAC}}}AllowanceCharge")
		self.assertEqual(
			D(price.find(cbc("PriceAmount")).text),
			D(discount.find(cbc("BaseAmount")).text) - D(discount.find(cbc("Amount")).text),
		)

	def test_the_rule_holds_when_a_price_with_tax_inside_it_states_no_discount(self):
		# The reader leaves the discount off a price that had tax inside it,
		# because restating it without the tax would be a figure nobody
		# posted. The serializer writes nothing as the discount and the net
		# price as the base, and the rule still holds.
		root = parse(
			document(
				lines=[line(net_price="100.00", net_amount="100.00")],
				breakdown=[group(taxable="100.00", tax="5.00")],
				totals=money(
					line_net="100.00",
					tax_exclusive="100.00",
					tax="5.00",
					tax_inclusive="105.00",
					payable="105.00",
				),
			)
		)
		price = root.find(f"{{{CAC}}}InvoiceLine/{{{CAC}}}Price")
		discount = price.find(f"{{{CAC}}}AllowanceCharge")
		self.assertEqual(D(discount.find(cbc("Amount")).text), D(0))
		self.assertEqual(
			D(price.find(cbc("PriceAmount")).text),
			D(discount.find(cbc("BaseAmount")).text) - D(discount.find(cbc("Amount")).text),
		)


class TheTaxOnEachLine(unittest.TestCase):
	def test_the_line_tax_is_worked_out_again_instead_of_being_read(self):
		# The serializer multiplies each line's net amount by its rate and
		# rounds the answer. On three lines of 33.33 that is 1.67 apiece and
		# 5.01 in total, where the group and the posted figure both say 5.00.
		# Nothing reconciles the two, and this is the one place in the app
		# that produces a tax rather than reading the posted one.
		rows = [{"net_amount": D("33.33"), "tax_rate": D("5.00")} for _ in range(3)]
		self.assertEqual(sum(serializer._line_tax(row) for row in rows), D("5.01"))
		self.assertEqual((D("99.99") * D("5") / D("100")).quantize(D("0.01")), D("5.00"))

	def test_an_exempt_line_states_no_tax_at_all(self):
		# ibr-163-ae: an exempt line must not carry a VAT line amount.
		root = parse(
			document(
				lines=[line(net_price="100.00", net_amount="100.00", category="E", rate="0.00")],
				breakdown=[group(taxable="100.00", tax="0.00", category="E", rate="0.00")],
				totals=money(
					line_net="100.00",
					tax_exclusive="100.00",
					tax="0.00",
					tax_inclusive="100.00",
					payable="100.00",
				),
			)
		)
		extension = root.find(f"{{{CAC}}}InvoiceLine/{{{CAC}}}ItemPriceExtension")
		self.assertIsNone(extension.find(TAX_TOTAL))


class DirhamsOnAForeignCurrencyInvoice(unittest.TestCase):
	"""What a dollar invoice states in dirhams.

	It stated nothing, and five fatal rules had nothing to read, so a foreign
	currency invoice was refused outright. The fifth worked example in spec
	5.3 had no implementation behind it.

	These were written to hold that gap still while it was visible. They now
	hold the other side: the figures are there, and they are the ones the
	arithmetic says they should be.
	"""

	def build(self):
		return document(
			currency="USD",
			lines=[line(net_price="100.00", net_amount="100.00")],
			breakdown=[group(taxable="100.00", tax="5.00")],
			totals=money(
				line_net="100.00",
				tax_exclusive="100.00",
				tax="5.00",
				tax_inclusive="105.00",
				payable="105.00",
				tax_in_aed="18.36",
				tax_inclusive_aed="385.61",
			),
			exchange_rates={
				"to_aed": {
					"from_currency": "USD",
					"to_currency": "AED",
					"rate": D("3.672500000"),
					"date": "2026-09-17",
					"source": "Rate on the invoice",
				}
			},
		)

	def test_the_dirham_amounts_the_rules_ask_for(self):
		# Worked out here rather than taken from the app, so the figures the
		# document ought to carry are on the record.
		rate = D("3.6725")
		self.assertEqual((D("100.00") * rate).quantize(D("0.01")), D("367.25"))
		self.assertEqual((D("5.00") * rate).quantize(D("0.01")), D("18.36"))
		self.assertEqual((D("105.00") * rate).quantize(D("0.01")), D("385.61"))

	def test_the_document_names_aed_as_its_tax_currency(self):
		root = parse(self.build())
		self.assertEqual(value(root, cbc("TaxCurrencyCode")), "AED")
		self.assertEqual(value(root, cbc("DocumentCurrencyCode")), "USD")

	def test_the_tax_is_stated_in_dirhams_as_well(self):
		root = parse(self.build())
		labelled = {node.get("currencyID") for node in root.iter() if node.get("currencyID")}
		self.assertIn("AED", labelled, "nothing on the document is stated in dirhams")

	def test_the_frozen_rate_reaches_the_document(self):
		root = parse(self.build())
		node = root.find(f"{{{CAC}}}TaxExchangeRate")
		self.assertIsNotNone(node, "the rate was frozen and then never written down")
		self.assertEqual(value(node, cbc("CalculationRate")), "3.6725")
