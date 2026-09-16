# Decisions

Each entry: ID, choice, reason, source, affected contract, status. Status is Verified, Proposed, or Unresolved. Unresolved entries name an owner, consequence, and affected phase.

## D001 License AGPL-3.0-only

Choice: `app_license = "agpl-3.0"`; `license.txt` holds the GNU AGPL-3.0 text verbatim.
Reason: fixed decision in spec 0. The bench scaffold defaulted to MIT.
Source: spec 0 and S12. Text fetched 16-09-2026 from https://www.gnu.org/licenses/agpl-3.0.txt, sha256 0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0.
Affected: pyproject.toml, uae_compliance/hooks.py, license.txt.
Status: Verified.

## D002 Module name UAE e-Invoicing

Choice: single module `UAE e-Invoicing`, package folder `uae_compliance/uae_e_invoicing`. The scaffold module was renamed before first installation, so no stale Module Def exists.
Reason: fixed decision in spec 0.
Source: spec 0; frappe scrub rule for module folders (S11).
Affected: modules.txt, all app DocTypes from P02.
Status: Verified.

## D003 XML runtime: saxonche 13.0.0 (SaxonC-HE)

Choice: SaxonC-HE through the `saxonche` wheel runs the official PINT AE Schematron XSLT. lxml 6.1.1 (libxslt 1.1.43, XSLT 1.0 only) stays for parsing and XSD.
Reason: the official Schematron files declare `queryBinding="xslt2"` and the compiled stylesheets declare `version="2.0"`. libxslt and xsltproc cannot run them. No Java runtime exists on the host.
Source: spec 3; docs/evidence/p00/B1-validation-harness.md F1 to F5; Saxon-HE terms page states Mozilla Public License 2.0 (https://www.saxonica.com/license/terms.xml, read 16-09-2026); wheels exist for Linux x86_64 and aarch64, macOS arm64, Windows, Python 3.9 to 3.14.
Cost: about 40 MB per platform wheel; native library; no JVM.
Affected: validation contract (P01c), pyproject dependency pin (P01), platform statement, uae_compliance/standards/NOTICES.md.
Status: Verified. All 30 official examples ran on it; the license is recorded in NOTICES.md.

## D004 Repository, branches, protection

Choice: remote github.com/dxbitz-technology/uae_compliance (public). Default branch `develop`. No `main`. Rulesets: `develop` and `version-*` accept only pull requests with one approval, approval of the last push, resolved review threads, and a passing `ci` check; force push and deletion blocked; admins bypass only through a pull request. All tags immutable. Squash or merge commits only; PR branches deleted after merge.
Reason: spec 1.1 requires protected release branches, required CI, and maintainer review. Public visibility fits AGPL.
Source: maintainer instruction 16-09-2026; GitHub rulesets 23560368 and 23560370.
Affected: every packet lands through a pull request; the maintainer approves and merges.
Status: Verified.

## D005 Implementation lane order

Choice: implement against Frappe v16.22.0 (567c05b6b7b736b52f08c372a620bd19cba168d1) and ERPNext v16.26.2 (d1d3b241ae7bc21d18cf830a4bacd568e21a2a19) first. The v15 lane is unverified and not advertised.
Reason: only bench available; spec 3 allows one lane first.
Source: `bench version` and `git rev-parse HEAD` on 16-09-2026. Both checkouts differ from their tags only in yarn tooling files. No core Python or JS edits.
Affected: compatibility claims, hook facts, CI matrix.
Status: Verified for v16. v15 and v14: Unresolved, owner maintainer, no compatibility claim, phase P09.

## D006 Official artifact placement

Choice: PINT AE 1.0.4 (schematron, compiled XSLT, code lists, examples) and the UBL 2.1 XSD set live unchanged under `uae_compliance/standards`, with every file hashed in docs/standards-lock.json and terms in uae_compliance/standards/NOTICES.md. The release PDFs are recorded by hash and URL only.
Reason: spec 6.1 forbids runtime downloads and requires unchanged artifacts with provenance.
Source: spec 6.1 and 3; check_lock.py result 91 files, 0 problems.
Affected: validator wrapper (P01c), package size, NOTICES.
Status: Verified.

## D007 Branch and version model

Choice: follow the Frappe app model. `develop` carries the next release with a `-dev` suffix (`__version__ = "16.0.0-dev"`). `version-16` is cut at the first production deployment and carries 16.x.y releases and tags. `version-15` and `version-14` are derived later by the maintainer. `required_apps = ["frappe/erpnext"]`. No other long-lived branches.
Reason: maintainer instruction 16-09-2026; matches frappe, erpnext and hrms.
Source: apps/hrms/hrms/hooks.py:7 for required_apps; version strings in the three core apps.
Affected: release process, CI triggers (develop, version-*), tag protection.
Status: Verified.

## D008 Official example fails UBL XSD

Choice: keep the artifact unchanged and keep the check strict. `trn-creditnote/example/Volume-discount-credit-note.xml` places cac:DiscrepancyResponse before cac:OrderLineReference inside cac:CreditNoteLine; UBL 2.1 requires the opposite order (UBL-CommonAggregateComponents-2.1.xsd:9600 and :9616). Both Schematron layers pass on the same file.
Reason: spec 1.2 forbids weakening a validator or changing expected results to pass CI.
Source: docs/evidence/p00/B1-validation-harness.md Finding 1; validate_examples.py output.
Affected: this example cannot be an XSD positive fixture in P01; the serializer must follow XSD order, not this example. The ci job fails on this case until a decision is recorded on how to mark a known upstream defect.
Status: Unresolved. Owner: maintainer. Report upstream to the PINT AE publisher or confirm against a later release. Phase P01.

## D009 XML parsing order

Choice: parse every document first with a hardened lxml parser (resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False), reject any DOCTYPE and oversized input, then hand the lxml serialization to Saxon. Never pass a user file path to Saxon.
Reason: SaxonC's own parser expands external entities declared in an internal DTD subset.
Source: docs/evidence/p00/B1-validation-harness.md F9 and Finding 2; spec 10.2.
Affected: validator wrapper (P01c), event and artifact parsing (P06).
Status: Verified.

## D010 CI definition

Choice: one GitHub Actions job named `ci` on push to develop and version-* and on pull requests: ruff check and format, check_lock.py, validate_examples.py plain, `--negative`, `--determinism`. Pinned: Python 3.14, ruff 0.15.22, lxml 6.1.1, saxonche 13.0.0.
Reason: spec 1.1 required CI; the job name matches the required status check in D004.
Source: .github/workflows/ci.yml.
Affected: every pull request. Note D008: the job fails on the official defect until resolved.
Status: Proposed until the first green or expected run is observed.

## D011 Test approach for pure domain code

Choice: standard library unittest, run with the bench env Python, no frappe import, until P01 decides otherwise.
Reason: spec 3 says domain code must not import Frappe; the bench env is the only verified interpreter.
Status: Proposed.

## Unresolved facts carried from spec 14

| Fact | Owner | Consequence until resolved | Phase |
| --- | --- | --- | --- |
| Frappe v15 and v14 lanes | maintainer | No v15 or v14 claim | P09 |
| Reference deployment workload and company/invoice distribution | maintainer | No capacity claim; spec 11.2 fixture is the placeholder | P00/P09 |
| Real site tax templates, accounts, currency policy | deployment setup | Mappings incomplete | P02/P03 |
| Child table Password encryption behavior | P02 | No credential path | P02 |
| Frappe and ERPNext source facts with file and line (C5, C6) | next session | P04 and P05 contracts cannot cite hook order yet | P00 |
| Volume-discount-credit-note.xml XSD defect (D008) | maintainer | Example excluded as XSD positive; ci red | P01 |
| Effective applicability and mandate dates | maintainer | No applicability claim; never hard-coded | P02 |
| ASP contract facts | P10 | Simulation only | P10 |
