"""Write down what this release supports, from the code rather than memory.

A hand written capability list drifts. Somebody disables a scenario, or
adds one, and the document that tells a customer what they bought stays as
it was. So the parts that can be read out of the code are read out of the
code, and `scripts/check.sh` fails if the written file has fallen behind.

	python scripts/capabilities.py           # check it is current
	python scripts/capabilities.py --write   # bring it up to date
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from uae_compliance.domain.canonical import DOCUMENT_TYPES, TAX_CATEGORIES
from uae_compliance.domain.scenarios import SCENARIOS
from uae_compliance.domain.scope import Mode
from uae_compliance.validation.artifacts import (
	CUSTOMIZATION_ID,
	PINT_VERSION,
	SELF_BILLING_CUSTOMIZATION_ID,
)

TARGET = ROOT / "docs" / "what-works.md"

TYPE_NAMES = {
	"380": "Tax invoice",
	"480": "Commercial invoice",
	"381": "Tax credit note",
	"81": "Commercial credit note",
}

# Named here because none of them exists in the code to be read out of it.
# That is the point: an unimplemented thing has no switch.
NOT_BUILT = (
	("Domestic reverse charge", "The accounting has not been settled."),
	(
		"Advance invoices and retention",
		"Needs the advance, payment, balance and release documents defined together.",
	),
	(
		"Issuing a self-billed document",
		"The rules are held and a self-billed document can be checked. Issuing one on a supplier's behalf is its own workflow and is not built.",
	),
	("Receiving by callback", "Documents are collected by asking. Nothing listens for a push yet."),
)


def rows() -> list[str]:
	out = []
	out.append("# What this release does\n")
	out.append(
		"Generated from the code by `scripts/capabilities.py`. A hand written\n"
		"list of this kind drifts away from the software, so this one is read\n"
		"out of it and checked on every build.\n"
	)
	out.append(
		f"Rules: PINT AE Billing {PINT_VERSION}, `{CUSTOMIZATION_ID}`, and PINT AE\n"
		f"Self-Billing {PINT_VERSION}, `{SELF_BILLING_CUSTOMIZATION_ID}`.\n"
	)

	out.append("## Documents\n")
	out.append("| Code | Document |")
	out.append("| --- | --- |")
	for code in DOCUMENT_TYPES:
		out.append(f"| {code} | {TYPE_NAMES.get(code, code)} |")
	out.append("")
	out.append(
		"The type is chosen from the tax categories on the document and whether\n"
		"the seller is registered, not from whether the source is a return.\n"
	)

	out.append(
		"Self-billed documents, 389 and 261, are checked against their own\n"
		"published package. This release can read and validate one. It cannot\n"
		"issue one, which needs the self-billing workflow in P12.\n"
	)

	out.append("## Tax categories\n")
	out.append(", ".join(TAX_CATEGORIES) + ". Margin is the letter N.\n")

	out.append("## Kinds of supply\n")
	out.append("| Supply | Supported | What it needs |")
	out.append("| --- | --- | --- |")
	for item in SCENARIOS.values():
		needs = ", ".join(sorted({r.path for r in item.requires})) or "Nothing beyond an ordinary invoice"
		out.append(f"| {item.label} | {'Yes' if item.supported else 'No'} | {needs} |")
	out.append("")
	for item in SCENARIOS.values():
		if not item.supported and item.notes:
			out.append(f"{item.label} is off because: {item.notes}\n")

	out.append("## Not built\n")
	out.append("| Thing | Why not |")
	out.append("| --- | --- |")
	for label, why in NOT_BUILT:
		out.append(f"| {label} | {why} |")
	out.append("")
	out.append(
		"An unsupported case is refused in Live rather than approximated. There\n"
		"is no switch that turns an unfinished one on.\n"
	)

	out.append("## Company modes\n")
	out.append("| Mode | What happens |")
	out.append("| --- | --- |")
	out.append(f"| {Mode.OFF.value} | Nothing. No record, no notice, no field. |")
	out.append(f"| {Mode.PREPARATION.value} | Collects and checks. Sends nothing. |")
	out.append(f"| {Mode.LIVE.value} | Blocks a submission that would fail, and queues what passes. |")
	out.append("")
	out.append("A company nobody configured is Off.\n")

	out.append("## Buying\n")
	out.append(
		"Documents suppliers send are collected by asking the provider, read,\n"
		"matched to a supplier by tax number or network address, and kept. One\n"
		"can then be entered as a draft purchase invoice, which a person\n"
		"submits.\n"
	)
	out.append(
		"No supplier is created from an arriving document, no item is invented\n"
		"to make a line fit, and nothing posts on its own.\n"
	)

	out.append("## Sending\n")
	out.append(
		"Against the local simulator only. No real provider has been connected\n"
		"and no production certification is claimed.\n"
	)
	return out


def main() -> int:
	wanted = "\n".join(rows()).rstrip() + "\n"
	if "--write" in sys.argv:
		TARGET.write_text(wanted)
		print(f"wrote {TARGET.relative_to(ROOT)}")
		return 0

	if not TARGET.exists():
		print(f"{TARGET.relative_to(ROOT)} is missing. Run with --write.")
		return 1
	if TARGET.read_text() != wanted:
		print(
			f"{TARGET.relative_to(ROOT)} no longer matches the code. Run "
			"`python scripts/capabilities.py --write`."
		)
		return 1
	print("what-works.md matches the code")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
