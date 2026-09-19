"""What each kind of supply has to carry. Case A23.

The table these check was read out of the pinned rules rather than written
from scratch, so the thing worth testing is that it still says what those
rules say. Every requirement cites a rule id, and the rule ids are checked
here against the list the packet record took them from.

The other half is that an unsupported scenario is refused rather than
approximated, which is invariant I11 and the whole reason the table has a
supported column at all.
"""

import unittest
from decimal import Decimal as D

from uae_compliance.domain.scenarios import (
	CODE_CONTRADICTS,
	CODE_MISSING,
	CODE_UNSUPPORTED,
	POSITIONS,
	SCENARIOS,
	capability_rows,
	check,
)

# Read out of the pinned package: which rule demands what, per position.
# If the table drifts from this, one of the two is wrong and it has to be
# settled against the publication rather than against whichever is newer.
RULES_BY_SCENARIO = {
	"free_zone": {"ibr-007-ae"},
	"deemed_supply": {"ibr-191-ae"},
	"margin_scheme": set(),
	"summary": {"ibr-138-ae"},
	"continuous_supply": set(),
	"agent_billing": {"ibr-137-ae", "ibr-177-ae"},
	"ecommerce": {"ibr-142-ae"},
	"export": {"ibr-135-ae", "ibr-152-ae"},
}


def a_document(**scenario) -> dict:
	"""The smallest shape the scenario checks read."""
	return {
		"scenario": {**dict.fromkeys(POSITIONS, False), **scenario},
		"parties": {
			"seller": {"legal_name": "Seller", "tax_registration": {"scheme": "VAT", "value": "1"}},
			"buyer": {"legal_name": "Buyer", "tax_registration": {"scheme": "VAT", "value": "2"}},
		},
		"document": {"number": "SINV-1"},
		"delivery": {},
		"payment": {},
	}


def codes(findings) -> list[str]:
	return sorted(finding.code for finding in findings)


def rules(findings) -> set[str]:
	return {finding.rule_id for finding in findings if finding.rule_id}


class TheTableMatchesThePublishedRules(unittest.TestCase):
	def test_every_position_has_a_row(self):
		self.assertEqual(set(SCENARIOS), set(POSITIONS))

	def test_there_are_eight_of_them_in_the_published_order(self):
		# The serializer builds the eight character string from this order
		# and nothing else may decide it.
		self.assertEqual(len(POSITIONS), 8)
		self.assertEqual(POSITIONS[0], "free_zone")
		self.assertEqual(POSITIONS[-1], "export")

	def test_each_scenario_cites_the_rules_it_was_read_from(self):
		for flag, expected in RULES_BY_SCENARIO.items():
			found = {requirement.rule for requirement in SCENARIOS[flag].requires}
			self.assertEqual(found, expected, f"{flag} cites {found} and should cite {expected}")

	def test_every_requirement_names_a_field_and_a_repair(self):
		# A finding with no field is one somebody has to go hunting for.
		for item in SCENARIOS.values():
			for requirement in item.requires:
				self.assertTrue(requirement.path, f"{item.flag} has a requirement with no field")
				self.assertTrue(requirement.repair, f"{item.flag} has a requirement with no repair")


class AnOrdinaryInvoice(unittest.TestCase):
	def test_nothing_ticked_asks_for_nothing(self):
		self.assertEqual(check(a_document()), [])


class WhatEachKindOfSupplyNeeds(unittest.TestCase):
	def test_a_free_zone_supply_wants_the_beneficiary(self):
		found = check(a_document(free_zone=True))
		self.assertEqual(codes(found), [CODE_MISSING])
		self.assertEqual(rules(found), {"ibr-007-ae"})

	def test_naming_the_beneficiary_satisfies_it(self):
		document = a_document(free_zone=True)
		document["parties"]["beneficiary"] = {"participant": {"scheme": "0235", "value": "1"}}
		self.assertEqual(check(document), [])

	def test_a_beneficiary_with_a_name_and_no_identifier_is_not_enough(self):
		# The rule asks for the identifier. A name satisfies nobody.
		document = a_document(free_zone=True)
		document["parties"]["beneficiary"] = {"legal_name": "Jebel Ali Trading FZE"}
		self.assertEqual(codes(check(document)), [CODE_MISSING])

	def test_a_summary_invoice_wants_the_period(self):
		found = check(a_document(summary=True))
		self.assertEqual(rules(found), {"ibr-138-ae"})

	def test_giving_it_the_period_satisfies_it(self):
		document = a_document(summary=True)
		document["document"]["period"] = {"start_date": "2026-09-01", "end_date": "2026-09-30"}
		self.assertEqual(check(document), [])

	def test_an_export_wants_the_delivery_and_the_buyer(self):
		document = a_document(export=True)
		document["parties"]["buyer"] = {"legal_name": "Buyer"}
		self.assertEqual(rules(check(document)), {"ibr-152-ae", "ibr-135-ae"})

	def test_an_agent_wants_the_principal(self):
		self.assertEqual(rules(check(a_document(agent_billing=True))), {"ibr-137-ae"})

	def test_an_agent_cannot_be_the_principal(self):
		# Billing on your own behalf is not agency, and ibr-176-ae says so.
		document = a_document(agent_billing=True)
		document["parties"]["principal"] = {"participant": {"scheme": "0235", "value": "1"}}
		found = check(document)
		self.assertIn(CODE_CONTRADICTS, codes(found))
		self.assertIn("ibr-176-ae", rules(found))

	def test_a_continuous_supply_asks_for_nothing_extra(self):
		self.assertEqual(check(a_document(continuous_supply=True)), [])


class WhatIsNotSupported(unittest.TestCase):
	def test_the_margin_scheme_is_refused_rather_than_approximated(self):
		# Invariant I11. An unsupported case fails in Live and is never
		# guessed at.
		found = check(a_document(margin_scheme=True))
		self.assertEqual(codes(found), [CODE_UNSUPPORTED])
		self.assertTrue(found[0].blocking)

	def test_it_says_why_it_is_not_supported(self):
		found = check(a_document(margin_scheme=True))
		self.assertTrue(found[0].params.get("why"), "an unsupported scenario has to say why")

	def test_an_unsupported_one_cannot_be_satisfied_by_filling_fields_in(self):
		# There is no combination of inputs that turns it on, which is the
		# point of the supported column.
		document = a_document(margin_scheme=True)
		document["parties"]["beneficiary"] = {"participant": {"scheme": "0235", "value": "1"}}
		document["document"]["period"] = {"start_date": "2026-09-01", "end_date": "2026-09-30"}
		self.assertEqual(codes(check(document)), [CODE_UNSUPPORTED])


class TwoAtOnce(unittest.TestCase):
	def test_both_are_asked_for(self):
		found = check(a_document(free_zone=True, summary=True))
		self.assertEqual(rules(found), {"ibr-007-ae", "ibr-138-ae"})

	def test_satisfying_one_leaves_the_other(self):
		document = a_document(free_zone=True, summary=True)
		document["parties"]["beneficiary"] = {"participant": {"scheme": "0235", "value": "1"}}
		self.assertEqual(rules(check(document)), {"ibr-138-ae"})


class WhatIsPublished(unittest.TestCase):
	def test_every_row_says_whether_it_is_supported(self):
		rows = capability_rows()
		self.assertEqual(len(rows), len(POSITIONS))
		for row in rows:
			self.assertIn("supported", row)
			self.assertIsInstance(row["supported"], bool)

	def test_the_published_rules_are_the_ones_the_table_cites(self):
		# What a customer is told and what the code does have to be the
		# same thing.
		for row in capability_rows():
			self.assertEqual(set(row["rules"]), RULES_BY_SCENARIO[row["flag"]])
