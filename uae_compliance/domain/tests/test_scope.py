"""Company modes and the document type matrix.

The type rules are quoted from the pinned publication in the module, so these
checks are about the app applying them, not about whether they are right.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from uae_compliance.domain.findings import Severity, Stage
from uae_compliance.domain.scope import (
	CODE_COMMERCIAL_CATEGORY,
	CODE_COMMERCIAL_FLAG,
	CODE_SELLER_NOT_REGISTERED,
	CODE_TAX_CATEGORY,
	CODE_TYPE_DIRECTION,
	COMMERCIAL_CREDIT_NOTE,
	COMMERCIAL_INVOICE,
	TAX_CREDIT_NOTE,
	TAX_INVOICE,
	Enforcement,
	Mode,
	blocks_submission,
	categories_on,
	check,
	check_document_type,
	enforcement_for,
	may_create_intent,
	mode_of,
	permitted_types,
)


def invoice(type_code=TAX_INVOICE, categories=("S",), **extra):
	document = {
		"document": {"type_code": type_code},
		"lines": [
			{"id": str(i + 1), "tax_category": c, "tax_rate": Decimal(5)} for i, c in enumerate(categories)
		],
	}
	document.update(extra)
	return document


def codes(findings):
	return sorted(f.code for f in findings)


class ReadingTheMode(unittest.TestCase):
	def test_the_three_modes_read_back(self):
		self.assertIs(mode_of("Live"), Mode.LIVE)
		self.assertIs(mode_of("Preparation"), Mode.PREPARATION)
		self.assertIs(mode_of("Off"), Mode.OFF)

	def test_anything_unset_or_unknown_is_off(self):
		# A company nobody configured must behave as it did before we arrived.
		for value in (None, "", "live", "on", "Enabled", 1, object()):
			self.assertIs(mode_of(value), Mode.OFF)


class WhatEachModeDoes(unittest.TestCase):
	def test_off_enforces_nothing_and_creates_no_work(self):
		self.assertIs(enforcement_for(Mode.OFF), Enforcement.NONE)
		self.assertFalse(may_create_intent(Mode.OFF))

	def test_preparation_advises_but_creates_no_work(self):
		self.assertIs(enforcement_for(Mode.PREPARATION), Enforcement.ADVISORY)
		self.assertFalse(may_create_intent(Mode.PREPARATION))

	def test_live_blocks_and_creates_work(self):
		self.assertIs(enforcement_for(Mode.LIVE), Enforcement.BLOCKING)
		self.assertTrue(may_create_intent(Mode.LIVE))


class WhenSubmissionIsBlocked(unittest.TestCase):
	def test_only_a_live_company_blocks(self):
		for mode in (Mode.OFF, Mode.PREPARATION):
			self.assertFalse(
				blocks_submission(mode, in_scope=True, has_errors=True, validation_unavailable=True)
			)

	def test_live_blocks_on_an_error(self):
		self.assertTrue(
			blocks_submission(Mode.LIVE, in_scope=True, has_errors=True, validation_unavailable=False)
		)

	def test_live_blocks_when_the_checks_could_not_run(self):
		# Not knowing is not the same as being fine.
		self.assertTrue(
			blocks_submission(Mode.LIVE, in_scope=True, has_errors=False, validation_unavailable=True)
		)

	def test_live_lets_a_clean_invoice_through(self):
		self.assertFalse(
			blocks_submission(Mode.LIVE, in_scope=True, has_errors=False, validation_unavailable=False)
		)

	def test_an_invoice_out_of_scope_is_never_blocked(self):
		self.assertFalse(
			blocks_submission(Mode.LIVE, in_scope=False, has_errors=True, validation_unavailable=True)
		)


class WhichTypesTheRulesLeaveOpen(unittest.TestCase):
	def test_a_registered_seller_with_standard_lines_issues_a_tax_invoice(self):
		self.assertEqual(
			permitted_types(is_credit_note=False, categories={"S"}, seller_registered=True),
			(TAX_INVOICE,),
		)

	def test_an_unregistered_seller_cannot_issue_a_tax_document(self):
		self.assertEqual(
			permitted_types(is_credit_note=False, categories={"Z"}, seller_registered=False),
			(COMMERCIAL_INVOICE,),
		)

	def test_an_unregistered_seller_with_standard_lines_has_nothing_open(self):
		# Standard rated lines need a tax document, which needs a registration.
		# The facts contradict each other and the caller has to resolve it.
		self.assertEqual(
			permitted_types(is_credit_note=False, categories={"S"}, seller_registered=False),
			(),
		)

	def test_only_exempt_and_out_of_scope_rules_out_a_tax_document(self):
		self.assertEqual(
			permitted_types(is_credit_note=False, categories={"E", "O"}, seller_registered=True),
			(COMMERCIAL_INVOICE,),
		)

	def test_zero_rated_alone_leaves_both_open(self):
		self.assertEqual(
			permitted_types(is_credit_note=False, categories={"Z"}, seller_registered=True),
			(TAX_INVOICE, COMMERCIAL_INVOICE),
		)

	def test_a_credit_note_gets_credit_note_types(self):
		self.assertEqual(
			permitted_types(is_credit_note=True, categories={"S"}, seller_registered=True),
			(TAX_CREDIT_NOTE,),
		)
		self.assertEqual(
			permitted_types(is_credit_note=True, categories={"E"}, seller_registered=True),
			(COMMERCIAL_CREDIT_NOTE,),
		)


class WhereADocumentContradictsItself(unittest.TestCase):
	def test_a_commercial_document_cannot_carry_a_standard_rated_line(self):
		found = check_document_type(invoice(COMMERCIAL_INVOICE, ("S",)), seller_registered=True)
		self.assertEqual(codes(found), [CODE_COMMERCIAL_CATEGORY])
		self.assertEqual(found[0].rule_id, "ibr-122-ae")

	def test_a_commercial_document_may_carry_exempt_and_zero_rated_lines(self):
		self.assertEqual(
			check_document_type(invoice(COMMERCIAL_INVOICE, ("E", "Z", "O")), seller_registered=True),
			[],
		)

	def test_a_tax_document_made_only_of_exempt_and_out_of_scope_is_reported(self):
		found = check_document_type(invoice(TAX_INVOICE, ("E", "O")), seller_registered=True)
		self.assertEqual(codes(found), [CODE_TAX_CATEGORY])
		self.assertEqual(found[0].rule_id, "ibr-151-ae")

	def test_a_tax_document_with_one_zero_rated_line_among_them_is_fine(self):
		self.assertEqual(
			check_document_type(invoice(TAX_INVOICE, ("E", "O", "Z")), seller_registered=True),
			[],
		)

	def test_an_unregistered_seller_issuing_a_tax_document_is_reported(self):
		found = check_document_type(invoice(TAX_INVOICE, ("S",)), seller_registered=False)
		self.assertIn(CODE_SELLER_NOT_REGISTERED, codes(found))
		self.assertIn("ibr-134-ae", [f.rule_id for f in found])

	def test_an_unregistered_seller_issuing_a_commercial_document_is_fine(self):
		self.assertEqual(
			check_document_type(invoice(COMMERCIAL_INVOICE, ("Z",)), seller_registered=False),
			[],
		)

	def test_a_commercial_document_cannot_be_a_deemed_supply(self):
		document = invoice(COMMERCIAL_INVOICE, ("Z",), scenario={"deemed_supply": True})
		found = check_document_type(document, seller_registered=True)
		self.assertEqual(codes(found), [CODE_COMMERCIAL_FLAG])
		self.assertEqual(found[0].rule_id, "ibr-157-ae")

	def test_a_commercial_document_cannot_be_margin_or_summary_either(self):
		for flag in ("margin_scheme", "summary"):
			document = invoice(COMMERCIAL_INVOICE, ("Z",), scenario={flag: True})
			self.assertEqual(
				codes(check_document_type(document, seller_registered=True)),
				[CODE_COMMERCIAL_FLAG],
			)

	def test_a_commercial_document_may_be_an_export(self):
		# Only positions two, three and four are barred.
		document = invoice(COMMERCIAL_INVOICE, ("Z",), scenario={"export": True})
		self.assertEqual(check_document_type(document, seller_registered=True), [])

	def test_adjustments_count_towards_the_categories(self):
		document = invoice(COMMERCIAL_INVOICE, ("Z",))
		document["charges"] = [{"amount": Decimal("5.00"), "tax_category": "S"}]
		self.assertEqual(
			codes(check_document_type(document, seller_registered=True)),
			[CODE_COMMERCIAL_CATEGORY],
		)
		self.assertEqual(categories_on(document), {"Z", "S"})


class Direction(unittest.TestCase):
	def test_a_credit_note_carrying_an_invoice_type_is_reported(self):
		found = check(invoice(TAX_INVOICE), seller_registered=True, is_credit_note=True)
		self.assertIn(CODE_TYPE_DIRECTION, codes(found))

	def test_an_invoice_carrying_a_credit_note_type_is_reported(self):
		found = check(invoice(TAX_CREDIT_NOTE), seller_registered=True, is_credit_note=False)
		self.assertIn(CODE_TYPE_DIRECTION, codes(found))

	def test_agreement_passes(self):
		self.assertEqual(check(invoice(TAX_CREDIT_NOTE), seller_registered=True, is_credit_note=True), [])


class WhatTheseFindingsAre(unittest.TestCase):
	def test_each_one_names_the_published_rule_it_comes_from(self):
		found = check(invoice(COMMERCIAL_INVOICE, ("S",)), seller_registered=True, is_credit_note=False)
		self.assertTrue(found)
		for item in found:
			self.assertIs(item.stage, Stage.SCOPE)
			self.assertIs(item.severity, Severity.ERROR)
			self.assertTrue(item.rule_id, "a rule finding must say which rule")
			self.assertTrue(item.repair)


if __name__ == "__main__":
	unittest.main(verbosity=2)
