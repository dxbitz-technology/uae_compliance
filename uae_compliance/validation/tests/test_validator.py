"""The validator, checked against the published examples themselves.

These run the real official files, not a stand-in, so a passing run here means
the same engine and the same rules that the standards harness proves.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uae_compliance.domain.findings import Severity, Stage, StageState
from uae_compliance.validation import safe_xml
from uae_compliance.validation.artifacts import (
	PINT_VERSION,
	STANDARDS_ROOT,
	ArtifactsUnavailable,
	Compiled,
	paths_for,
)
from uae_compliance.validation.validator import CODE_NOT_XML, CODE_RULE, CODE_SCHEMA, validate

EXAMPLES = STANDARDS_ROOT / "pint_ae" / PINT_VERSION / "trn-invoice" / "example"
STANDARD = EXAMPLES / "Standard tax invoice.xml"
CREDIT_NOTE = (
	STANDARDS_ROOT / "pint_ae" / PINT_VERSION / "trn-creditnote" / "example" / "Standard tax credit Note.xml"
)

RULE_STAGES = (Stage.XSD, Stage.SCHEMATRON_SHARED, Stage.SCHEMATRON_AE)


def rule_ids(report):
	return sorted({f.rule_id for f in report.findings if f.rule_id})


class APublishedExample(unittest.TestCase):
	def test_an_official_invoice_passes_all_three_layers(self):
		report = validate(STANDARD.read_bytes())
		self.assertEqual(report.findings, ())
		for stage in RULE_STAGES:
			self.assertIs(report.state_of(stage), StageState.PASSED, stage.value)

	def test_an_official_credit_note_passes_too(self):
		report = validate(CREDIT_NOTE.read_bytes())
		self.assertEqual([f.message for f in report.findings], [])
		for stage in RULE_STAGES:
			self.assertIs(report.state_of(stage), StageState.PASSED, stage.value)


class ABrokenDocument(unittest.TestCase):
	def test_removing_the_invoice_number_fails_the_rule_that_requires_it(self):
		text = STANDARD.read_text()
		start = text.index("<cbc:ID>")
		end = text.index("</cbc:ID>", start) + len("</cbc:ID>")
		report = validate((text[:start] + text[end:]).encode())
		self.assertIn("ibr-002", rule_ids(report))

	def test_an_unknown_document_type_fails_the_code_list_rule(self):
		text = STANDARD.read_text().replace(
			"<cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>",
			"<cbc:InvoiceTypeCode>999</cbc:InvoiceTypeCode>",
		)
		report = validate(text.encode())
		self.assertIn("ibr-cl-01", rule_ids(report))
		self.assertIs(report.state_of(Stage.SCHEMATRON_SHARED), StageState.FAILED)

	def test_a_bad_tax_registration_fails_the_jurisdiction_layer(self):
		# The seller VAT identifier, one digit short of the required fifteen.
		text = STANDARD.read_text().replace(
			"<cbc:CompanyID>198765432102003</cbc:CompanyID>",
			"<cbc:CompanyID>19876543210203</cbc:CompanyID>",
		)
		report = validate(text.encode())
		self.assertIn("ibr-132-ae", rule_ids(report))
		self.assertIs(report.state_of(Stage.SCHEMATRON_AE), StageState.FAILED)

	def test_a_failed_rule_keeps_its_official_id_and_its_own_words(self):
		text = STANDARD.read_text().replace(
			"<cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>",
			"<cbc:InvoiceTypeCode>999</cbc:InvoiceTypeCode>",
		)
		report = validate(text.encode())
		failed = [f for f in report.findings if f.code == CODE_RULE]
		self.assertTrue(failed)
		for item in failed:
			self.assertTrue(item.rule_id)
			self.assertTrue(item.message)
			self.assertIs(item.severity, Severity.ERROR)

	def test_a_shape_the_schema_rejects_is_reported_by_the_schema(self):
		text = (
			STANDARD.read_text()
			.replace("<cbc:IssueDate>", "<cbc:NotAThing>")
			.replace("</cbc:IssueDate>", "</cbc:NotAThing>")
		)
		report = validate(text.encode())
		self.assertIs(report.state_of(Stage.XSD), StageState.FAILED)
		self.assertIn(CODE_SCHEMA, [f.code for f in report.findings])


class WhatCannotBeRead(unittest.TestCase):
	def test_a_document_type_declaration_is_refused_before_the_engine_sees_it(self):
		hostile = (
			b'<?xml version="1.0"?>'
			b'<!DOCTYPE Invoice [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
			b"<Invoice>&x;</Invoice>"
		)
		report = validate(hostile)
		self.assertIn(CODE_NOT_XML, [f.code for f in report.findings])
		for stage in RULE_STAGES:
			self.assertIs(report.state_of(stage), StageState.NOT_RUN)

	def test_nothing_is_reported_as_passed_when_nothing_could_be_read(self):
		report = validate(b"not xml at all")
		self.assertTrue(report.findings)
		for outcome in report.stages:
			self.assertIsNot(outcome.state, StageState.PASSED)
			self.assertTrue(outcome.reason)

	def test_an_oversized_document_is_refused(self):
		report = validate(b"<Invoice/>" + b" " * (safe_xml.MAX_BYTES + 1))
		self.assertIn(CODE_NOT_XML, [f.code for f in report.findings])


class WhenTheOfficialFilesAreMissing(unittest.TestCase):
	def test_a_missing_rule_layer_reports_unavailable_rather_than_passed(self):
		with tempfile.TemporaryDirectory() as empty:
			report = validate(STANDARD.read_bytes(), compiled=Compiled(root=Path(empty)))
		for stage in RULE_STAGES:
			self.assertIs(report.state_of(stage), StageState.UNAVAILABLE, stage.value)
			outcome = next(o for o in report.stages if o.stage is stage)
			self.assertIn("missing", outcome.reason)

	def test_an_unknown_kind_of_document_has_no_rules(self):
		with self.assertRaises(ArtifactsUnavailable):
			paths_for("PurchaseOrder")

	def test_the_pinned_files_are_all_present(self):
		for root_name in ("Invoice", "CreditNote"):
			self.assertEqual(paths_for(root_name).missing(), [])


class CompilingOnce(unittest.TestCase):
	def test_the_rule_layers_are_built_once_and_reused(self):
		# Compiling costs far more than checking a document, so a worker must
		# not rebuild them per invoice.
		compiled = Compiled()
		first = compiled.rule_layers("Invoice")
		second = compiled.rule_layers("Invoice")
		self.assertIs(first, second)
		self.assertIs(compiled.schema("Invoice"), compiled.schema("Invoice"))

	def test_the_same_document_gives_the_same_answer_twice(self):
		compiled = Compiled()
		one = validate(STANDARD.read_bytes(), compiled=compiled)
		two = validate(STANDARD.read_bytes(), compiled=compiled)
		self.assertEqual(rule_ids(one), rule_ids(two))
		self.assertEqual([(o.stage, o.state) for o in one.stages], [(o.stage, o.state) for o in two.stages])


if __name__ == "__main__":
	unittest.main(verbosity=2)
