# Build state

Phase: P00 Accepted and merged. P01a and P01b merged. P01c in progress, which finishes P01.
Branch: p01c-validator, one pull request against develop. Develop takes pull requests with a passing ci check; an approving review is not required, which the maintainer relaxed on 17-09-2026. Tags stay immutable.
Last verified code commit: develop at the merge of the scope packet, all eight gates passing, 251 domain tests.

Note on branching. P01a was originally a stack of five pull requests. Merging them bottom up deleted each base branch, so the ones above hit conflicts and were closed, and the stack came apart. No work was lost and P01a went in as one pull request. Every packet since gets its own pull request against develop and none are stacked.
Development site: uae.local on bench /Users/aslam/frappe-local/loc16. Frappe v16.22.0 (567c05b), ERPNext v16.26.2 (d1d3b24), Python 3.14.5, MariaDB 12.2.2, Node 24.16.0, macOS arm64 host. This is not the reference host in spec 11.2, so no timing here is a capacity claim.

## Packet P00 Baseline

Requirement IDs: spec 0, 1.1, 1.3, 1.4, 3, 4.3, 6.1, 6.2, 7.2, 11.2, 12.2 P00, 13 A01, 14.
Expected behavior: a pinned baseline. Official sources with checksums, a working XML runtime, official positive and negative runs, and the facts the later phases depend on, each with its source. No application feature.
Exclusions: no DocTypes, roles, fixtures, hooks, JavaScript, or v15 work. No provider or ministry contact. No production or destructive action.

## Outcomes

- C1 pinned files match their checksums: Passed. check_lock.py reports 91 files, 0 problems.
- C2 XSLT 2.0 runtime: Passed. SaxonC-HE 13.0 runs the official compiled rules in the bench environment.
- C3 official examples: Passed with one recorded exception. 29 of 30 pass the schema and both rule layers with nothing failing. The Volume discount credit note fails the UBL schema on element order inside the credit note line. The file is untouched and the check is unchanged. See D008.
- C4 negative cases: Passed. All 7 altered copies fire the expected rule. Repeat runs are identical.
- C5 Frappe facts: Passed. 199 facts with file and line, 11 proposals, none unresolved. See D021 to D025.
- C6 ERPNext facts: Passed. 104 facts plus the field inventories, with file and line. See D019 to D021 and D026.
- C7 site customizations: Passed. No third party customization on the eleven target DocTypes. ERPNext's own UAE regional layer is present because a UAE company exists. See D012.
- C8 house style: Passed. No em dashes, no tool names, no credits in anything written here.
- Harness tests: Passed. 7 tests hold the known defect guard narrow.

## What still needs a decision from the maintainer

- Accept or reject this phase.
- The Volume discount example defect: report it to the publisher or confirm it against a later release (D008).
- Spec 5.2 names a tax breakup field that version 16 no longer has. Our rule is stricter and already recorded, but the specification text needs amending (D019).
- Spec 4.1 lists a UOM code DocType that may not be needed, since UOM already carries a common code field (D026).
- Whether docs/evidence/p00 stays. It holds the five investigation reports behind the decisions. Spec 1.3 keeps the record set small, so these may be dropped once P01 has used them. They are kept for now because the field inventories and hook tables save re-deriving the same facts in P02 and P03.

## Blockers

- No Frappe v15 bench on this host, so that lane stays unverified. version-15 and version-14 are the maintainer's later work.
- uae.local has no hosts entry and this session has no sudo, so browser access needs the maintainer or a separate serve port. Not needed so far.

## Packet P01c-1 The locked validator wrapper

State: In progress on branch p01c-validator, one pull request against develop.
Requirement IDs: spec 7.1 (stage states, Schematron runs on XML and never on JSON, an absent artifact means unavailable rather than passed), 6.1 (the locked ruleset), 3 (a pinned runtime, compiled artifacts cached per worker), 10.2 (safe XML parsing), 12.2 P01c, 13 A02.
Expected behavior: run a document through the official schema and both official rule layers, and report what happened as findings and stage outcomes. This is the same path the standards harness already proves against the published examples, made available to the app.
Affected interfaces: what the canonical, schema and rule stages return during a full check.
Likely files: uae_compliance/validation/, its tests, a decision entry.
Checks: an official example passes all three layers; a broken one fails on the rule you would expect; a missing or unreadable artifact reports unavailable rather than passed; a document with a doctype is refused before the engine sees it; the compiled artifacts are built once and reused; every failed rule becomes a finding carrying its official rule id.
Exclusions: no serializer, so nothing here builds XML. That is the next packet. No network, no provider validator.

## Packet P01b-2 Scope and the document type matrix

State: Merged into develop on 17-09-2026. 30 tests; three deliberate breaks confirmed they catch things. See D038 and D039.
Requirement IDs: spec 2.1 (company modes and what each enforces), 6.2 (document codes chosen through the verified category matrix rather than from a return flag), 6.3, 12.2 P01b, 13 A05 and A09.
Expected behavior: what a company mode allows, and which document types the official rules permit for a given invoice. No extraction and no scenario conditions.
Affected interfaces: the scope decision the invoice gate reads in P04, and the document type extraction picks in P03.
Likely files: uae_compliance/domain/scope.py, its tests, a decision entry.
Checks: missing configuration reads as off; off creates no intent; preparation is advisory and never blocks; live blocks an in scope submission on a local error or on validation that could not run; the four document types follow the pinned rules, so a commercial document carries only exempt, out of scope or zero rated lines, a tax document is not made up only of exempt and out of scope lines, a seller with no registration cannot issue a tax document, and a commercial document carries no deemed supply, margin or summary flag.
Exclusions: no per scenario conditions, no serializer, no extraction. Those are the next packets. The rules here constrain the choice rather than making it, so this reports what is permitted and what contradicts, and extraction picks within that.

## Packet P01b-1 Money rules

State: Merged into develop on 17-09-2026. 29 tests on the six worked examples; three deliberate breaks confirmed the tests catch them. See D036 and D037.
Requirement IDs: spec 5.3 (money rules, the six fixtures, credit note signs, foreign currency), 2.2 invariant I01, 7.1 (the arithmetic stage returns findings), 12.2 P01b, 13 A03 and A04.
Expected behavior: check that an invoice's own numbers hold together, and say exactly where they do not. The app never recalculates tax. ERPNext is authoritative, so this reads the frozen document and reports differences.
Affected interfaces: what the arithmetic stage returns, and the money codes it raises.
Likely files: uae_compliance/domain/money.py, its tests, a decision entry.
Checks: the six fixtures from spec 5.3 give their stated controls; the three identities hold exactly, since rounding is its own field; a price discount already inside the net price is not deducted twice; tax is grouped by category and rate together, not rate alone; a foreign currency invoice keeps its own amounts and its dirham figures follow the frozen rate; an invoice paid later keeps the same bytes and hash.
Exclusions: no currency rounding table, because the pinned code list carries no minor units and spec 1.2 forbids money assumptions without evidence. No serializer, no extraction, no scope or document type decisions. Those are their own packets.

## Next packets

P01b decision tables and money examples. P01c reference serializer and validator wrapper.
