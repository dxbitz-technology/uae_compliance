"""The serializer, judged by the official rules rather than by us.

Almost every check here builds an invoice, writes it out, and runs the real
published schema and both rule layers over the result. That is the only
measure that matters: not whether the XML looks right to us, but whether the
rules accept it.
"""

from __future__ import annotations

import unittest
from decimal import Decimal as D

from uae_compliance.domain.canonical import INVOICE, SCENARIO_FLAGS
from uae_compliance.domain.encoding import NOT_APPLICABLE
from uae_compliance.domain.schema import check as check_canonical
from uae_compliance.validation.serializer import (
	SerializerError,
	scenario_string,
	to_xml,
)
from uae_compliance.validation.validator import validate


def party(name, tin, trn, subdivision="DXB"):
	return {
		"legal_name": name,
		"country": "AE",
		"participant": {"scheme": "0235", "value": tin},
		"tax_registration": {"scheme": "VAT", "value": trn},
		"legal_registration": {
			"scheme": "TL",
			"value": "112345678900003",
			"authority": "Trade License issuing Authority",
		},
		"address": {"line1": "Street", "city": "Dubai", "subdivision": subdivision, "country": "AE"},
	}


def an_invoice(type_code="380", **document):
	"""Two units of a service at 90, VAT at 5 per cent, totalling 189."""
	meta = {
		"number": "SINV-0001",
		"uuid": "4b6000ca-0128-4bdc-99a6-406f2909247f",
		"type_code": type_code,
		"issue_date": "2026-09-17",
		"currency": "AED",
	}
	meta.update(document)
	return {
		"provenance": {
			"schema_version": "1",
			"extraction_version": "1",
			"extracted_at": "2026-09-17T09:00:00Z",
			"source_doctype": "Sales Invoice",
			"source_name": "SINV-0001",
			"company": "Dxbitz",
			"source_fingerprint": "src-1",
			"master_fingerprint": "mst-1",
		},
		"context": {
			"jurisdiction": "AE",
			"policy_revision": "1",
			"in_scope": True,
			"environment": "Simulation",
			"standards_version": "pint-ae-1.0.4",
			"customization_id": "urn:peppol:pint:billing-1@ae-1",
			"profile_id": "urn:peppol:bis:billing",
		},
		"document": meta,
		"parties": {
			"seller": party("Dxbitz Technology FZC LLC", "1357902468", "198765432102003"),
			"buyer": party("A Client LLC", "1345678901", "134567890123003", "AUH"),
		},
		"payment": {
			"means_code": "30",
			"account": {"identifier": "AE070331234567890123456", "name": "Dxbitz"},
		},
		"lines": [
			{
				"id": "1",
				"source_row": "row-abc",
				"name": "Consulting",
				"item_type": "Services",
				"classifications": [{"scheme": "SAC", "value": "998311"}],
				"quantity": D("2"),
				"uom_code": "H87",
				"net_price": D("90.00"),
				"net_amount": D("180.00"),
				"tax_category": "S",
				"tax_rate": D("5"),
			}
		],
		"tax_breakdown": [
			{
				"category": "S",
				"rate": D("5"),
				"taxable_amount": D("180.00"),
				"tax_amount": D("9.00"),
			}
		],
		"totals": {
			"line_net": D("180.00"),
			"allowances": D("0.00"),
			"charges": D("0.00"),
			"tax_exclusive": D("180.00"),
			"tax": D("9.00"),
			"tax_inclusive": D("189.00"),
			"payable": D("189.00"),
		},
		"scenario": dict.fromkeys(SCENARIO_FLAGS, False),
	}


def a_credit_note(**references):
	note = an_invoice("381")
	note["references"] = references or {
		"preceding": [{"number": "SINV-0001", "issue_date": "2026-08-01"}],
		"credit_reason_code": "DL8.61.1.E",
		"credit_reason": "Goods returned",
	}
	return note


class Passing(unittest.TestCase):
	"""These are the ones that matter. The official rules are the judge."""

	def assert_accepted(self, document):
		report = validate(to_xml(document))
		self.assertEqual(
			[(f.rule_id, f.message[:80]) for f in report.findings],
			[],
			"the official rules rejected it",
		)
		for outcome in report.stages:
			self.assertEqual(outcome.state.value, "Passed", outcome.stage.value)

	def test_an_invoice_we_build_is_accepted_by_the_official_rules(self):
		self.assert_accepted(an_invoice(due_date="2026-10-17"))

	def test_a_credit_note_we_build_is_accepted(self):
		self.assert_accepted(a_credit_note())

	def test_a_volume_discount_credit_note_carries_no_preceding_reference(self):
		# The published exception: a volume discount credit note states its
		# reason and deliberately has no preceding invoice, and the rules check
		# both halves of that together.
		self.assert_accepted(a_credit_note(credit_reason_code="VD", credit_reason="Volume discount"))

	def test_a_goods_line_classified_under_the_goods_scheme_is_accepted(self):
		document = an_invoice(due_date="2026-10-17")
		document["lines"][0]["item_type"] = "Goods"
		document["lines"][0]["classifications"] = [{"scheme": "HS", "value": "88098432324"}]
		self.assert_accepted(document)

	def test_a_line_that_is_both_goods_and_services_carries_both_schemes(self):
		document = an_invoice(due_date="2026-10-17")
		document["lines"][0]["item_type"] = "Both"
		document["lines"][0]["classifications"] = [
			{"scheme": "HS", "value": "88098432324"},
			{"scheme": "SAC", "value": "998311"},
		]
		self.assert_accepted(document)

	def test_the_invoice_we_build_is_also_a_valid_canonical_document(self):
		# The two have to agree, or the serializer is writing from something
		# the model would not accept in the first place.
		self.assertEqual(check_canonical(an_invoice(due_date="2026-10-17"), INVOICE), [])


class TheSameInputGivesTheSameBytes(unittest.TestCase):
	def test_writing_it_twice_produces_identical_bytes(self):
		document = an_invoice(due_date="2026-10-17")
		self.assertEqual(to_xml(document), to_xml(document))

	def test_a_real_change_changes_the_bytes(self):
		one = to_xml(an_invoice(due_date="2026-10-17"))
		other = an_invoice(due_date="2026-10-17")
		other["totals"]["payable"] = D("189.01")
		self.assertNotEqual(one, to_xml(other))


class TheScenarioString(unittest.TestCase):
	def test_nothing_set_is_eight_zeros(self):
		self.assertEqual(scenario_string(dict.fromkeys(SCENARIO_FLAGS, False)), "00000000")

	def test_each_flag_lands_in_its_published_position(self):
		for index, flag in enumerate(SCENARIO_FLAGS):
			expected = "0" * index + "1" + "0" * (7 - index)
			self.assertEqual(scenario_string({flag: True}), expected, flag)

	def test_the_margin_scheme_is_the_third_position(self):
		self.assertEqual(scenario_string({"margin_scheme": True}), "00100000")

	def test_several_at_once(self):
		self.assertEqual(
			scenario_string({"free_zone": True, "continuous_supply": True, "ecommerce": True}),
			"10001010",
		)


class WhatIsLeftOut(unittest.TestCase):
	def test_a_field_marked_not_applicable_is_not_written_at_all(self):
		document = an_invoice()
		document["document"]["due_date"] = NOT_APPLICABLE
		self.assertNotIn(b"DueDate", to_xml(document))

	def test_an_absent_field_is_not_written_either(self):
		document = an_invoice()
		self.assertNotIn("buyer_reference", document["document"])
		self.assertNotIn(b"BuyerReference", to_xml(document))

	def test_a_credit_note_carries_no_due_date(self):
		self.assertNotIn(b"DueDate", to_xml(a_credit_note()))


class WhatItRefuses(unittest.TestCase):
	def test_something_that_is_not_a_document(self):
		with self.assertRaises(SerializerError):
			to_xml(["not", "a", "document"])

	def test_a_document_with_no_document_section(self):
		with self.assertRaises(SerializerError):
			to_xml({"lines": []})

	def test_a_document_with_no_currency(self):
		document = an_invoice()
		del document["document"]["currency"]
		with self.assertRaises(SerializerError):
			to_xml(document)


class TheShapeItWrites(unittest.TestCase):
	def test_a_credit_note_uses_the_credit_note_elements(self):
		xml = to_xml(a_credit_note())
		self.assertIn(b"<CreditNote", xml)
		self.assertIn(b"CreditNoteTypeCode", xml)
		self.assertIn(b"CreditedQuantity", xml)
		self.assertNotIn(b"InvoicedQuantity", xml)

	def test_an_invoice_uses_the_invoice_elements(self):
		xml = to_xml(an_invoice(due_date="2026-10-17"))
		self.assertIn(b"<Invoice", xml)
		self.assertIn(b"InvoiceTypeCode", xml)
		self.assertIn(b"InvoicedQuantity", xml)

	def test_the_authority_that_issued_a_registration_is_written(self):
		xml = to_xml(an_invoice(due_date="2026-10-17"))
		self.assertIn(b'schemeAgencyName="Trade License issuing Authority"', xml)

	def test_amounts_are_written_with_their_currency(self):
		xml = to_xml(an_invoice(due_date="2026-10-17"))
		self.assertIn(b'currencyID="AED">189.00<', xml)


if __name__ == "__main__":
	unittest.main(verbosity=2)
