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
Handling: the check records this one file as a known upstream defect, by name, exact sha256, and the exact schema error. It stays visible in every run and in the lock file. The run fails if the file changes, if it starts passing, if it fails a Schematron rule, or if the error differs. Nothing is relaxed for our own output, and no other file can inherit the allowance. Seven tests in scripts/standards/test_validate_examples.py hold that line.
Affected: this example cannot be an XSD positive fixture in P01. The serializer must follow the schema order, not this example.
Status: the defect is Verified and its handling is Verified. Reporting it upstream is Unresolved. Owner: maintainer. Report it to the publisher or confirm it against a later release. Phase P01.

## D009 XML parsing order

Choice: parse every document first with a hardened lxml parser (resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False), reject any DOCTYPE and oversized input, then hand the lxml serialization to Saxon. Never pass a user file path to Saxon.
Reason: SaxonC's own parser expands external entities declared in an internal DTD subset.
Source: docs/evidence/p00/B1-validation-harness.md F9 and Finding 2; spec 10.2.
Affected: validator wrapper (P01c), event and artifact parsing (P06).
Status: Verified.

## D010 CI definition

Choice: one GitHub Actions job named `ci` on push to develop and version-* and on pull requests: ruff check and format, the standards tooling tests, check_lock.py, then validate_examples.py plain, `--negative` and `--determinism`. Pinned: Python 3.14, ruff 0.15.22, lxml 6.1.1, saxonche 13.0.0.
Reason: spec 1.1 requires CI; the job name matches the required status check in D004.
Source: .github/workflows/ci.yml. Every step was run locally on 17-09-2026 and passed.
Affected: every pull request.
Status: Verified locally. Confirm on the first run in the pull request.

## D011 Test approach for pure domain code

Choice: standard library unittest, run with the bench env Python, no frappe import, until P01 decides otherwise.
Reason: spec 3 says domain code must not import Frappe; the bench env is the only verified interpreter.
Status: Proposed.

## D012 ERPNext already owns a UAE regional field layer

Choice: treat the ERPNext United Arab Emirates regional fields as existing native fields. Never export Custom Field or Property Setter fixtures without a module filter set to UAE e-Invoicing. Read those fields through meta and treat them as optional; rely on fieldname and existence only, never on label, fieldtype or insert_after.
Reason: ERPNext installs its own UAE fields (company_trn, vat_emirate, customer_name_in_arabic, Address.emirate, Item.is_zero_rated and is_exempt among others) when a Company with country United Arab Emirates is saved. They carry module NULL, so an unfiltered fixture export would capture them and a later migrate would overwrite them. Other Dxbitz apps already rewrite some of these rows on every migrate.
Source: docs/evidence/p00/A3-site-inspection.md sections 3.1, 3.3, 9.4, 9.6; erpnext/regional/united_arab_emirates/setup.py:10 and :246; erpnext/setup/doctype/company/company.py:336, :352 and :847.
Affected: fixtures declaration (P02), master resolution (P02/P03), install and upgrade tests (A21).
Status: Verified.

## D013 Quick entry extension composes, it does not replace

Choice: at load time, wrap or subclass whatever class is currently bound to frappe.ui.form.CustomerQuickEntryForm and SupplierQuickEntryForm. Never assign a fresh class over the global.
Reason: Frappe resolves the quick entry class by global name, so a plain assignment silently removes any other app's extension. No app on this bench overrides it today, so ours would be the first, but client sites carry many apps.
Source: docs/evidence/p00/A3-site-inspection.md section 9.1; frappe/public/js/frappe/form/quick_entry.js:19; erpnext/public/js/utils/contact_address_quick_entry.js:3 and the two binding files.
Affected: party entry (P04c), A07 and A21.
Status: Verified.

## D014 Coexistence with other apps on Sales Invoice

Choice: assume no position in doc_events order. Our handlers must not depend on running first or last, and must not fail on unknown fields other apps add.
Reason: on Dxbitz client sites the likely co-installed apps that hook Sales Invoice validate or on_submit are fta_compliance, bitz_progress_billing, milestone_invoice, hangcha, internal_pms and tht.
Source: docs/evidence/p00/A3-site-inspection.md section 9.6.
Open question: whether this app reads fta_compliance party fields when both are installed, or stays independent. Owner: P01 design. Consequence until decided: stay independent and duplicate nothing.
Status: Verified for the ordering rule; the fta_compliance relationship is Unresolved.

## D015 Verified official code values

Choice: take these values as the baseline for the P01 decision tables.
- Document types: 380 tax invoice, 480 commercial invoice, 381 tax credit note, 81 commercial credit note. Only these four exist and ibr-cl-01 enforces them. Selection follows the category rules (ibr-122-ae, ibr-123-ae, ibr-134-ae, ibr-136-ae, ibr-151-ae, ibr-157-ae), never is_return alone.
- Tax categories: S, E, O, AE, Z, N. Margin is ASCII N. The rules and every example use ASCII N; the code list file stores a Greek capital Nu at that row. Treat the code list character as an upstream typo and keep ASCII N.
- Transaction flags: eight positions carried in cbc:ProfileExecutionID as an eight character string of 0 and 1 (ibr-154-ae). Order: free zone, deemed supply, margin, summary, continuous supply, agent, e-commerce, export. ibr-157-ae forbids positions 2, 3 and 4 with document type 480 or 81.
- Electronic address scheme for the UAE TIN is 0235, permitted by ibr-cl-25 for endpoints and ibr-cl-10 for party identification.
- Every example carries CustomizationID urn:peppol:pint:billing-1@ae-1 and ProfileID urn:peppol:bis:billing.
- No rule requires the participant TIN to match the VAT registration prefix. ibr-148-ae constrains the seller non-VAT TIN format only.
Reason: spec 6.2 requires these corrections to be confirmed against the pinned publication rather than copied.
Source: docs/evidence/p00/B2-codelists-rules-notices.md sections 1 to 9 and 13, with file and line for each value.
Affected: document type matrix, tax category table, scenario flags, identity validation (all P01b).
Status: Verified.

## D016 Guideline facts that shape the contracts

Choice: carry these into the P01 and P02 contracts.
- Each tax group member holds its own participant identity and onboards separately. Which registration appears on a member's invoice is Unresolved in the guideline.
- Exchange (delivery to the buyer) and reporting (to the authority) are separate confirmations. A validation failure at the reporting corner means no reporting acknowledgement.
- Three predefined endpoint values exist: deemed supply, buyer not yet onboarded, and export without a buyer identifier. Their exact serialized form comes from the Peppol specification, not the guideline.
- The guideline states no numeric issuance deadline. The issuance and date policy needs another source.
- Retention obligations and their extensions come from the tax procedures law and its regulation, not from a single fixed number of years.
Reason: spec 14 names this guideline as the identity, scenario and storage source, and spec 1.2 forbids guessing.
Source: docs/evidence/p00/B3-mof-guidelines.md sections 1, 2, 5, 9, 12 and 13, each fact carrying a page number.
Affected: seller and party profiles (P02), routing (P01b and P06), retention policy (P07).
Status: Verified as a record of what the guideline says. The mandate dates are facts only and must never be hard-coded into invoice logic.

## D017 Site encryption key is created on first use

Choice: store every credential through the Password fieldtype or the decrypted password helper. Never assume the key exists at install time.
Reason: the site has no encryption key today. Frappe generates and writes one the first time a Password value is encrypted or decrypted.
Source: docs/evidence/p00/A3-site-inspection.md section 6; frappe/utils/password.py:223.
Affected: connection credentials (P02a), backup and restore procedure (P07c).
Status: Verified.

## D018 Currency precision on this site is unset

Choice: money tests must not assume a System Settings currency precision. The float precision is 3 and the currency precision is blank, so the framework falls back to its own rule.
Reason: spec 5.3 requires documented rounding for each value class.
Source: docs/evidence/p00/A3-site-inspection.md section 7.
Affected: money rules (P01b) and the ERP extraction fixtures (P03).
Status: Unresolved. Owner: the money rules packet. Read the precision helper in the pinned framework and cite it before writing the rounding table.

## Unresolved facts carried from spec 14

| Fact | Owner | Consequence until resolved | Phase |
| --- | --- | --- | --- |
| Frappe v15 and v14 lanes | maintainer | No v15 or v14 claim | P09 |
| Reference deployment workload and company/invoice distribution | maintainer | No capacity claim; spec 11.2 fixture is the placeholder | P00/P09 |
| Real site tax templates, accounts, currency policy | deployment setup | Mappings incomplete | P02/P03 |
| Child table Password encryption behavior | P02 | No credential path | P02 |
| Whether this app reads fta_compliance fields when co-installed (D014) | P01 | Stay independent for now | P01 |
| Currency precision fallback (D018) | money rules packet | No rounding table yet | P01/P03 |
| Which registration a tax group member shows on its invoice (D016) | maintainer with the tax adviser | Seller profile keeps both identities separate | P02 |
| Issuance and date policy source | maintainer | No issuance deadline logic | P02 |
| Reporting the Volume discount example defect upstream (D008) | maintainer | Example excluded as an XSD positive case | P01 |
| Effective applicability and mandate dates | maintainer | No applicability claim; never hard-coded | P02 |
| ASP contract facts | P10 | Simulation only | P10 |
