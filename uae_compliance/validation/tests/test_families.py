"""Which package checks a document, and why it matters that it is the right one.

Self-billing is a separate published specification with its own rules. The
billing package refuses its two document types outright, so a self-billed
document checked against the wrong package looks broken when it is not, and
a billing document checked against the self-billing package would be
checked against rules it never claimed to follow.

So the document says which specification it follows and is checked against
that. One we do not hold is not checked at all, which reports as
unavailable rather than passed.
"""

import unittest
from pathlib import Path

from uae_compliance.validation.artifacts import (
	CUSTOMIZATION_ID,
	SELF_BILLING_CUSTOMIZATION_ID,
	ArtifactsUnavailable,
	family_for,
)
from uae_compliance.validation.validator import validate

ROOT = Path(__file__).resolve().parents[2] / "standards"
BILLING = ROOT / "pint_ae" / "1.0.4"
SELF_BILLING = ROOT / "pint_ae_sb" / "1.0.4"

SELF_BILLED_INVOICE = SELF_BILLING / "trn-invoice" / "example" / "Self Billing.xml"
SELF_BILLED_CREDIT_NOTE = SELF_BILLING / "trn-creditnote" / "example" / "Self billing tax credit note.xml"


def states(report) -> dict:
	return {outcome.stage.value: outcome.state.value for outcome in report.stages}


def rules(report) -> set:
	return {finding.rule_id for finding in report.findings if finding.rule_id}


class ChoosingThePackage(unittest.TestCase):
	def test_billing_goes_to_the_billing_package(self):
		self.assertEqual(family_for(CUSTOMIZATION_ID), "pint_ae")

	def test_self_billing_goes_to_its_own(self):
		self.assertEqual(family_for(SELF_BILLING_CUSTOMIZATION_ID), "pint_ae_sb")

	def test_a_specification_we_do_not_hold_is_refused_rather_than_guessed(self):
		with self.assertRaises(ArtifactsUnavailable):
			family_for("urn:peppol:pint:billing-1@xx-9")

	def test_a_document_that_says_nothing_gets_the_billing_package(self):
		# The schema will refuse it on its own terms. There is no point
		# refusing to look at it before that.
		self.assertEqual(family_for(None), "pint_ae")


class TheOfficialSelfBillingExamples(unittest.TestCase):
	def test_the_invoice_passes_every_layer(self):
		report = validate(SELF_BILLED_INVOICE.read_bytes())
		self.assertEqual(
			states(report),
			{"XSD": "Passed", "Schematron shared": "Passed", "Schematron AE": "Passed"},
		)

	def test_the_credit_note_passes_every_layer(self):
		report = validate(SELF_BILLED_CREDIT_NOTE.read_bytes())
		self.assertEqual(
			states(report),
			{"XSD": "Passed", "Schematron shared": "Passed", "Schematron AE": "Passed"},
		)

	def test_they_carry_the_two_document_types_the_billing_package_refuses(self):
		self.assertIn(b"<cbc:InvoiceTypeCode>389", SELF_BILLED_INVOICE.read_bytes())
		self.assertIn(b"<cbc:CreditNoteTypeCode>261", SELF_BILLED_CREDIT_NOTE.read_bytes())


class WhyTheRightPackageMatters(unittest.TestCase):
	def test_the_billing_package_refuses_a_self_billed_document(self):
		# Not a hypothetical. This is what P00 recorded and why self-billing
		# waited for its own package rather than being bolted onto the
		# billing one.
		forced = SELF_BILLED_INVOICE.read_bytes().replace(
			SELF_BILLING_CUSTOMIZATION_ID.encode(), CUSTOMIZATION_ID.encode()
		)
		report = validate(forced)
		self.assertEqual(states(report)["Schematron shared"], "Failed")
		self.assertIn("ibr-cl-01", rules(report))

	def test_an_unknown_specification_is_unavailable_and_never_passed(self):
		# Spec 6.1. Missing artifacts mean validation unavailable, which is
		# a different thing from a document being fine.
		unknown = SELF_BILLED_INVOICE.read_bytes().replace(
			SELF_BILLING_CUSTOMIZATION_ID.encode(), b"urn:peppol:pint:billing-1@xx-9"
		)
		report = validate(unknown)
		self.assertEqual(set(states(report).values()), {"Unavailable"})
		self.assertTrue(report.findings)

	def test_an_ordinary_billing_invoice_still_passes(self):
		# The routing must not have moved the ground under the billing side.
		example = BILLING / "trn-invoice" / "example" / "Standard tax invoice.xml"
		if not example.is_file():
			example = sorted((BILLING / "trn-invoice" / "example").glob("*.xml"))[0]
		report = validate(example.read_bytes())
		self.assertEqual(states(report)["Schematron AE"], "Passed")
