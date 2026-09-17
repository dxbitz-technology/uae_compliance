"""What a validation check returns, and when an invoice may say it is ready.

A check never returns a sentence. It returns a finding: a stable code, where
the problem is, and what would fix it. The words come later, at display, so
they can be translated and so a stored finding still makes sense after the
wording changes.

A result gathers the findings with the state of each stage that ran. The
readiness rule lives here too, because it is the one place that decides
whether an invoice may claim it is ready, and it must not be re-derived
anywhere else.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class FindingError(ValueError):
	"""A finding or result was built in a way that cannot be trusted."""


class Level(StrEnum):
	"""How much was checked. Fast is cheap and local. Full is everything."""

	FAST = "Fast"
	FULL = "Full"


class Severity(StrEnum):
	ERROR = "Error"
	WARNING = "Warning"
	INFO = "Info"


class Stage(StrEnum):
	"""A step of the check. Required stages must pass before Ready locally."""

	SCOPE = "Scope"
	MASTERS = "Masters"
	MAPPING = "Mapping"
	ARITHMETIC = "Arithmetic"
	CANONICAL = "Canonical"
	XSD = "XSD"
	SCHEMATRON_SHARED = "Schematron shared"
	SCHEMATRON_AE = "Schematron AE"
	PROVIDER_LOCAL = "Provider local"


# Fast stops at the cheap local checks. Full adds the document ones.
FAST_STAGES = (Stage.SCOPE, Stage.MASTERS, Stage.MAPPING, Stage.ARITHMETIC)
FULL_STAGES = (
	*FAST_STAGES,
	Stage.CANONICAL,
	Stage.XSD,
	Stage.SCHEMATRON_SHARED,
	Stage.SCHEMATRON_AE,
)
# The only stage that may be skipped. An absent optional provider validator is
# not a reason to call an invoice unchecked, and it can never excuse a rule
# above.
OPTIONAL_STAGES = (Stage.PROVIDER_LOCAL,)


class StageState(StrEnum):
	PASSED = "Passed"
	FAILED = "Failed"
	NOT_RUN = "Not run"
	UNAVAILABLE = "Unavailable"
	SKIPPED = "Skipped"


# A state that is not Passed or Failed has to say why, so nobody reads a
# missing check as a clean one.
STATES_NEEDING_A_REASON = (StageState.NOT_RUN, StageState.UNAVAILABLE, StageState.SKIPPED)


class Readiness(StrEnum):
	"""What the working record may say about an invoice."""

	NOT_CHECKED = "Not checked"
	STALE = "Stale"
	FURTHER_CHECKS_REQUIRED = "Further checks required"
	NEEDS_DETAILS = "Needs details"
	READY_LOCALLY = "Ready locally"
	UNAVAILABLE = "Unavailable"
	OUT_OF_SCOPE = "Out of scope"


@dataclass(frozen=True)
class SourceRef:
	"""Where the problem sits in the source document."""

	doctype: str
	name: str
	row_id: str | None = None

	def __post_init__(self):
		if not self.doctype or not self.name:
			raise FindingError("a source reference needs a doctype and a name")


@dataclass(frozen=True)
class Finding:
	"""One problem, in a form that survives a wording change.

	`code` is ours and stable. `rule_id` is the official rule when an official
	rule is what failed. `message` is a plain fallback for a reader with no
	translation; `params` carries the values so the display can build a
	translated sentence instead of parsing the fallback.
	"""

	code: str
	severity: Severity
	stage: Stage
	message: str
	path: str | None = None
	source: SourceRef | None = None
	rule_id: str | None = None
	repair: str | None = None
	params: Mapping[str, str] = field(default_factory=dict)
	caused_by: str | None = None

	def __post_init__(self):
		if not self.code:
			raise FindingError("a finding needs a stable code")
		if not self.message:
			raise FindingError(f"{self.code}: a finding needs a fallback message")
		if self.path is None and self.source is None:
			raise FindingError(f"{self.code}: a finding must say where the problem is")
		if self.severity is Severity.ERROR and not self.repair:
			raise FindingError(f"{self.code}: an error must name what would fix it")
		if self.caused_by == self.code:
			raise FindingError(f"{self.code}: a finding cannot be its own cause")
		for key, value in self.params.items():
			if not isinstance(key, str) or not isinstance(value, str):
				raise FindingError(f"{self.code}: message parameters must be strings")

	@property
	def blocking(self) -> bool:
		return self.severity is Severity.ERROR


@dataclass(frozen=True)
class StageOutcome:
	stage: Stage
	state: StageState
	reason: str | None = None

	def __post_init__(self):
		if self.state in STATES_NEEDING_A_REASON and not self.reason:
			raise FindingError(f"{self.stage.value} is {self.state.value} and must say why")
		if self.state is StageState.SKIPPED and self.stage not in OPTIONAL_STAGES:
			raise FindingError(f"{self.stage.value} is not optional and cannot be skipped")


@dataclass(frozen=True)
class ValidationResult:
	"""Everything one run of the checks produced.

	The fingerprints say what was checked. If either has moved since, the
	result is stale and says nothing about the invoice as it stands now.
	"""

	level: Level
	checked_at: str
	input_fingerprint: str
	master_fingerprint: str
	ruleset_version: str
	in_scope: bool
	stages: Sequence[StageOutcome] = field(default_factory=tuple)
	findings: Sequence[Finding] = field(default_factory=tuple)

	def __post_init__(self):
		seen = [outcome.stage for outcome in self.stages]
		duplicates = {s.value for s in seen if seen.count(s) > 1}
		if duplicates:
			raise FindingError("a stage appears twice: " + ", ".join(sorted(duplicates)))
		if not self.checked_at:
			raise FindingError("a result must say when it was checked")
		if not self.ruleset_version:
			raise FindingError("a result must say which rules produced it")
		codes = {f.code for f in self.findings}
		for item in self.findings:
			if item.caused_by and item.caused_by not in codes:
				raise FindingError(f"{item.code} names a cause that is not in this result")

	def state_of(self, stage: Stage) -> StageState:
		for outcome in self.stages:
			if outcome.stage is stage:
				return outcome.state
		return StageState.NOT_RUN

	@property
	def errors(self) -> tuple[Finding, ...]:
		return tuple(f for f in self.findings if f.blocking)

	def actionable(self) -> tuple[Finding, ...]:
		"""Findings worth showing, with the knock-on ones left out.

		One missing value can fail several rules. Showing all of them buries
		the thing the user has to fix, so a finding that names a cause present
		in this result is held back until its cause is dealt with.
		"""
		return tuple(f for f in self.findings if not f.caused_by)

	@property
	def readiness(self) -> Readiness:
		"""What this result alone says.

		It cannot know whether the invoice has changed since, so it never
		returns Stale. Anything deciding what to show, or whether to let a
		submission through, calls working_readiness instead.
		"""
		if not self.in_scope:
			return Readiness.OUT_OF_SCOPE
		required = FULL_STAGES if self.level is Level.FULL else FAST_STAGES
		states = {stage: self.state_of(stage) for stage in required}
		if any(state is StageState.UNAVAILABLE for state in states.values()):
			return Readiness.UNAVAILABLE
		if self.errors or any(state is StageState.FAILED for state in states.values()):
			return Readiness.NEEDS_DETAILS
		if any(state is not StageState.PASSED for state in states.values()):
			# A required stage that did not run leaves the question open.
			return Readiness.FURTHER_CHECKS_REQUIRED
		if self.level is not Level.FULL:
			# Fast passing means nothing cheap is wrong, not that it is ready.
			return Readiness.FURTHER_CHECKS_REQUIRED
		return Readiness.READY_LOCALLY

	def is_current_for(self, input_fingerprint: str, master_fingerprint: str) -> bool:
		"""Say whether this result still describes the invoice in front of us."""
		return self.input_fingerprint == input_fingerprint and self.master_fingerprint == master_fingerprint


def working_readiness(
	result: ValidationResult | None,
	input_fingerprint: str,
	master_fingerprint: str,
) -> Readiness:
	"""What the working record should say about the invoice as it stands now.

	This is the whole rule in one place. An invoice with no result has not
	been checked. A result taken against different inputs or different
	masters is stale and says nothing about the invoice in front of us, even
	if it passed at the time. Only a current full pass reaches Ready locally.
	"""
	if result is None:
		return Readiness.NOT_CHECKED
	if not result.is_current_for(input_fingerprint, master_fingerprint):
		# Out of scope does not go stale: scope is decided by company policy,
		# not by the invoice content the fingerprints cover.
		if not result.in_scope:
			return Readiness.OUT_OF_SCOPE
		return Readiness.STALE
	return result.readiness


def summarise(findings: Iterable[Finding]) -> dict[str, int]:
	"""Count by severity, for a short line in the interface."""
	counts = {severity.value: 0 for severity in Severity}
	for item in findings:
		counts[item.severity.value] += 1
	return counts
