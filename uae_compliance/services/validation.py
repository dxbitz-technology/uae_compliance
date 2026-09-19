"""The one place an invoice gets checked.

Two levels. Fast is local and cheap: is this in scope, are the masters
there, does every line map to a category, and does the arithmetic hold. Full
adds the document itself: build the canonical invoice, write the XML, and
put it through the schema and both rule layers.

The same code answers the form and the server, so what a person sees before
saving is what the submit gate will decide with. Nothing here reaches the
network. A provider is never asked whether an invoice is valid.
"""

from __future__ import annotations

from datetime import UTC, datetime

import frappe

from uae_compliance.domain import money, scenarios, scope
from uae_compliance.domain.findings import (
	Level,
	Severity,
	Stage,
	StageOutcome,
	StageState,
	ValidationResult,
	summarise,
)
from uae_compliance.erpnext import masters
from uae_compliance.erpnext.extract import extract
from uae_compliance.erpnext.fingerprint import master_fingerprint, source_fingerprint
from uae_compliance.services.working import WORKING_DOCTYPE
from uae_compliance.validation.artifacts import PINT_VERSION

FAST = Level.FAST
FULL = Level.FULL


def check(invoice, level: Level = FAST, *, overrides: dict | None = None) -> ValidationResult:
	"""Check one invoice and say what was found.

	`invoice` is a Sales Invoice document, saved or not. Nothing is written.
	`overrides` carries details somebody has typed but not saved, so a preview
	shows what those would mean without committing them.
	"""
	resolution = masters.resolve(invoice)
	in_scope = resolution.mode is not scope.Mode.OFF
	source_print = source_fingerprint(invoice)

	if not in_scope:
		return ValidationResult(
			level=level,
			checked_at=_now(),
			input_fingerprint=source_print,
			master_fingerprint=master_fingerprint(resolution.revisions),
			ruleset_version=PINT_VERSION,
			in_scope=False,
			stages=(StageOutcome(Stage.SCOPE, StageState.PASSED),),
		)

	document, findings = extract(invoice, overrides=overrides)
	findings = list(findings)
	stages = [StageOutcome(Stage.SCOPE, StageState.PASSED)]

	if document is None:
		# Extraction gave up, which only happens when the company went off
		# underneath us between the two reads.
		return _unavailable(level, source_print, resolution, "The company was switched off while checking.")

	# Before the XML, so a missing scenario detail names its field rather
	# than coming back later as a rule id.
	findings.extend(scenarios.check(document))
	stages[0] = StageOutcome(
		Stage.SCOPE,
		StageState.FAILED
		if any(f.stage is Stage.SCOPE and f.blocking for f in findings)
		else StageState.PASSED,
	)

	stages.append(_outcome(Stage.MASTERS, findings, Stage.MASTERS))
	stages.append(_outcome(Stage.MAPPING, findings, Stage.MAPPING))

	arithmetic = money.check(document)
	findings.extend(arithmetic)
	stages.append(
		StageOutcome(
			Stage.ARITHMETIC,
			StageState.FAILED if any(f.blocking for f in arithmetic) else StageState.PASSED,
		)
	)

	if level is FULL:
		stages.extend(_full(document, findings))

	return ValidationResult(
		level=level,
		checked_at=_now(),
		input_fingerprint=source_print,
		master_fingerprint=master_fingerprint(resolution.revisions),
		ruleset_version=PINT_VERSION,
		in_scope=True,
		stages=tuple(stages),
		findings=tuple(findings),
	)


def _full(document, findings) -> list[StageOutcome]:
	"""The document checks: canonical, schema, then both rule layers.

	A document that will not serialize cannot be put through the rules, so
	the later stages say they did not run and why, rather than passing by
	default.
	"""
	from uae_compliance.domain.canonical import INVOICE
	from uae_compliance.domain.schema import check as check_schema
	from uae_compliance.validation.serializer import to_xml
	from uae_compliance.validation.validator import validate

	canonical_findings = check_schema(document, INVOICE)
	findings.extend(canonical_findings)
	if any(f.blocking for f in canonical_findings):
		reason = "The invoice is not complete enough to write."
		return [
			StageOutcome(Stage.CANONICAL, StageState.FAILED),
			StageOutcome(Stage.XSD, StageState.NOT_RUN, reason),
			StageOutcome(Stage.SCHEMATRON_SHARED, StageState.NOT_RUN, reason),
			StageOutcome(Stage.SCHEMATRON_AE, StageState.NOT_RUN, reason),
		]

	outcomes = [StageOutcome(Stage.CANONICAL, StageState.PASSED)]
	report = validate(to_xml(document))
	findings.extend(report.findings)
	outcomes.extend(report.stages)
	return outcomes


def _outcome(stage: Stage, findings, wanted: Stage) -> StageOutcome:
	failed = any(f.stage is wanted and f.blocking for f in findings)
	return StageOutcome(stage, StageState.FAILED if failed else StageState.PASSED)


def _unavailable(level, source_print, resolution, reason) -> ValidationResult:
	return ValidationResult(
		level=level,
		checked_at=_now(),
		input_fingerprint=source_print,
		master_fingerprint=master_fingerprint(resolution.revisions),
		ruleset_version=PINT_VERSION,
		in_scope=True,
		stages=(StageOutcome(Stage.SCOPE, StageState.UNAVAILABLE, reason),),
	)


def _now() -> str:
	return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def record_result(invoice_name: str, result: ValidationResult):
	"""Write what a check found onto the working record.

	The record keeps the current findings only. Anything already sent holds
	its own frozen copy and is never touched by a later check.
	"""
	name = frappe.db.get_value(WORKING_DOCTYPE, {"sales_invoice": invoice_name}, "name")
	if not name:
		return
	counts = summarise(result.findings)
	doc = frappe.get_doc(WORKING_DOCTYPE, name)
	doc.flags.from_check = True
	doc.readiness = result.readiness.value
	doc.checked_at = result.checked_at.replace("T", " ").rstrip("Z")
	doc.checked_level = result.level.value
	doc.errors = counts[Severity.ERROR.value]
	doc.warnings = counts[Severity.WARNING.value]
	doc.source_fingerprint = result.input_fingerprint
	doc.master_fingerprint = result.master_fingerprint
	doc.findings = frappe.as_json([plain_finding(f) for f in result.actionable()])
	doc.in_scope = 1 if result.in_scope else 0
	doc.save(ignore_permissions=True)


def plain_finding(finding) -> dict:
	"""A finding in a form the browser can render and a reader can search."""
	return {
		"code": finding.code,
		"severity": finding.severity.value,
		"stage": finding.stage.value,
		"message": finding.message,
		"path": finding.path,
		"rule_id": finding.rule_id,
		"repair": finding.repair,
		"row": finding.source.row_id if finding.source else None,
		"params": dict(finding.params),
	}
