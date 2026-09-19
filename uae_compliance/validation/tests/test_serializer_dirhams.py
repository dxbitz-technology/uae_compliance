"""An invoice in another currency has to say what it is in dirhams.

Five fatal rules read these, and none of them had anything to read. A
foreign currency invoice was rejected outright by the official rules, which
means the fifth worked example in spec 5.3 had no implementation behind it.

What the rules want, each checked below: the rate, with the document's own
currency as the source and dirhams as the target; the tax again in dirhams
as its own total; and the dirham total including tax, written as text.
"""

import unittest
from decimal import Decimal

from lxml import etree

from uae_compliance.validation.serializer import to_xml

CBC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"
CAC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"


def an_invoice(currency: str, **extra) -> dict:
	"""The smallest document the writer will accept, in the given currency."""
	totals = {
		"line_net": Decimal("300.00"),
		"allowances": Decimal("0.00"),
		"charges": Decimal("0.00"),
		"tax_exclusive": Decimal("300.00"),
		"tax": Decimal("15.00"),
		"tax_inclusive": Decimal("315.00"),
		"payable": Decimal("315.00"),
	}
	totals.update(extra.pop("totals", {}))
	document = {
		"provenance": {
			"schema_version": "1",
			"extraction_version": "1",
			"extracted_at": "2026-09-19T00:00:00Z",
			"source_doctype": "Sales Invoice",
			"source_name": "SINV-1",
			"company": "Test Co",
			"source_fingerprint": "a" * 64,
			"master_fingerprint": "b" * 64,
		},
		"context": {
			"jurisdiction": "AE",
			"policy_revision": "1",
			"in_scope": True,
			"environment": "Simulation",
			"standards_version": "1.0.4",
			"customization_id": "urn:peppol:pint:billing-1@ae-1",
			"profile_id": "urn:peppol:bis:billing",
		},
		"document": {
			"number": "SINV-1",
			"uuid": "11111111-1111-1111-1111-111111111111",
			"type_code": "380",
			"issue_date": "2026-09-19",
			"currency": currency,
		},
		"parties": {
			"seller": {"legal_name": "Seller", "country": "AE"},
			"buyer": {"legal_name": "Buyer", "country": "AE"},
		},
		"lines": [
			{
				"id": "1",
				"source_row": "r1",
				"name": "Thing",
				"quantity": Decimal("3.000"),
				"uom_code": "C62",
				"net_price": Decimal("100.00"),
				"net_amount": Decimal("300.00"),
				"tax_category": "S",
				"tax_rate": Decimal("5.00"),
			}
		],
		"tax_breakdown": [
			{
				"category": "S",
				"rate": Decimal("5.00"),
				"taxable_amount": Decimal("300.00"),
				"tax_amount": Decimal("15.00"),
			}
		],
		"totals": totals,
		"scenario": dict.fromkeys(
			(
				"free_zone",
				"deemed_supply",
				"margin_scheme",
				"summary",
				"continuous_supply",
				"agent_billing",
				"ecommerce",
				"export",
			),
			False,
		),
	}
	document.update(extra)
	return document


def a_foreign_invoice(rate: str = "3.6725") -> dict:
	return an_invoice(
		"USD",
		totals={"tax_in_aed": Decimal("55.09"), "tax_inclusive_aed": Decimal("1156.84")},
		exchange_rates={
			"to_aed": {
				"from_currency": "USD",
				"to_currency": "AED",
				"rate": Decimal(rate),
				"date": "2026-09-19",
				"source": "Rate on the invoice",
			}
		},
	)


def written(document: dict):
	return etree.fromstring(to_xml(document))


class AnInvoiceInAnotherCurrency(unittest.TestCase):
	def test_it_carries_the_rate_to_dirhams(self):
		root = written(a_foreign_invoice())
		node = root.find(f"{CAC}TaxExchangeRate")
		self.assertIsNotNone(node, "no rate, and three rules read it")
		self.assertEqual(node.find(f"{CBC}SourceCurrencyCode").text, "USD")
		self.assertEqual(node.find(f"{CBC}TargetCurrencyCode").text, "AED")
		self.assertEqual(node.find(f"{CBC}CalculationRate").text, "3.6725")

	def test_the_rate_is_never_written_longer_than_the_rules_allow(self):
		# Our own scale is wider on purpose, as a safety net against a value
		# arriving from floating point arithmetic. Six places is what the
		# document may carry.
		root = written(a_foreign_invoice("3.672512345678"))
		text = root.find(f"{CAC}TaxExchangeRate/{CBC}CalculationRate").text
		self.assertLessEqual(len(text.split(".")[1]), 6, f"the rate was written as {text}")

	def test_it_states_the_tax_again_in_dirhams(self):
		root = written(a_foreign_invoice())
		amounts = [
			node.text
			for node in root.findall(f"{CAC}TaxTotal/{CBC}TaxAmount")
			if node.get("currencyID") == "AED"
		]
		self.assertEqual(amounts, ["55.09"])

	def test_it_states_the_dirham_total_including_tax(self):
		# As words rather than as an amount, which is how the published
		# example writes it and what the rule looks for.
		root = written(a_foreign_invoice())
		for node in root.findall(f"{CAC}AdditionalDocumentReference"):
			if node.find(f"{CBC}DocumentTypeCode").text == "aedtotal-incl-vat":
				self.assertEqual(node.find(f"{CBC}ID").text, "AED")
				self.assertEqual(node.find(f"{CBC}DocumentDescription").text, "AED 1156.84")
				return
		self.fail("the dirham total is not on the document")

	def test_nothing_of_the_sort_on_an_invoice_already_in_dirhams(self):
		# Saying the same figure twice in the same currency tells a reader
		# nothing and gives the rules something extra to disagree with.
		root = written(an_invoice("AED"))
		self.assertIsNone(root.find(f"{CAC}TaxExchangeRate"))
		self.assertEqual(
			[
				node
				for node in root.findall(f"{CAC}TaxTotal/{CBC}TaxAmount")
				if node.get("currencyID") == "AED" and node.getparent().find(f"{CAC}TaxSubtotal") is None
			],
			[],
		)

	def test_a_foreign_invoice_with_no_rate_writes_no_rate(self):
		# Where nothing evidenced the rate, nothing is invented. The document
		# is then incomplete and the rules say so, which is the right answer.
		document = a_foreign_invoice()
		document.pop("exchange_rates")
		root = written(document)
		self.assertIsNone(root.find(f"{CAC}TaxExchangeRate"))
