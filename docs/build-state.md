# Build state

Phase: P00 Baseline. State: In review. Acceptance is the maintainer's call, so this phase is not Accepted.
Branch: p00-baseline-evidence, open as a pull request into develop. Default branch is develop. develop and version-* take pull requests only, with one approval and a passing ci check. Tags are immutable.
Last verified code commit: the head of p00-baseline-evidence. Nothing is merged into develop yet beyond the app skeleton.
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

## Packets finished and awaiting review

Each is a branch stacked on the one before, each with its own pull request, all gates passing. Full detail lives in the pull requests and in the decisions.

| Packet | What it settled | Decisions | Notes |
| --- | --- | --- | --- |
| P01a-1 Deterministic encoding | Same meaning gives the same bytes; the business hash and the payload hash | D027 | Writing the tests found a real defect. A volatile path stopped being removed after the first row of a list, so a per line field would have leaked into the business hash. |
| P01a-2 Finding and result shape | What a check returns, and the one function that decides readiness | D028 | Checking against spec 8.1 showed the state list was short of Not checked and Stale. A passing result taken before the invoice changed now reports Stale rather than Ready. |
| P01a-3 Schema machinery | How a canonical field is described and checked | D029, D030 | Adds scripts/check.sh, which runs every gate separately, after a misread local result put a red build on the repository. |

## Packet P01a-4 The canonical invoice

State: In review on branch p01a-canonical, stacked on P01a-3.
Requirement IDs: spec 5.1 (all twelve groups, decimal strings, ISO values, identifier pairs, the business hash exclusions), 6.2 and 6.3 through the verified values in D015, 12.2 P01a, 13 A02.
Expected behavior: the whole invoice model as one declaration, plus the list of fields the business hash ignores.
Affected interfaces: everything downstream reads this and nothing reads the source document again. Once P01 is accepted, a change here is a version change.
Checks: the example invoice passes; every required group is reported when missing; unknown fields are refused anywhere; only the four verified document types and six tax categories are accepted; re-extracting the same invoice does not change its business hash while a real edit does; every volatile path names a field the model requires.
Exclusions: no money rules, no serializer, no extraction. The amounts are carried, not calculated.

Two things to flag honestly. First, the packet record was written after the work rather than before it, which the method asks for the other way round. Second, it runs to about 650 lines against the 400 the method aims for. The model is one coherent thing and splitting it at any point would leave a half model that reads as complete, so the exception is recorded here rather than taken quietly.

## Packet P01a-5 The adapter contract

State: In review on branch p01a-connector, stacked on P01a-4. Record written before the work this time.
Outcome: all gates passed, 37 tests here and 174 across the domain. The safety rule is enforced where the outcome is built rather than left to an adapter author to remember, so an unknown send cannot be marked for another attempt at all. See D035.
Requirement IDs: spec 9.1 (versioned contract, registry of trusted modules, metadata, exact operation names, normalized results, business rejection kept apart from transport and authentication failure), 8.1 (the independent outcome dimensions), 8.4 (the retry classes), 2.2 invariants I06, I11 and I12, 12.2 P01a, 13 A02.
Expected behavior: the contract a provider adapter fills in, and the shape of what an operation returns, with the safety rules that stop an unsafe resend. No HTTP, no adapter, no provider.
Affected interfaces: everything P06 builds against. The operation names and the outcome shape become a contract once P01 is accepted.
Likely files: uae_compliance/domain/connector.py, its tests, one new stage in findings.py, a decision entry.
Checks: an operation the adapter did not declare cannot be called; an outcome whose effect is unknown cannot advise repeating the same send unless the adapter declares an idempotency guarantee, and holds for a person when it does not; a business rejection is not a transport failure and not an authentication failure; a rate limit carries its wait; the four outcome dimensions stay independent and none of them can be inferred from another; a provider status code cannot reach a decision, only the record; the registry takes an adapter object and refuses an import path.
Exclusions: no HTTP transport, no real or test adapter, no simulator, no retry scheduling. Those are P06.

## Next packets

P01b decision tables and money examples. P01c reference serializer and validator wrapper.
