"""Checks on the finding and result shapes, and on the readiness rule.

The readiness rule decides whether an invoice may claim it is ready, so most
of these checks are about the ways it must refuse to say yes.
"""

from __future__ import annotations

import unittest

from uae_compliance.domain.findings import (
	FAST_STAGES,
	FULL_STAGES,
	Finding,
	FindingError,
	Level,
	Readiness,
	Severity,
	SourceRef,
	Stage,
	StageOutcome,
	StageState,
	ValidationResult,
	summarise,
	working_readiness,
)


def passed(stages):
	return tuple(StageOutcome(stage, StageState.PASSED) for stage in stages)


def an_error(code="UAE-0001", **kwargs):
	base = {
		"code": code,
		"severity": Severity.ERROR,
		"stage": Stage.MASTERS,
		"message": "Buyer tax registration missing.",
		"path": "parties.buyer.tax_registration",
		"repair": "open_party_profile",
	}
	base.update(kwargs)
	return Finding(**base)


def a_result(level=Level.FULL, stages=None, findings=(), in_scope=True):
	return ValidationResult(
		level=level,
		checked_at="2026-09-17T10:00:00Z",
		input_fingerprint="input-1",
		master_fingerprint="master-1",
		ruleset_version="pint-ae-1.0.4",
		in_scope=in_scope,
		stages=passed(FULL_STAGES if level is Level.FULL else FAST_STAGES) if stages is None else stages,
		findings=findings,
	)


class BuildingAFinding(unittest.TestCase):
	def test_a_finding_needs_a_code_and_a_fallback_message(self):
		with self.assertRaises(FindingError):
			an_error(code="")
		with self.assertRaises(FindingError):
			an_error(message="")

	def test_a_finding_must_say_where_the_problem_is(self):
		with self.assertRaises(FindingError):
			Finding(
				code="UAE-0001",
				severity=Severity.WARNING,
				stage=Stage.MASTERS,
				message="Something is off.",
			)

	def test_a_source_row_counts_as_saying_where(self):
		item = Finding(
			code="UAE-0002",
			severity=Severity.WARNING,
			stage=Stage.MAPPING,
			message="Unit of measure has no code.",
			source=SourceRef("Sales Invoice Item", "SINV-1", row_id="row-3"),
		)
		self.assertEqual(item.source.row_id, "row-3")

	def test_an_error_must_name_what_would_fix_it(self):
		with self.assertRaises(FindingError):
			an_error(repair=None)

	def test_a_warning_does_not_have_to(self):
		item = an_error(severity=Severity.WARNING, repair=None)
		self.assertFalse(item.blocking)

	def test_a_source_reference_needs_both_parts(self):
		with self.assertRaises(FindingError):
			SourceRef("Sales Invoice", "")

	def test_message_parameters_stay_strings_so_they_can_be_translated(self):
		item = an_error(params={"field": "TRN"})
		self.assertEqual(item.params["field"], "TRN")
		with self.assertRaises(FindingError):
			an_error(params={"count": 3})

	def test_a_finding_cannot_be_its_own_cause(self):
		with self.assertRaises(FindingError):
			an_error(caused_by="UAE-0001")


class BuildingAStageOutcome(unittest.TestCase):
	def test_a_stage_that_did_not_run_must_say_why(self):
		with self.assertRaises(FindingError):
			StageOutcome(Stage.XSD, StageState.NOT_RUN)
		outcome = StageOutcome(Stage.XSD, StageState.NOT_RUN, reason="extraction failed earlier")
		self.assertEqual(outcome.reason, "extraction failed earlier")

	def test_an_unavailable_stage_must_say_why(self):
		with self.assertRaises(FindingError):
			StageOutcome(Stage.SCHEMATRON_AE, StageState.UNAVAILABLE)

	def test_only_an_optional_stage_may_be_skipped(self):
		ok = StageOutcome(Stage.PROVIDER_LOCAL, StageState.SKIPPED, reason="no validator installed")
		self.assertIs(ok.state, StageState.SKIPPED)
		with self.assertRaises(FindingError):
			StageOutcome(Stage.SCHEMATRON_AE, StageState.SKIPPED, reason="slow")

	def test_a_passing_stage_needs_no_reason(self):
		self.assertIsNone(StageOutcome(Stage.SCOPE, StageState.PASSED).reason)


class BuildingAResult(unittest.TestCase):
	def test_a_stage_cannot_appear_twice(self):
		with self.assertRaises(FindingError):
			a_result(stages=(*passed(FULL_STAGES), StageOutcome(Stage.SCOPE, StageState.FAILED)))

	def test_a_result_must_say_when_and_under_which_rules(self):
		with self.assertRaises(FindingError):
			ValidationResult(
				level=Level.FAST,
				checked_at="",
				input_fingerprint="a",
				master_fingerprint="b",
				ruleset_version="pint-ae-1.0.4",
				in_scope=True,
			)

	def test_a_cause_must_exist_in_the_same_result(self):
		with self.assertRaises(FindingError):
			a_result(findings=(an_error(caused_by="UAE-9999"),))

	def test_an_unlisted_stage_reads_as_not_run(self):
		result = a_result(level=Level.FAST, stages=())
		self.assertIs(result.state_of(Stage.SCOPE), StageState.NOT_RUN)


class ReadinessRule(unittest.TestCase):
	def test_a_full_pass_with_no_errors_is_ready(self):
		self.assertIs(a_result().readiness, Readiness.READY_LOCALLY)

	def test_a_fast_pass_is_not_ready(self):
		self.assertIs(a_result(level=Level.FAST).readiness, Readiness.FURTHER_CHECKS_REQUIRED)

	def test_an_error_means_details_are_needed(self):
		self.assertIs(a_result(findings=(an_error(),)).readiness, Readiness.NEEDS_DETAILS)

	def test_a_warning_alone_does_not_block(self):
		warning = an_error(severity=Severity.WARNING, repair=None)
		self.assertIs(a_result(findings=(warning,)).readiness, Readiness.READY_LOCALLY)

	def test_a_failed_stage_means_details_are_needed(self):
		stages = (
			*passed([s for s in FULL_STAGES if s is not Stage.XSD]),
			StageOutcome(Stage.XSD, StageState.FAILED),
		)
		self.assertIs(a_result(stages=stages).readiness, Readiness.NEEDS_DETAILS)

	def test_a_required_stage_that_did_not_run_leaves_it_open(self):
		stages = (
			*passed([s for s in FULL_STAGES if s is not Stage.SCHEMATRON_AE]),
			StageOutcome(Stage.SCHEMATRON_AE, StageState.NOT_RUN, reason="no XML produced"),
		)
		self.assertIs(a_result(stages=stages).readiness, Readiness.FURTHER_CHECKS_REQUIRED)

	def test_a_missing_required_stage_is_never_ready(self):
		stages = passed([s for s in FULL_STAGES if s is not Stage.SCHEMATRON_AE])
		self.assertIs(a_result(stages=stages).readiness, Readiness.FURTHER_CHECKS_REQUIRED)

	def test_an_unavailable_stage_says_so_rather_than_passing(self):
		stages = (
			*passed([s for s in FULL_STAGES if s is not Stage.SCHEMATRON_AE]),
			StageOutcome(Stage.SCHEMATRON_AE, StageState.UNAVAILABLE, reason="engine missing"),
		)
		self.assertIs(a_result(stages=stages).readiness, Readiness.UNAVAILABLE)

	def test_a_skipped_optional_stage_does_not_stop_readiness(self):
		stages = (
			*passed(FULL_STAGES),
			StageOutcome(Stage.PROVIDER_LOCAL, StageState.SKIPPED, reason="not installed"),
		)
		self.assertIs(a_result(stages=stages).readiness, Readiness.READY_LOCALLY)

	def test_out_of_scope_wins_over_everything(self):
		result = a_result(in_scope=False, stages=(), findings=(an_error(),))
		self.assertIs(result.readiness, Readiness.OUT_OF_SCOPE)


class StaleResults(unittest.TestCase):
	def test_a_result_is_current_only_for_what_it_checked(self):
		result = a_result()
		self.assertTrue(result.is_current_for("input-1", "master-1"))
		self.assertFalse(result.is_current_for("input-2", "master-1"))
		self.assertFalse(result.is_current_for("input-1", "master-2"))


class WorkingReadiness(unittest.TestCase):
	def test_no_result_means_not_checked(self):
		self.assertIs(
			working_readiness(None, "input-1", "master-1"),
			Readiness.NOT_CHECKED,
		)

	def test_a_current_full_pass_is_ready(self):
		self.assertIs(
			working_readiness(a_result(), "input-1", "master-1"),
			Readiness.READY_LOCALLY,
		)

	def test_a_changed_invoice_makes_a_passing_result_stale(self):
		self.assertIs(
			working_readiness(a_result(), "input-2", "master-1"),
			Readiness.STALE,
		)

	def test_a_changed_master_makes_a_passing_result_stale(self):
		self.assertIs(
			working_readiness(a_result(), "input-1", "master-2"),
			Readiness.STALE,
		)

	def test_out_of_scope_does_not_go_stale(self):
		result = a_result(in_scope=False, stages=())
		self.assertIs(
			working_readiness(result, "input-99", "master-99"),
			Readiness.OUT_OF_SCOPE,
		)

	def test_a_stale_result_never_reports_ready_even_though_it_passed(self):
		result = a_result()
		self.assertIs(result.readiness, Readiness.READY_LOCALLY)
		self.assertIsNot(
			working_readiness(result, "input-changed", "master-1"),
			Readiness.READY_LOCALLY,
		)


class Reporting(unittest.TestCase):
	def test_a_consequence_is_held_back_until_its_cause_is_fixed(self):
		cause = an_error(code="UAE-0001")
		consequence = an_error(code="UAE-0002", caused_by="UAE-0001")
		result = a_result(findings=(cause, consequence))
		self.assertEqual([f.code for f in result.actionable()], ["UAE-0001"])
		self.assertEqual(len(result.errors), 2)

	def test_independent_errors_are_all_shown(self):
		result = a_result(findings=(an_error(code="UAE-0001"), an_error(code="UAE-0003")))
		self.assertEqual([f.code for f in result.actionable()], ["UAE-0001", "UAE-0003"])

	def test_counts_by_severity(self):
		findings = (
			an_error(code="UAE-0001"),
			an_error(code="UAE-0002", severity=Severity.WARNING, repair=None),
		)
		self.assertEqual(summarise(findings), {"Error": 1, "Warning": 1, "Info": 0})


if __name__ == "__main__":
	unittest.main(verbosity=2)
