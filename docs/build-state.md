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

## Packet P01a-1 Deterministic encoding and hashing

State: In review on branch p01a-deterministic-encoding, stacked on the P00 branch. It cannot merge before P00 is accepted.
Outcome: all checks passed. 33 tests cover the rules, including that the document hash for a known example does not drift. Writing the tests found one real defect: a volatile path stopped being removed after the first row of a list, so a per line field would have leaked into the business hash. Fixed, with the test that caught it kept. The module imports nothing from the framework, which is checked.
Requirement IDs: spec 5.1 (deterministic JSON encoding, business hash, payload hash), 5.3 (no binary floating point in domain calculations), 3 (domain owns no database, HTTP or framework import), 12.2 P01a, 13 A02.
Expected behavior: one module that turns a canonical document into the same bytes every time, hashes those bytes, and hashes a business subset with the volatile parts removed. Nothing else in the app depends on it yet.
Affected interfaces: the canonical document hash and the payload hash, which the submission record freezes in P05. Once P01 is accepted these become a contract, so changing them later needs a version bump.
Likely files: uae_compliance/domain/__init__.py, uae_compliance/domain/encoding.py, its tests, the CI job, and a decision entry.
Checks: round trip and repeat runs give identical bytes; key order does not matter to the result; floats are refused; decimals keep their scale; the business hash ignores the volatile parts and nothing else; the payload hash covers exact bytes.
Exclusions: no canonical field list, no finding schema, no adapter contract, no serializer. Those are their own packets. No framework import.

## Next packets

P01a-2 finding and result schema. P01a-3 the canonical field list. P01a-4 the adapter contract. Then P01b decision tables and money examples, P01c reference serializer and validator wrapper.
