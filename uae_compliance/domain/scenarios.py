"""What each kind of supply has to carry.

The eight flags are not decoration. Each one turns on rules that demand
things an ordinary invoice does not need, and the official rules enforce
them at the very end, by rule id, on XML. A person reading "ibr-137-ae
failed" has to go and look it up.

So the same requirements are checked here first, in the canonical model,
where a finding can say which field is missing and what would fill it. The
official rules remain the authority and still run. This is about telling
somebody something useful before they get there.

Every row below cites the rule that demands it. Nothing here was invented.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from uae_compliance.domain.findings import Finding, Severity, Stage

CODE_MISSING = "SCEN-0001"
CODE_UNSUPPORTED = "SCEN-0002"
CODE_CONTRADICTS = "SCEN-0003"

# The published order of the eight positions. The serializer builds the
# string; this names what each position means.
POSITIONS = (
	"free_zone",
	"deemed_supply",
	"margin_scheme",
	"summary",
	"continuous_supply",
	"agent_billing",
	"ecommerce",
	"export",
)


@dataclass(frozen=True)
class Requirement:
	"""One thing a scenario makes necessary, and the rule that says so."""

	path: str
	rule: str
	message: str
	repair: str


@dataclass(frozen=True)
class Scenario:
	"""One kind of supply, what it needs, and whether we support it yet.

	`supported` starts false for anything whose accounting has not been
	worked through. An unsupported scenario is refused in Live rather than
	approximated, which is invariant I11.
	"""

	flag: str
	label: str
	supported: bool
	requires: tuple[Requirement, ...] = ()
	notes: str = ""


def needs(path: str, rule: str, message: str, repair: str) -> Requirement:
	return Requirement(path=path, rule=rule, message=message, repair=repair)


# Read from the pinned rules, each one cited. See the packet record for how
# the patterns in those rules map onto the eight positions.
SCENARIOS: dict[str, Scenario] = {
	"free_zone": Scenario(
		flag="free_zone",
		label="Free zone",
		supported=True,
		requires=(
			needs(
				"parties.beneficiary.participant",
				"ibr-007-ae",
				"A free zone supply has to name who benefits from it.",
				"Add the beneficiary's identifier on the invoice's e-invoicing details.",
			),
		),
		notes="A name on its own is not enough. The rule asks for the identifier.",
	),
	"deemed_supply": Scenario(
		flag="deemed_supply",
		label="Deemed supply",
		supported=True,
		requires=(
			needs(
				"payment.means_code",
				"ibr-191-ae",
				"A deemed supply has to say how it is paid.",
				"Record a mode of payment on the invoice.",
			),
		),
		notes="A due date is also required once anything is payable, which ibr-127-ae enforces.",
	),
	"margin_scheme": Scenario(
		flag="margin_scheme",
		label="Margin scheme",
		supported=False,
		notes=(
			"Every line has to carry tax category N and the margin itself has to be worked "
			"out, which ibr-116-ae enforces. The accounting for it has not been settled."
		),
	),
	"summary": Scenario(
		flag="summary",
		label="Summary invoice",
		supported=True,
		requires=(
			needs(
				"document.period",
				"ibr-138-ae",
				"A summary invoice has to say which period it covers.",
				"Set the from and to dates on the invoice.",
			),
		),
	),
	"continuous_supply": Scenario(
		flag="continuous_supply",
		label="Continuous supply",
		supported=True,
		notes="No rule adds a requirement for this on its own.",
	),
	"agent_billing": Scenario(
		flag="agent_billing",
		label="Billed by an agent",
		supported=True,
		requires=(
			needs(
				"parties.principal.participant",
				"ibr-137-ae",
				"An invoice billed by an agent has to name the principal.",
				"Add the principal's identifier on the invoice's e-invoicing details.",
			),
			needs(
				"parties.seller.tax_registration",
				"ibr-177-ae",
				"An agent billing on somebody's behalf has to carry its own registration.",
				"Add the seller's tax registration.",
			),
		),
		notes="ibr-176-ae also requires the seller and the principal to be different parties.",
	),
	"ecommerce": Scenario(
		flag="ecommerce",
		label="E-commerce",
		supported=True,
		requires=(
			needs(
				"delivery.address",
				"ibr-142-ae",
				"An e-commerce supply has to say where it was delivered.",
				"Set a shipping address on the invoice, with its street, city and emirate.",
			),
		),
	),
	"export": Scenario(
		flag="export",
		label="Export",
		supported=True,
		requires=(
			needs(
				"delivery.address",
				"ibr-152-ae",
				"An export has to say where the goods went, unless they stayed in the UAE.",
				"Set a shipping address on the invoice, with its street, city and subdivision.",
			),
			needs(
				"parties.buyer.tax_registration",
				"ibr-135-ae",
				"An export has to identify the buyer.",
				"Add the customer's tax registration or its own identifier.",
			),
		),
		notes="A foreign customer does not make a sale an export, and an export does not make it zero rated.",
	),
}


def enabled(scenario: Mapping) -> tuple[str, ...]:
	return tuple(flag for flag in POSITIONS if scenario.get(flag))


def check(document: Mapping) -> list[Finding]:
	"""What is missing for the kinds of supply this invoice says it is.

	Runs before the XML is built, so the answer names a field rather than a
	rule id. The official rules still run afterwards and remain the
	authority.
	"""
	scenario = document.get("scenario") or {}
	findings: list[Finding] = []

	for flag in enabled(scenario):
		known = SCENARIOS.get(flag)
		if known is None:
			continue

		if not known.supported:
			findings.append(
				Finding(
					code=CODE_UNSUPPORTED,
					severity=Severity.ERROR,
					stage=Stage.SCOPE,
					message=f"{known.label} is not supported yet.",
					path=f"scenario.{flag}",
					repair="Take this off, or invoice it outside the app until it is supported.",
					params={"scenario": known.label, "why": known.notes},
				)
			)
			continue

		for requirement in known.requires:
			if _present(document, requirement.path):
				continue
			findings.append(
				Finding(
					code=CODE_MISSING,
					severity=Severity.ERROR,
					stage=Stage.SCOPE,
					message=requirement.message,
					path=requirement.path,
					rule_id=requirement.rule,
					repair=requirement.repair,
					params={"scenario": known.label},
				)
			)

	findings.extend(_contradictions(document, scenario))
	return findings


def _contradictions(document: Mapping, scenario: Mapping) -> list[Finding]:
	"""Combinations the rules refuse outright.

	Checked here as well as in the document type matrix, because a person
	ticking two boxes should be told at once rather than after everything
	else has been worked out.
	"""
	findings = []
	seller = (document.get("parties") or {}).get("seller") or {}
	principal = (document.get("parties") or {}).get("principal") or {}

	if scenario.get("agent_billing") and seller and principal:
		seller_id = (seller.get("tax_registration") or {}).get("value")
		principal_id = (principal.get("participant") or {}).get("value")
		if seller_id and principal_id and seller_id == principal_id:
			findings.append(
				Finding(
					code=CODE_CONTRADICTS,
					severity=Severity.ERROR,
					stage=Stage.SCOPE,
					message="An agent and the principal it bills for cannot be the same party.",
					path="parties.principal.participant",
					rule_id="ibr-176-ae",
					repair="Either take the agent flag off, or name the party actually being billed for.",
				)
			)
	return findings


def _present(document: Mapping, path: str) -> bool:
	"""Whether a dotted path holds anything at all."""
	value = document
	for part in path.split("."):
		if not isinstance(value, Mapping):
			return False
		value = value.get(part)
		if value is None:
			return False
	if isinstance(value, (Mapping, list, str)):
		return bool(value)
	return True


def capability_rows() -> list[dict]:
	"""What this release says it supports, for the release notes and the UI."""
	return [
		{
			"scenario": item.label,
			"flag": item.flag,
			"supported": item.supported,
			"requires": [requirement.path for requirement in item.requires],
			"rules": sorted({requirement.rule for requirement in item.requires}),
			"notes": item.notes,
		}
		for item in SCENARIOS.values()
	]
