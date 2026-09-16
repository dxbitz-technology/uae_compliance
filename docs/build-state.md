# Build state

Phase: P00 Baseline. State: In progress. Checkpoint written 16-09-2026 when the session was stopped early on request.
Branch: p00-baseline-evidence, pushed to github.com/dxbitz-technology/uae_compliance. Default branch is develop. develop and version-* accept only pull requests with one approval and a passing ci check. Tags are immutable.
Last verified code commit: 6d9f342 on develop. The P00 evidence sits on the p00-baseline-evidence branch and is not merged.
Development site: uae.local on bench /Users/aslam/frappe-local/loc16. Frappe v16.22.0 (567c05b), ERPNext v16.26.2 (d1d3b24), Python 3.14.5, MariaDB 12.2.2, Node 24.16.0, macOS arm64 host. Not the spec 11.2 reference host.

## Packet P00 Baseline

Requirement IDs: spec 0, 1.1, 1.3, 1.4, 3, 4.3, 6.1, 6.2, 7.2 (hook facts only), 11.2 (workload record), 12.2 P00, 13 A01, 14.
Expected behavior: repository baseline, pinned sources with hashes, verified XML runtime, official positive and negative example runs, recorded decisions and unresolved facts. No application feature, DocType, hook, fixture, or UI.
Exclusions: no DocTypes, roles, fixtures, hooks, JavaScript, or v15 lane work. No provider or MoF contact. No production or destructive actions.

## What changed at this checkpoint

- Official PINT AE Billing 1.0.4 files (trn-invoice, trn-creditnote) and the UBL 2.1 XSD set are vendored unchanged under uae_compliance/standards, with NOTICES.md.
- scripts/standards/validate_examples.py and check_lock.py exist. docs/standards-lock.json lists 91 vendored files with sha256 and the run evidence.
- .github/workflows/ci.yml defines the ci job: ruff, lock check, official examples, negative cases, determinism.
- docs/evidence/p00 holds four investigator reports (site inspection, harness, code lists and rules, MoF guideline). Temporary. Fold their facts into decisions.md and delete the folder before the P00 pull request merges.

## Outcomes so far

- C1 lock hashes: Passed. check_lock.py reports 91 listed files, 0 problems (re-run by the orchestrator at checkpoint).
- C2 XSLT 2.0 runtime: Passed. SaxonC-HE 13.0 executes the official compiled Schematron XSLT in the bench env.
- C3 official examples: 29 of 30 Passed. Volume-discount-credit-note.xml fails UBL 2.1 XSD on element order inside cac:CreditNoteLine. Both Schematron layers report zero failed asserts on all 30. See D008.
- C4 negative examples: Passed, 7 of 7 fired the expected rule (ibr-002, ibr-132-ae, ibr-139-ae, ibr-cl-01, ibr-001, ibr-co-15, ibr-cl-04). Determinism run: identical on repeat.
- C5 Frappe facts with file and line: Not run. The investigator was stopped before it reported.
- C6 ERPNext facts with file and line: Not run. Same reason.
- C7 site customizations: report written (docs/evidence/p00/A3-site-inspection.md), not yet folded into decisions.md.
- C8 house style: grep for em dashes, en dashes, and tool names is clean on all files written at this checkpoint.

## Blockers

- Frappe v15 lane: no bench on this host. version-15 and version-14 branches are the maintainer's later work.
- uae.local has no hosts entry and this session has no sudo. Browser access needs the maintainer to add it or a separate serve port.
- Volume-discount-credit-note.xml XSD defect is in the published artifact. Owner: maintainer, report upstream or confirm against a later release.

## Next action

1. Redo C5 and C6: Frappe v16 lifecycle, enqueue after commit, Password storage, private File access; ERPNext tax calculation order, item_wise_tax_detail shape, Quick Entry class, regional UAE fields. Cite file and line. Write the facts into decisions.md.
2. Fold the A3, B2, B3 reports into decisions.md, then remove docs/evidence/p00.
3. Run the review pass over the records, then open the P00 pull request from p00-baseline-evidence to develop for maintainer acceptance.
4. After acceptance, start packet P01a: canonical, finding and adapter schemas with deterministic hashing, with its own packet record here.
