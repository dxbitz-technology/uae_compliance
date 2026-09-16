# Decisions

Each entry: ID, choice, reason, source, affected contract, status. Status is Verified, Proposed, or Unresolved. Unresolved entries name an owner, consequence, and affected phase.

## D001 License AGPL-3.0-only

Choice: `app_license = "agpl-3.0"`; `license.txt` holds the GNU AGPL-3.0 text verbatim.
Reason: fixed decision in spec 0. The bench scaffold defaulted to MIT.
Source: spec 0 and S12. Text fetched 16-09-2026 from https://www.gnu.org/licenses/agpl-3.0.txt, sha256 0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0.
Affected: pyproject.toml, uae_compliance/hooks.py, license.txt.
Status: Verified.

## D002 Module name UAE e-Invoicing

Choice: single module `UAE e-Invoicing`, package folder `uae_compliance/uae_e_invoicing`. The scaffold module `UAE Compliance` was renamed before first installation, so no stale Module Def exists.
Reason: fixed decision in spec 0.
Source: spec 0; frappe scrub rule for module folders (S11).
Affected: modules.txt, all app DocTypes from P02.
Status: Verified.

## D003 XML runtime candidate: saxonche 13.0.0 (SaxonC-HE)

Choice: evaluate SaxonC-HE via the `saxonche` wheel as the XSLT 2.0 engine for the official PINT AE Schematron XSLT. lxml 6.1.1 (libxslt, XSLT 1.0 only) stays for parsing and XSD.
Reason: the official Schematron files declare `queryBinding="xslt2"` and the shipped compiled stylesheets declare `version="2.0"`. libxslt and xsltproc cannot execute them. No Java runtime exists on the host, which rules out Saxon-HE Java without adding a JVM.
Source: spec 3; artifact inspection in P00b; Saxon-HE licensing page states Mozilla Public License 2.0 (https://www.saxonica.com/license/terms.xml, read 16-09-2026). Wheel evidence: saxonche-13.0.0-cp314-cp314-macosx_11_0_arm64.whl, 40.4 MB; PyPI publishes cp3x wheels for Linux x86_64 and aarch64, macOS, and Windows.
Cost: about 40 MB per platform wheel; native library; no JVM.
Affected: validation contract (P01c), pyproject dependency pin (P01), platform support statement.
Status: Proposed. Becomes Verified when P00 records official example runs on this runtime and the license note is included in NOTICES.

## D004 Repository hosting, protected main, CI

Choice: none yet. The app repository is local only, branch `main`.
Reason: spec 1.1 requires protected main, required CI, and maintainer review. Creating a remote is an outward action that needs the maintainer.
Owner: maintainer. Consequence: pull request based review cannot be recorded; commits stay local and reviewable. Affected phase: P00 onward.
Status: Unresolved.

## D005 Implementation lane order

Choice: implement against Frappe v16.22.0 (567c05b6b7b736b52f08c372a620bd19cba168d1) and ERPNext v16.26.2 (d1d3b241ae7bc21d18cf830a4bacd568e21a2a19) first. The v15 lane is unverified and not advertised.
Reason: this is the only bench available; spec 3 allows one lane first.
Source: `bench version` and `git rev-parse HEAD` in apps/frappe and apps/erpnext on 16-09-2026. Both checkouts differ from the tag only in yarn tooling files (frappe package.json packageManager line, erpnext banking/yarn.lock). No core Python or JS edits.
Affected: compatibility claims, hook facts, CI matrix.
Status: Verified for v16; v15 Unresolved (owner: maintainer; consequence: no v15 compatibility claim; phase P09).

## D006 Official artifact placement

Choice: vendor the PINT AE 1.0.4 resources (schematron, compiled XSLT, code lists, examples) and the UBL 2.1 XSD set inside the package under `uae_compliance/standards`, unchanged, with provenance in docs/standards-lock.json. PDFs from the release are recorded by hash and URL only.
Reason: spec 6.1 forbids runtime downloads and requires unchanged artifacts with provenance. Package placement lets the P01c validator load them by version.
Source: spec 6.1, 3.
Affected: validator wrapper (P01c), package size, NOTICES.
Status: Proposed. Becomes Verified when P00b records the hashes and the redistribution terms.

## Unresolved facts carried from spec 14

| Fact | Owner | Consequence until resolved | Phase |
| --- | --- | --- | --- |
| Remote repository and CI | maintainer | No PR based review record | P00 |
| Frappe v15 lane | maintainer | No v15 claim | P09 |
| Reference deployment workload and company/invoice distribution | maintainer | No capacity claim; benchmark fixture from spec 11.2 is the placeholder | P00/P09 |
| Real site tax templates, accounts, currency policy | deployment setup | Mappings incomplete | P02/P03 |
| Child table Password encryption behavior | P02 | No credential path | P02 |
| ASP contract facts | P10 | Simulation only | P10 |
