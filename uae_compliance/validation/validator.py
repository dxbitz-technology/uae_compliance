"""Run a document through the official schema and both official rule layers.

Three layers, each reported separately: the UBL schema says whether the shape
is right, the shared layer carries the rules every country's invoices follow,
and the jurisdiction layer carries the ones specific to here.

A layer that could not run is reported as unavailable, never as passed. The
difference matters: an invoice nobody managed to check is not an invoice that
passed, and treating the two alike is how an unchecked document reaches a tax
authority.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from uae_compliance.domain.findings import Finding, Severity, Stage, StageOutcome, StageState
from uae_compliance.validation import safe_xml
from uae_compliance.validation.artifacts import ArtifactsUnavailable, Compiled, shared

CODE_NOT_XML = "XML-0001"
CODE_SCHEMA = "XML-0002"
CODE_RULE = "XML-0003"

SVRL = "{http://purl.oclc.org/dsdl/svrl}"

# Which stage each layer reports under.
STAGE_FOR_LAYER = {
	"Schematron shared": Stage.SCHEMATRON_SHARED,
	"Schematron AE": Stage.SCHEMATRON_AE,
}


@dataclass(frozen=True)
class Report:
	findings: tuple[Finding, ...]
	stages: tuple[StageOutcome, ...]

	def state_of(self, stage: Stage) -> StageState:
		for outcome in self.stages:
			if outcome.stage is stage:
				return outcome.state
		return StageState.NOT_RUN


def _finding(code: str, message: str, *, rule: str | None = None, path: str | None = None) -> Finding:
	return Finding(
		code=code,
		severity=Severity.ERROR,
		stage=Stage.XSD if code != CODE_RULE else Stage.SCHEMATRON_SHARED,
		message=message,
		path=path or "document",
		repair="correct_the_document",
		rule_id=rule,
	)


def _rule_finding(layer: str, item) -> Finding:
	"""One failed official rule, kept in its own words."""
	text = " ".join("".join(item.itertext()).split())
	flag = item.get("flag", "")
	return Finding(
		code=CODE_RULE,
		severity=Severity.WARNING if flag == "warning" else Severity.ERROR,
		stage=STAGE_FOR_LAYER.get(layer, Stage.SCHEMATRON_SHARED),
		message=text or "An official rule was not satisfied.",
		path=item.get("location") or "document",
		rule_id=item.get("id") or None,
		repair="correct_the_document" if flag != "warning" else None,
	)


def validate(data: bytes, *, compiled: Compiled | None = None) -> Report:
	"""Check one document, reporting each layer separately."""
	compiled = compiled or shared()
	findings: list[Finding] = []
	stages: list[StageOutcome] = []

	try:
		tree = safe_xml.parse_bytes(data)
	except safe_xml.UnsafeDocument as exc:
		# Nothing can be checked, and nothing is assumed about it.
		reason = str(exc)
		findings.append(_finding(CODE_NOT_XML, f"This document cannot be read. {reason}"))
		return Report(
			findings=tuple(findings),
			stages=tuple(
				StageOutcome(stage, StageState.NOT_RUN, reason=reason)
				for stage in (Stage.XSD, Stage.SCHEMATRON_SHARED, Stage.SCHEMATRON_AE)
			),
		)

	root_name = safe_xml.root_name(tree)
	stages.append(_run_schema(tree, root_name, compiled, findings))
	stages.extend(_run_rules(tree, root_name, compiled, findings))
	return Report(findings=tuple(findings), stages=tuple(stages))


def _run_schema(tree, root_name: str, compiled: Compiled, findings: list[Finding]) -> StageOutcome:
	try:
		schema = compiled.schema(root_name)
	except ArtifactsUnavailable as exc:
		return StageOutcome(Stage.XSD, StageState.UNAVAILABLE, reason=str(exc))
	if schema.validate(tree):
		return StageOutcome(Stage.XSD, StageState.PASSED)
	for error in schema.error_log:
		findings.append(_finding(CODE_SCHEMA, f"line {error.line}: {error.message}", path=error.path or None))
	return StageOutcome(Stage.XSD, StageState.FAILED)


def _run_rules(tree, root_name: str, compiled: Compiled, findings: list[Finding]) -> Sequence[StageOutcome]:
	try:
		layers = compiled.rule_layers(root_name)
		# The engine reads what the hardened parse produced, never the file.
		document = compiled.parse(safe_xml.reserialize(tree))
	except ArtifactsUnavailable as exc:
		return [
			StageOutcome(stage, StageState.UNAVAILABLE, reason=str(exc))
			for stage in (Stage.SCHEMATRON_SHARED, Stage.SCHEMATRON_AE)
		]

	outcomes = []
	for label, executable in layers:
		stage = STAGE_FOR_LAYER[label]
		try:
			svrl = executable.transform_to_string(xdm_node=document)
			report = safe_xml.parse_bytes(svrl.encode("utf-8"))
		except Exception as exc:
			outcomes.append(StageOutcome(stage, StageState.UNAVAILABLE, reason=str(exc)))
			continue
		failed = [_rule_finding(label, item) for item in report.getroot().iter(SVRL + "failed-assert")]
		findings.extend(failed)
		blocking = [f for f in failed if f.severity is Severity.ERROR]
		outcomes.append(StageOutcome(stage, StageState.FAILED if blocking else StageState.PASSED))
	return outcomes
