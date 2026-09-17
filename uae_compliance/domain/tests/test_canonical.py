"""Checks on the canonical invoice.

A small hand-built invoice stands in for a real one. The checks are about
the shape holding: what must be there, what must not, and that the business
hash ignores exactly the fields that move on their own and nothing else.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from uae_compliance.domain.canonical import (
	CANONICAL_VERSION,
	DOCUMENT_TYPES,
	INVOICE,
	SCENARIO_FLAGS,
	TAX_CATEGORIES,
	VOLATILE_PATHS,
)
from uae_compliance.domain.encoding import business_hash, canonical_bytes
from uae_compliance.domain.schema import (
	CODE_MISSING,
	CODE_UNKNOWN,
	CODE_VALUE,
	NOT_APPLICABLE,
	check,
)


def party(name, country="AE"):
	return {
		"legal_name": name,
		"country": country,
		"address": {"city": "Dubai", "country": country},
	}


def an_invoice():
	"""Two units at 100, a line discount of 20, VAT at 5 per cent."""
	return {
		"provenance": {
			"schema_version": str(CANONICAL_VERSION),
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
		"document": {
			"number": "SINV-0001",
			"type_code": "380",
			"issue_date": "2026-09-17",
			"currency": "AED",
		},
		"parties": {"seller": party("Dxbitz Technology"), "buyer": party("A Client")},
		"lines": [
			{
				"id": "1",
				"source_row": "row-abc",
				"name": "Consulting",
				"quantity": Decimal("2"),
				"uom_code": "H87",
				"net_price": Decimal("90"),
				"net_amount": Decimal("180.00"),
				"tax_category": "S",
				"tax_rate": Decimal("5"),
			}
		],
		"tax_breakdown": [
			{
				"category": "S",
				"rate": Decimal("5"),
				"taxable_amount": Decimal("180.00"),
				"tax_amount": Decimal("9.00"),
			}
		],
		"totals": {
			"line_net": Decimal("180.00"),
			"allowances": Decimal("0.00"),
			"charges": Decimal("0.00"),
			"tax_exclusive": Decimal("180.00"),
			"tax": Decimal("9.00"),
			"tax_inclusive": Decimal("189.00"),
			"payable": Decimal("189.00"),
		},
		"scenario": dict.fromkeys(SCENARIO_FLAGS, False),
	}


def codes(findings):
	return sorted(f.code for f in findings)


def paths(findings):
	return sorted(f.path for f in findings)


class TheExampleInvoice(unittest.TestCase):
	def test_it_passes(self):
		self.assertEqual(check(an_invoice(), INVOICE), [])

	def test_it_encodes(self):
		self.assertIn(b'"number":"SINV-0001"', canonical_bytes(an_invoice()))

	def test_its_money_adds_up_the_way_the_spec_example_says(self):
		invoice = an_invoice()
		totals = invoice["totals"]
		self.assertEqual(totals["tax_exclusive"], Decimal("180.00"))
		self.assertEqual(totals["tax"], Decimal("9.00"))
		self.assertEqual(totals["tax_inclusive"], Decimal("189.00"))


class WhatMustBeThere(unittest.TestCase):
	def test_every_top_level_group_that_is_required(self):
		found = check({}, INVOICE)
		self.assertEqual(
			paths(found),
			[
				"context",
				"document",
				"lines",
				"parties",
				"provenance",
				"scenario",
				"tax_breakdown",
				"totals",
			],
		)
		self.assertEqual(set(codes(found)), {CODE_MISSING})

	def test_a_line_needs_its_row_so_a_finding_can_point_back(self):
		invoice = an_invoice()
		del invoice["lines"][0]["source_row"]
		self.assertEqual(paths(check(invoice, INVOICE)), ["lines[0].source_row"])

	def test_a_party_needs_a_name_and_a_country(self):
		invoice = an_invoice()
		del invoice["parties"]["buyer"]["legal_name"]
		del invoice["parties"]["buyer"]["country"]
		self.assertEqual(
			paths(check(invoice, INVOICE)),
			["parties.buyer.country", "parties.buyer.legal_name"],
		)

	def test_an_exchange_rate_must_say_where_it_came_from(self):
		invoice = an_invoice()
		invoice["exchange_rates"] = {
			"to_aed": {
				"from_currency": "USD",
				"to_currency": "AED",
				"rate": Decimal("3.6725"),
				"date": "2026-09-17",
			}
		}
		self.assertEqual(paths(check(invoice, INVOICE)), ["exchange_rates.to_aed.source"])

	def test_every_scenario_flag_must_be_stated(self):
		invoice = an_invoice()
		del invoice["scenario"]["export"]
		found = check(invoice, INVOICE)
		self.assertEqual(paths(found), ["scenario.export"])

	def test_there_are_eight_scenario_flags(self):
		self.assertEqual(len(SCENARIO_FLAGS), 8)
		self.assertEqual(len(set(SCENARIO_FLAGS)), 8)


class WhatIsRefused(unittest.TestCase):
	def test_an_unknown_field_anywhere(self):
		invoice = an_invoice()
		invoice["document"]["qr_code"] = "x"
		self.assertEqual(codes(check(invoice, INVOICE)), [CODE_UNKNOWN])

	def test_a_document_type_outside_the_four(self):
		invoice = an_invoice()
		invoice["document"]["type_code"] = "388"
		self.assertEqual(codes(check(invoice, INVOICE)), [CODE_VALUE])

	def test_the_four_document_types_are_the_verified_ones(self):
		self.assertEqual(set(DOCUMENT_TYPES), {"380", "480", "381", "81"})

	def test_a_tax_category_outside_the_list(self):
		invoice = an_invoice()
		invoice["lines"][0]["tax_category"] = "M"
		self.assertEqual(codes(check(invoice, INVOICE)), [CODE_VALUE])

	def test_margin_is_the_letter_n_not_the_letter_m(self):
		self.assertIn("N", TAX_CATEGORIES)
		self.assertNotIn("M", TAX_CATEGORIES)

	def test_an_unknown_environment(self):
		invoice = an_invoice()
		invoice["context"]["environment"] = "Live"
		self.assertEqual(codes(check(invoice, INVOICE)), [CODE_VALUE])

	def test_a_negative_quantity_on_a_price_basis(self):
		invoice = an_invoice()
		invoice["lines"][0]["base_quantity"] = Decimal("-1")
		self.assertEqual(codes(check(invoice, INVOICE)), [CODE_VALUE])

	def test_a_negative_exchange_rate(self):
		invoice = an_invoice()
		invoice["exchange_rates"] = {
			"to_aed": {
				"from_currency": "USD",
				"to_currency": "AED",
				"rate": Decimal("-3.6725"),
				"date": "2026-09-17",
				"source": "Currency Exchange",
			}
		}
		self.assertEqual(codes(check(invoice, INVOICE)), [CODE_VALUE])


class ThingsThatMayNotApply(unittest.TestCase):
	def test_a_due_date_may_be_marked_as_not_applicable(self):
		invoice = an_invoice()
		invoice["document"]["due_date"] = NOT_APPLICABLE
		self.assertEqual(check(invoice, INVOICE), [])

	def test_a_tax_currency_may_be_marked_as_not_applicable(self):
		invoice = an_invoice()
		invoice["document"]["tax_currency"] = NOT_APPLICABLE
		self.assertEqual(check(invoice, INVOICE), [])

	def test_an_issue_date_may_not_be(self):
		invoice = an_invoice()
		invoice["document"]["issue_date"] = NOT_APPLICABLE
		self.assertTrue(check(invoice, INVOICE))


class CreditNotesAndScenarios(unittest.TestCase):
	def test_a_credit_note_can_answer_more_than_one_invoice(self):
		invoice = an_invoice()
		invoice["document"]["type_code"] = "381"
		invoice["references"] = {
			"credit_reason": "Volume discount",
			"preceding": [
				{"number": "SINV-0001", "issue_date": "2026-08-01"},
				{"number": "SINV-0002", "issue_date": "2026-08-15"},
			],
		}
		self.assertEqual(check(invoice, INVOICE), [])

	def test_a_free_zone_supply_can_name_a_beneficiary(self):
		invoice = an_invoice()
		invoice["scenario"]["free_zone"] = True
		invoice["parties"]["beneficiary"] = party("The Beneficiary")
		self.assertEqual(check(invoice, INVOICE), [])

	def test_an_agent_billing_can_name_a_principal(self):
		invoice = an_invoice()
		invoice["scenario"]["agent_billing"] = True
		invoice["parties"]["principal"] = party("The Principal")
		self.assertEqual(check(invoice, INVOICE), [])

	def test_a_foreign_buyer_keeps_both_registrations(self):
		invoice = an_invoice()
		buyer = invoice["parties"]["buyer"]
		buyer["country"] = "GB"
		buyer["address"]["country"] = "GB"
		buyer["tax_registration"] = {"scheme": "GB:VAT", "value": "GB123456789"}
		buyer["extra_tax_registration"] = {"scheme": "AE:TRN", "value": "100000000000003"}
		self.assertEqual(check(invoice, INVOICE), [])

	def test_a_buyer_with_no_network_address_is_still_a_valid_document(self):
		invoice = an_invoice()
		self.assertNotIn("participant", invoice["parties"]["buyer"])
		self.assertEqual(check(invoice, INVOICE), [])


class TheBusinessHash(unittest.TestCase):
	def test_every_volatile_path_names_a_required_field_in_the_model(self):
		# The exclusion list is strict: a path matching nothing raises. So each
		# volatile field has to be required, or the hash would break on the
		# first invoice that happened to leave it out.
		for path in VOLATILE_PATHS:
			spec = INVOICE.known()
			field = None
			for part in path.split("."):
				self.assertIn(part, spec, f"{path} does not exist in the model")
				field = spec[part]
				spec = field.fields or {}
			self.assertTrue(field.required, f"{path} is excluded from the hash but is not required")

	def test_a_volatile_path_that_stopped_existing_would_be_caught(self):
		with self.assertRaises(Exception):
			business_hash(an_invoice(), ["provenance.renamed_away"])

	def test_re_extracting_the_same_invoice_does_not_change_it(self):
		first = an_invoice()
		second = an_invoice()
		second["provenance"]["extracted_at"] = "2026-09-18T17:45:12Z"
		self.assertNotEqual(canonical_bytes(first), canonical_bytes(second))
		self.assertEqual(
			business_hash(first, VOLATILE_PATHS),
			business_hash(second, VOLATILE_PATHS),
		)

	def test_a_change_to_the_invoice_itself_still_changes_it(self):
		first = an_invoice()
		second = an_invoice()
		second["totals"]["payable"] = Decimal("189.01")
		self.assertNotEqual(
			business_hash(first, VOLATILE_PATHS),
			business_hash(second, VOLATILE_PATHS),
		)

	def test_the_source_fingerprint_is_part_of_the_business_hash(self):
		# It says which source the document was built from, so it belongs to
		# what was agreed rather than to the noise around it.
		first = an_invoice()
		second = an_invoice()
		second["provenance"]["source_fingerprint"] = "src-2"
		self.assertNotEqual(
			business_hash(first, VOLATILE_PATHS),
			business_hash(second, VOLATILE_PATHS),
		)


if __name__ == "__main__":
	unittest.main(verbosity=2)
