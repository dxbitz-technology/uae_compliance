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
Handling: the check records this one file as a known upstream defect, by name, exact sha256, and the complete set of schema errors it is known to produce, with their count. Matching only one error would have let a second, unrelated failure ride along on the record, so every reported error must be one already written down and the count must agree. It stays visible in every run and in the lock file. The run fails if the file changes, if it starts passing, if it fails a Schematron rule, or if the error differs. Nothing is relaxed for our own output, and no other file can inherit the allowance. Nine tests in scripts/standards/test_validate_examples.py hold that line, including the recorded error accompanied by an unrelated one.
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
- Document types: 380 tax invoice, 480 commercial invoice, 381 tax credit note, 81 commercial credit note. These four are the whole of the billing family, and ibr-cl-01 enforces them. Two more exist in the self-billing family, 389 and 261, which the package we pinned rejects. Spec 2.1 puts them in P12, and their artifacts are not vendored. Selection follows the category rules (ibr-122-ae, ibr-123-ae, ibr-134-ae, ibr-136-ae, ibr-151-ae, ibr-157-ae), never is_return alone.
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

## D019 ERPNext v16 replaced the per item tax breakup field

Choice: do not read `item_wise_tax_detail`. It does not exist in this version. Compute every per line tax figure in our own code from the row net amount and the effective rate, then reconcile the total to the invoice tax rows.
Reason: in v16.26.2 the JSON field is gone from Sales Taxes and Charges. The parent now carries a child table `item_wise_tax_details` of DocType `Item Wise Tax Detail` with item_row, tax_row, rate, amount and taxable_amount. It looks like the per line ledger we want, and it is not one. Its amounts are company currency, produced as deltas of a running cumulative total so the sum reconciles to the base tax amount after discount. The display helper that still groups by item code divides the taxable amount back by the exchange rate but leaves the tax amount in company currency.
Source: erpnext/accounts/doctype/sales_taxes_and_charges/sales_taxes_and_charges.json (field absent, verified by field list); erpnext/accounts/doctype/item_wise_tax_detail/item_wise_tax_detail.json; erpnext/accounts/doctype/sales_invoice/sales_invoice.json:2217; erpnext/controllers/taxes_and_totals.py:635 to 673 and :1262; docs/evidence/p00/A2-erpnext-facts.md.
Affected: the source map (P03a) and the money fixtures (P03b).
Spec impact: section 5.2 warns against `item_wise_tax_detail[item_code]`, which describes the version 15 field. The warning still holds in spirit and its wording is now out of date. Owner: maintainer, to amend the specification. The rule we follow is stricter: neither shape is a per line ledger.
Status: Verified.

## D020 Which ERPNext figures are authoritative for money

Choice: read `tax_amount_after_discount_amount` as the tax figure for a tax row, never `tax_amount`. Treat a discount applied on the grand total as its own case with its own fixtures.
Reason: when the discount applies to the grand total, the second calculation pass deliberately leaves `tax_amount` untouched and rebuilds only the after discount figure, so `tax_amount` is stale. Cash and non trade discount on the grand total skips line distribution altogether, so the plain tax exclusive plus tax identity does not hold for it.
Source: erpnext/controllers/taxes_and_totals.py:272 and :455 (both guard on the discount applied and grand total condition), :869, and the calculate entry path.
Affected: money rules (P01b), extraction (P03b), the reconciliation identities in spec 5.3 which need an explicit carve out for that case.
Status: Verified.

## D021 ERPNext arithmetic is float, and rounding is a site setting

Choice: our domain code uses Decimal as the specification requires. Every money fixture records the site rounding method along with its expected values, and extraction compares against the posted source rather than recomputing it.
Reason: ERPNext uses plain Python floats through a precision helper, with no Decimal anywhere. The rounding method is a runtime choice in System Settings among several variants, so two sites holding identical data can post different figures.
Source: erpnext/controllers/taxes_and_totals.py throughout; frappe/utils/data.py:1239.
Affected: money rules (P01b), fixtures (P03), the A03 and A04 acceptance cases.
Status: Verified.

## D022 The queue is not a record, so the outbox is mandatory

Choice: the submission row is the only record that work exists. Enqueue is a nudge. Never let a hook try to commit.
Reason: the after commit callback runs once the commit has already landed and a new transaction has begun, it returns no job handle, and a queue failure surfaces outside the request error handling. Document event handlers run with transaction control disabled, so a commit inside a hook is a silent no operation that only warns.
Source: frappe/database/database.py:1178 and :1190; frappe/utils/background_jobs.py:207; frappe/app.py:144; frappe/model/document.py:1581. Full detail in docs/evidence/p00/A1-frappe-facts.md.
Affected: the durable worker boundary (P05b and P06), acceptance case A11.
Status: Verified.

## D023 Credentials in child rows work, with three gaps we must close

Choice: keep provider credentials in child rows, and handle the cleanup ourselves. Delete the stored secret explicitly when a credential row is removed and when the parent is deleted. Never export these DocTypes as fixtures.
Reason: the framework saves and reads child row passwords keyed by child DocType and row name, and row names are stable across saves, so the storage itself is sound. Three gaps: removing a child row deletes it with a plain delete that leaves the stored secret behind; deleting the parent clears only the parent's own secrets while child rows go through a plain delete; and the fixture export strips the row name, which would orphan the secret permanently.
Source: frappe/model/document.py:830, :645 and :1111; frappe/model/delete_doc.py:201 and :266; frappe/core/doctype/data_import/data_import.py:350.
Affected: connection credentials (P02a), acceptance case A20. This closes the open question carried from spec 14 on child credential storage.
Status: Verified.

## D024 Native file permissions are not enough for evidence

Choice: do not rely on the framework's file permission alone to protect submitted evidence. Bind every artifact to its record, check access against that record, and block replacement and deletion of evidence in our own code.
Reason: the file permission check returns true for the uploading user before it delegates to the attached document, and it does so for every permission type including delete. There is no dedicated method that flips a file to public either, because the private flag is an ordinary field, so any write path that reaches it moves the bytes into the public directory.
Source: frappe/core/doctype/file/file.py:953, :175 and :312.
Affected: the artifact contract (P05a), permissions and evidence (P07b), acceptance cases A19 and A20.
Status: Verified.

## D025 Small traps to carry forward

- Claiming a lease must use dictionary filters. The values helper hardcodes a blocking wait when filters arrive as a list, so a no wait claim silently turns into a blocking one. frappe/database/database.py:658 against :665. Affects P05b.
- The exchange rate helper can make an outbound network call. It must never run inside validation, preview or a document hook. erpnext/setup/utils.py:108. Affects P03b and invariant I08.
- ERPNext's own UAE override decides its zero rated flag by comparing the company country with the customer address country. That is the blanket export rule the specification rejects, so the flag is never evidence of tax treatment. Affects P03 and spec 6.2.
- Validation does not run on an update after submit, yet several invoice fields allow it, and payment updates change the outstanding amount and status by direct writes with no document event. Reconciliation cannot rely on an event for those. frappe/model/document.py:1361. Affects P05c and P07a.
- The reverse charge field ERPNext installs is on purchase documents only, and its emirate field stores full names rather than codes. Affects P02b.
- The quick entry bindings for Customer and Supplier are the same class object, so replacing one replaces both. This reinforces D013.
Status: Verified, each with its own citation in docs/evidence/p00/A1-frappe-facts.md and A2-erpnext-facts.md.

## D026 UOM codes may not need a new DocType

Choice: before building the planned UOM code mapping, use the native UOM common code field.
Reason: UOM already carries a common code field of length three, described as the CEFACT code. Spec 4.3 says to reuse a native field where one exists. The value is not validated and is often blank, so the mapping still needs a fallback and a validation finding when it is missing or not in the pinned list.
Source: erpnext/setup/doctype/uom/uom.json; docs/evidence/p00/A2-erpnext-facts.md.
Affected: the storage contract (P02c). Spec 4.1 lists a `UAE Peppol UOM Code` DocType; this may reduce to a fallback table or disappear.
Status: Proposed. Decide in P02c with the maintainer, since it changes a listed DocType.

## D027 Deterministic encoding rules

Choice: encode a canonical document as UTF-8 JSON with keys sorted by code point, array order kept as given, no spaces in separators, and non-ASCII written as itself. Numbers are Decimal written as plain strings with the scale the caller set. Floats are refused anywhere in the document, as are sets, raw bytes and non-string keys. A key whose value is None is left out, because None means absent. A value that is present but deliberately does not apply is the not applicable marker, written as a single reserved key. The encoding owns that marker, because what matters about it is how it is written down and read back. Absent, zero, empty and not applicable all produce different bytes, and a test holds that.
Reason: spec 5.1 requires a documented encoding, and spec 5.3 forbids binary floating point in domain calculations. Refusing a float at the boundary is how that rule is enforced rather than merely stated.
Notes: the encoding carries a version. A submission freezes these hashes, so any later change to the rules is a contract change that raises the version rather than editing a stored value. The business hash takes the volatile paths from its caller, because which fields move on their own belongs to the canonical model. The payload hash covers exact bytes and accepts nothing else. A path passed to the business hash that matches no field is an error, so a renamed field cannot quietly stop being excluded.
Source: uae_compliance/domain/encoding.py with 33 tests beside it. The module imports nothing from the framework, which is checked.
Affected: the canonical hash and the payload hash frozen in P05, the approval identity in spec 8.2, acceptance case A02.
Status: Verified for the rules as written. The volatile path list itself arrives with the canonical model in P01a-3.

## D028 Finding and result shape, and the readiness rule

Choice: a check returns a finding, never a sentence. A finding carries a stable code of ours, the severity, the stage, where the problem is, a plain fallback message, the message parameters as separate values, the official rule id when an official rule failed, and the named repair. An error must name its repair or it cannot be built. A finding may name another finding as its cause, and a consequence is held back from the list until its cause is dealt with, so one missing value does not bury the thing to fix.
A result carries the level, when it ran, the input and master fingerprints, the ruleset version, whether the invoice is in scope, one outcome per stage, and the findings. A stage that is not passed or failed must say why, so a missing check cannot read as a clean one. Only the provider validator stage may be skipped, and skipping it can never excuse a rule above it.
Readiness: the full vocabulary is Not checked, Stale, Further checks required, Needs details, Ready locally, Unavailable, Out of scope. The rule lives in one function and nothing re-derives it. No result means Not checked. A result taken against different inputs or masters is Stale and says nothing about the invoice as it stands, even though it passed at the time. Only a current Full result with every required stage passed and no error reaches Ready locally. A Fast pass says further checks are required. Out of scope goes stale like any other result: the company is a field on the invoice and its policy can change, so a scope decision taken against different inputs says nothing about the invoice as it stands.
The optional provider validator counts once it has been attempted. Skipped means it is not installed and never ran, which does not block. Unavailable, failed, or listed as not run all mean its answer matters and is missing, so none of them reaches Ready locally. Review caught this: an engine that failed was being read as a pass.
Reason: spec 7.1 for the contents and the readiness rule, spec 8.1 for the working readiness states, spec 1.4 for stable codes and translatable strings.
Source: uae_compliance/domain/findings.py with 36 tests beside it. Imports nothing from the framework, which is checked.
Affected: everything the validation service returns, the working record in P04, the submission gate in P05. The codes become a contract once P01 is accepted.
Status: Verified for the shape and the rule. The code list itself arrives with the rules in P01b and P03.

## D029 The canonical model is written as data

Choice: describe each canonical field as data, with its kind, whether it is required, its decimal scale, its permitted values where it is a code, and whether it may be marked as not applicable. One check reads a document against that description and returns findings at the canonical stage. Classes would state the same thing in more places.
Reason: spec 5.1 asks for an executable schema, for unknown fields to be refused at controlled boundaries, and for intentional extensions to be versioned. A declaration gives all three in one place, and the same declaration produces the path that a finding points at.
Rules the machinery enforces: an unknown field is refused rather than ignored; a required field that is missing is reported with its path; a decimal carrying more places than declared is refused rather than quietly rounded, because rounding belongs to the money rules where it is deliberate; dates, currencies and countries are checked for shape; an identifier needs both its scheme and its value; a check reports everything in one pass rather than stopping at the first problem.
Absent, zero and not applicable stay apart. A key left out means nothing is known. Zero is an ordinary amount. Not applicable is the marker the encoding defines, permitted only where the schema allows it, and it has a written form so a document carrying one can still be stored and hashed. None is refused everywhere, because it reads as any of the three. Review caught that the schema accepted the marker while the encoder refused it, which would have left a valid invoice that could not be saved; the marker now lives with the encoding and a round trip test covers it.
Extensions sit in their own part of a schema and cannot reuse a core field name, so a local addition can never quietly redefine a canonical field.
Source: uae_compliance/domain/schema.py with 39 tests beside it. Imports nothing from the framework, which is checked.
Affected: the canonical field list in P01a-4, the extraction boundary in P03, anything that accepts a document from outside.
Status: Verified for the machinery. The field list itself is the next packet.

## D030 One command runs every gate

Choice: scripts/check.sh runs each CI step separately, prints pass or fail per step, and exits non-zero if any failed. It is the way to check work locally before pushing.
Reason: a tool can print a reassuring last line and still exit with a failure. Reading the tail of a command's output rather than its exit code sent a red build to the repository on 17-09-2026. A runner that reports per step removes the chance to misread.
Source: scripts/check.sh, referenced from AGENTS.md. It was tested against deliberately broken code and reported three failing steps with exit 1.
Affected: the working method in spec 1.1, which requires checks to be recorded against the reviewed commit.
Status: Verified.

## D031 The canonical invoice, version 1

Choice: one declaration holds all twelve groups from spec 5.1 as fourteen top level fields. Provenance, context, document, parties, lines, tax breakdown, document allowances, document charges, totals, references, payment, delivery, scenario, exchange rates. Document allowances and charges sit at the top level rather than inside totals, because they are rows with their own tax treatment rather than a single figure.
Decisions carried in as verified values, from D015: only 380, 480, 381 and 81 are accepted as document types; the tax categories are S, E, O, AE, Z and N, with margin as the letter N; the customization and profile identifiers are carried as fields rather than assumed.
Scenario flags are eight named booleans in the published order, all required, so an extractor has to state each one instead of leaving a scenario silently off. The official positional string is built from them at serialization and never stored, so nothing in the model depends on those positions.
A party may hold a second tax registration alongside its own, which is how a foreign buyer with a UAE registration is represented without either value overwriting the other. See D016.
An exchange rate must say where it came from. A missing source is a finding, never a reason to invent a rate.
Reason: spec 5.1 requires an executable schema covering these groups before any adapter is written.
Source: uae_compliance/domain/canonical.py with 34 tests beside it.
Affected: extraction (P03), the serializer (P01c), the frozen snapshot (P05). A change after acceptance is a version change.
Status: Verified for the shape. The rules that read it arrive in P01b.

## D032 Schema scales are a safety net, not the rounding rule

Choice: the model allows up to 4 decimal places on an amount, 6 on a price, quantity or percentage, and 9 on an exchange rate. A per unit price discount carries price precision rather than amount precision: the official rule requires net price to equal gross price minus the discount exactly, so a narrower scale on the discount would make price combinations the model allows impossible to reconcile. Review caught that. These are wide enough to hold what a real invoice carries and narrow enough to catch a value that arrived from floating point arithmetic with seventeen places.
Reason: what each currency actually rounds to is a money decision that needs the currency in hand, and spec 5.3 asks for rounding to be documented separately per value class. Encoding that policy in the schema would put it in the wrong place and would break on a currency with three minor units.
Affected: the money rules in P01b, which own the real per currency rounding and check it at the arithmetic stage.
Status: Proposed. P01b confirms the per currency rule and may narrow these.

## D033 What the business hash ignores

Choice: one path today, the extraction timestamp. Every path on that list must name a field the model requires, and a test enforces it.
Reason: the exclusion list is strict and raises when a path matches nothing, which is what stops a renamed field from quietly slipping back into the hash. That strictness only works if the excluded fields are always present.
Note: the source fingerprint stays inside the hash. It says which source the document was built from, so it belongs to what was agreed rather than to the noise around it. Payment collected after issue is not in the model at all, so there is nothing to exclude; the prepaid amount in the totals is frozen at issue and is part of the agreement.
Source: uae_compliance/domain/canonical.py, VOLATILE_PATHS, with its tests.
Affected: the frozen submission and the approval identity in P05.
Status: Verified.

## D034 The adapter contract

Choice: an adapter declares itself and a capability it does not declare does not exist. The declaration carries the provider key, the contract and adapter versions, the environments, the exact operations from spec 9.1, the request format, how it authenticates, what it promises about sending the same thing twice, whether a submission can be searched for by key, how its events are authenticated and whether they carry order, whether it serves artifacts, and how it pages.
An operation returns four things that are decided separately: what happened to the request, whether the effect actually landed on the other side, what to do next, and the four acknowledgement dimensions from spec 8.1. Completeness is answered against the route, which says which acknowledgements this document actually needs. A step may be marked as not applicable only where the route says it does not apply, so a document cannot read as complete having never been reported. A provider's own status code rides along for the record and nothing in this app may branch on it.
The registry takes an adapter object that is already imported. A name or an import path is refused, so nothing in configuration or in a request can make this app import and run arbitrary code.
Reason: spec 9.1, spec 8.1 and the retry classes in spec 8.4, with invariants I06, I11 and I12.
Source: uae_compliance/domain/connector.py with 37 tests beside it. Imports nothing from the framework.
Affected: everything P06 builds. The operation names and the outcome shape become a contract once P01 is accepted.
Status: Verified for the shape. Real provider facts stay unresolved until P10, as spec 14 says.

## D035 An ambiguous send is never repeated on a guess

Choice: when the effect of a send is unknown, the contract refuses to advise sending the same payload again. What happens instead depends on what the provider has actually promised. If it promises idempotency, or if a submission can be searched for by key, the outcome is reconciled first. If it promises neither, the work is held for a person.
Reason: this is invariant I06 and the ambiguous rows of spec 8.4. A late invoice is a nuisance. A duplicate legal invoice is a problem for the client and for their tax position. The decision cannot rest on an adapter author remembering the rule, so the contract refuses the unsafe combination at the point the outcome is built.
The same rule runs the other way. Once the provider has taken the document, the contract refuses to advise sending it again at all. Review caught that a successful, applied submit could still carry a resend instruction, which a worker following the contract would have obeyed. Whatever is still missing, a status or an artifact, is fetched by its own operation.
Related rules the contract holds: a success must report the effect as applied and a timeout may only report it as unknown, so no adapter can quietly claim certainty it does not have. A transport failure may be either, and has to say which, because a refused connection and a lost response are different situations. A rejected document needs a correction rather than another attempt. A rate limit must carry its wait and is waited out rather than corrected. Stale credentials are their own case and are never reported as a rejected document.
Source: uae_compliance/domain/connector.py, the effect table and the advice check, with tests covering each combination.
Affected: the worker in P06, acceptance cases A13, A14 and A15.
Status: Verified.

## D036 The money rules check, they do not calculate

Choice: nothing in the money rules works out what the tax should be. ERPNext already did that and its figures are the ones that get posted. These rules read the frozen document and report anywhere it does not add up, naming the stated figure and the expected one so someone can look at the source.
Reason: invariant I01 makes ERPNext authoritative for accounting values, and spec 5.3 says a difference from the frozen source is explained rather than corrected. Recalculating would only produce a second opinion nobody asked for.
The three identities are exact. The amount before tax is the lines less allowances plus charges. The amount after tax adds the tax. Payable takes off the prepaid amount and adds the rounding. Rounding is its own field on the document, so a real invoice has nothing left over and any gap is a genuine disagreement rather than a tolerance to widen.
Tax groups by category and rate together, never by rate alone, because a zero rated supply and an exempt one both carry no tax and are not the same thing on a return.
A price discount already inside the net price is never taken off again. Taking it twice is the ordinary way an invoice ends up short, so there is a test for it.
Source: uae_compliance/domain/money.py with 29 tests, built on the six worked examples in spec 5.3. Every expected figure in those tests was worked out from the specification table rather than read back from the code. Three deliberate breaks were introduced to confirm the tests catch them.
Affected: the arithmetic stage (P03), acceptance cases A03 and A04.
Status: Verified.

## D037 No currency rounding table

Choice: the money rules carry no list of what each currency rounds to. Every check works at the precision the document itself used.
Reason: the pinned currency code list holds only the code and the name, with no minor units, and spec 1.2 forbids a money assumption with nothing behind it. Inventing a table would be exactly that, and it would be wrong for the currencies with three minor units.
Consequence: these rules never decide that a figure is wrongly rounded. They only report that two figures in the same document disagree. Whether a currency was rounded correctly needs a source we do not have yet.
Affected: this supersedes the open question in D018 for the purposes of these checks, and narrows D032. A real per currency rule is still unresolved and belongs with the deployment setup, which knows the company and its currency.
Status: Verified as the choice. The per currency rule stays Unresolved, owner maintainer, affected phase P03.

## D038 Company mode and what each one enforces

Choice: three modes. Off enforces nothing and creates no work that could be transmitted. Preparation advises and still creates no transmittable work. Live enforces, and creates work. A stored value that is unset or unrecognised reads as Off, so a company nobody configured behaves exactly as it did before the app was installed.
A live company blocks an in scope submission when there is a local error, and equally when the checks could not run. Not knowing is not the same as being fine, and treating an unavailable validator as a pass is how an unchecked invoice reaches a tax authority.
Reason: spec 2.1, and its rule that missing configuration means Off.
Source: uae_compliance/domain/scope.py with tests, including a mutation check that an unknown mode is not read as live.
Affected: the invoice gate in P04, acceptance case A09.
Status: Verified.

## D039 The document type follows the category matrix

Choice: the four codes are tied to the tax categories on the document and to whether the seller is registered, not to whether the source is a return. The rules constrain rather than decide, so the domain reports which types are permitted and where a document contradicts itself; extraction picks within that.
The rules applied, each cited where it is used: a commercial document carries only exempt, out of scope or zero rated lines (ibr-122-ae); a tax document is not made up only of exempt and out of scope lines (ibr-151-ae); a seller with no registration cannot issue a tax document (ibr-134-ae); a commercial document carries no deemed supply, margin or summary flag (ibr-157-ae).
A consequence worth stating: an unregistered seller with standard rated lines has no permitted type at all. The facts contradict each other and someone has to resolve it rather than the app picking a code that fits neither.
Reason: spec 6.2 requires selection through the verified category matrix rather than from a return flag alone. The matrix itself was read from the pinned publication in P00 and recorded in the evidence.
Source: uae_compliance/domain/scope.py with 30 tests. Every finding carries the published rule id, so a reader can check rather than trust.
Affected: extraction (P03), the serializer (P01c), acceptance case A05.
Scope: the billing family only. Self-billing adds 389 and 261 at P12, on a separate specialisation this app has not pinned.
Status: Verified.

## D040 The validator reports three layers separately

Choice: the schema, the shared rule layer and the jurisdiction layer each report their own outcome. A failed official rule becomes a finding carrying that rule's own id and its own words, so a reader can look the rule up rather than take our paraphrase.
A layer that could not run reports unavailable, never passed. An invoice nobody managed to check is not an invoice that passed, and treating the two alike is how an unchecked document reaches a tax authority. A missing file, an engine that will not start and a rule layer that will not compile all land there.
Reason: spec 7.1 for the stage states and for Schematron running on XML rather than on our own structures; spec 6.1 for the locked ruleset.
Source: uae_compliance/validation/ with 15 tests that run the real published files, not a stand-in. A published invoice and credit note pass all three layers; broken copies fail the rule you would expect, by id.
Affected: the full check in P03 and P04, acceptance case A02.
Status: Verified.

## D041 One hardened read, before anything else touches the document

Choice: every document is parsed once by a hardened reader that refuses a document type declaration and anything oversized. Only what comes back out of that is handed onward, and the rule engine never sees a file from disk.
Reason: an XML document can instruct a parser to pull in other files or fetch a URL, which on a document from outside is a way to read private files or make the server call somewhere it should not. The rule engine has its own parser that does expand entities, so it is only ever given text the hardened read already accepted.
One exception, and only one: the official schema is split across files that reference each other by relative path, so it is read from its path rather than from bytes. That is safe because those files ship with the app and their checksums are recorded, so they are not something a document brought with it. The parser still refuses to reach the network.
Source: uae_compliance/validation/safe_xml.py, with a test that feeds it a document trying to read a system file and confirms nothing ran.
Affected: every document boundary, including events and artifacts in P06. This carries out D009.
Status: Verified.

## D042 One place writes the XML

Choice: every document the app sends is written by one serializer. Element order follows the schema rather than the published examples, because one of those examples fails its own schema on ordering. The eight position scenario string is built here and nowhere else, so nothing in the app depends on those positions.
Reason: spec 5.1 for the reference serializer, spec 6.3 for keeping the scenario flags as named booleans internally and producing the official string only at serialization.
How it is judged: not by whether the XML looks right to us. Every passing test builds an invoice, writes it out, and runs the real published schema and both rule layers over the result. An ordinary invoice, an ordinary credit note, a volume discount credit note, a goods line, a services line and a line that is both all come back with nothing.
Source: uae_compliance/validation/serializer.py with 22 tests. Four deliberate breaks were caught, including reversing the scenario positions and classifying services under the goods scheme.
Affected: extraction (P03), the frozen payload (P05).
Status: Verified for the ordinary invoice and credit note, which is the minimum scope in spec 2.3. The advanced scenarios each need their own conditions and belong to P08.

## D043 Three gaps the rules found in the canonical model

Choice: building the serializer against the real rules surfaced three things the model was missing, and all three are now in it.
- A document carries a unique identifier separate from its legal number. The rules require it and it stays with the document wherever it travels.
- A line carries a list of classifications rather than one. Goods are classified under one scheme and services under another, they land in different elements, and something that is both needs both.
- An identifier may name the authority that issued it. The rules require it for a trade licence, and it means different things per scheme: the issuing authority for a licence, the issuing country for a passport. So it is carried rather than derived.
Reason: each came from a rule failing against real output, not from reading the model and imagining what might be missing. This is the point of writing the serializer before extraction.
Affected: the canonical model, its version, and extraction in P03. These are contract changes made before P01 was accepted rather than after.
Status: Verified.

## D044 A connection's provider and environment settle once it is used

Choice: a provider connection may change freely until something has gone through it. After that its provider and its environment are fixed, and a different one needs a new connection. Rotating the credentials on the same connection stays allowed and expected.
Reason: old submissions stay bound to the connection that carried them, so repointing one at a different provider, or from sandbox to production, would quietly rewrite what those records mean. Spec 8.2 allows credential rotation on the same identity and requires a new connection for a change of provider or environment.
Source: uae_compliance/uae_e_invoicing/doctype/uae_peppol_asp/, with site tests covering both directions and a deliberate break confirming they catch it.
Affected: the worker in P06, and the connection evidence a submission records in P05.
Status: Verified.

## D045 The app deletes its own credentials

Choice: the connection removes the stored secret of every credential row a save drops, and takes all of them when the connection itself is deleted.
Reason: this carries out what D023 found. Child row passwords store and read correctly, but the framework deletes a removed row without its secret, and deleting a parent clears only the parent's own. Left alone, a secret would outlive the record that explained what it was for, and would sit in the table after the connection it belonged to was gone.
The cleanup is worked out from the document as it was before the save, so it only ever touches this connection's own rows. An earlier attempt read the whole credential table, which would have reached other connections' rows.
Source: site tests covering a dropped row, a deleted connection, and a drop that must leave the other credentials alone. Breaking either path fails those tests.
Affected: acceptance case A20. It also means these DocTypes must never be exported as fixtures, since the export strips the row name the secret is keyed by.
Status: Verified.

## D046 Site tests run separately from the rest

Choice: the domain and validation packages run on plain Python with no site. The DocType tests need a database and run through bench. The local gate runner keeps them apart and says plainly that it did not run the site tests.
Reason: a site test swept into the plain runner errors for want of a database, which reads as the code failing when it is the harness that is missing. Spec 13 says a skipped database test stays Not run and blocks the gate that needs it, so it has to be visible rather than absorbed.
Consequence, stated rather than glossed: the required `ci` check does not yet run the site tests, so P02's evidence is currently proved locally only. A second workflow that stands up a database is being built alongside. Until it passes, every site test here is Not run in CI.
Status: Verified as the arrangement. The CI harness is Unresolved, owner: the workflow now in progress, affected phase P02.

## D047 A claim and evidence never touch

Choice: what somebody tells us and what a lookup found are separate fields on both the seller and the party profile. A person may record that a party says it is on the network. Only a lookup may record it as verified, and the verified fields are read only on the form and refused in the controller.
Reason: spec 4.1 says a manual selection must never set verified. Answering a question about yourself is not evidence, and an invoice held back for missing evidence is a nuisance while an invoice sent on a false claim is the client's problem.
Source: both profile controllers, with site tests covering the refusal by hand and the lookup path being allowed.
Affected: routing in P06, which may only act on evidence.
Status: Verified.

## D048 Profiles save while they are incomplete

Choice: a seller profile saves with nothing but a label, and a party profile with nothing but the party. A seller's internal name is one you choose and does not depend on an identifier it may not have yet.
Reason: spec 4.1 requires it, and the reason is practical. The details usually arrive after the first invoice does, so refusing the save would leave nowhere to record what is known so far.
What is still refused: a company bound to two sellers, a second profile for the same party, and going live without a date it takes effect from.
A note on one of those. The uniqueness check for a new record must not exclude its own name, because a new record shares its name with the one it is about to collide with. That was a real defect here, found when the database caught the duplicate instead of the friendly message. The database remains the actual guarantee; the check exists so a person sees which record already has it.
Source: uae_compliance/uae_e_invoicing/doctype/, 19 site tests.
Affected: P04, where these records are created from the party forms.
Status: Verified.

## D049 No UOM code DocType

Choice: use the native common code field on UOM rather than adding a DocType for it. A unit with no code is reported as a finding for somebody to fill in on the unit itself, not guessed at.
Reason: spec 4.3 says to reuse a native field where one exists, and P00 established that UOM already carries one. A second record for the same fact would be a second source of truth, which spec 4.2 warns against. This closes the open question in D026.
Consequence: the mapping quality depends on a native field that is often blank, so the finding for a missing code has to be clear about where to fix it.
Affected: spec 4.1 lists a `UAE Peppol UOM Code` DocType that this decision does not build.
Status: Verified. The maintainer accepted this on 18-09-2026. If a unit's native code turns out to be blank too often on a real site, a fallback table can be added later as its own packet; it would sit behind the native field rather than replace it.

## D050 Version 16 keeps the per line tax in a table, not a map

Choice: read the per line tax from the `Item Wise Tax Detail` child table on the invoice.
Reason: spec 5.2 warns against `item_wise_tax_detail[item_code]`, because it was a map keyed by item code and two rows of the same item were added together with no way back to either. Version 16 replaced it with a child table holding the invoice row and the tax row by name, and ships a patch that migrates the old data into it. The thing the spec warns about no longer exists in the release we build on.
Consequence: a line's category can be resolved even when the same item appears twice at different rates, which is the second money fixture in spec 5.3. The table holds company currency amounts, so a foreign currency invoice converts them and the leftover from rounding settles on the largest group.
Source: erpnext/controllers/taxes_and_totals.py and accounts/doctype/item_wise_tax_detail, read on the pinned release.
Affected: spec 5.2 should drop the warning for version 16. D019 recorded the old field as dropped; it was replaced, which is the more useful fact.
Status: Verified.

## D051 A document discount is already in the line amounts

Choice: never state an ERPNext document discount as a document allowance.
Reason: the pinned controller spreads the discount across the rows and rewrites each row's net amount and net rate before tax is worked out. The reduced amount is already in every line, so putting it back at document level would take it off twice, which spec 5.3 forbids outright.
Consequence: `totals.allowances` is zero on an ordinary invoice and the taxable base still reconciles, which the fourth money fixture in spec 5.3 confirms.
The one shape this cannot carry: a cash or non trade discount applied to the grand total. The controller returns early and leaves the lines alone, so the deduction sits after tax with no line and no tax group it belongs to. It is reported as an error rather than approximated, which is invariant I11.
Source: erpnext/controllers/taxes_and_totals.py, the discount amount block.
Status: Verified.

## D052 Payment means when the invoice does not say

Choice: map Mode of Payment type to the official code, Cash to 10 and Bank to 42. Where the invoice records no payment at all, or a type with no safe equivalent, send 1 and raise a warning.
Reason: ibr-191-ae requires a payment means code on an invoice. ERPNext records how an invoice was paid through Mode of Payment, which carries a type rather than an official code, so something has to line the two up. Code 1 is the published value for an instrument that has not been stated, so it states absence rather than guessing at an answer.
Consequence: an invoice with no payment recorded still validates, and the warning says the document did not state one.
Status: Proposed. Worth confirming with the tax adviser that code 1 is acceptable on a UAE invoice that was simply not paid at the time of issue. If it is not, the code becomes a required input on the working record in P04.

## D053 The legal registration scheme is one of four

Choice: the legal registration scheme on both profiles is a list of TL, EID, PAS and CD rather than free text.
Reason: ibr-173-ae accepts only those four for a UAE party, and a free text field let a wrong value through to Full validation, where it failed with a rule id and nothing else. The list stops it at entry.
Consequence: an existing profile holding anything else has to be corrected. No real site has one yet.
Status: Verified.

## D054 Credit note reasons are a closed list of six

Choice: the credit reason code is one of DL8.61.1.A to DL8.61.1.E or VD, and nothing else.
Reason: ibr-001-ae tests the value against exactly that list. VD is the volume discount case, which is also the one exception that needs no preceding invoice reference.
Consequence: extraction cannot supply a reason, because ERPNext has no field holding one. A credit note is reported as needing a reason until the working record in P04 carries it. The field there is a list, not free text.
Status: Verified.

## D055 The adapter contract hands back an artifact reference, not the file

Choice: leave provider evidence uncollected for now, and record the evidence state the provider itself reports rather than inventing one.
Reason: `fetch_artifact` returns an `ArtifactRef` and the outcome has nowhere to put the bytes, so the retrieval works and the file cannot be kept. Adding half of it would leave code that looks like it stores evidence and does not. Spec 10.2 wants each manifest entry to carry the file, its hash, its size and where it came from, none of which can be filled in from a reference.
Consequence: a document can reach Delivered and Accepted and still not be Complete, because the route needs its evidence. That is the correct answer today and it is visible rather than hidden.
Affected: the contract in `domain/connector.py` needs a field for returned bytes, which is a change to something P01 settled and so needs its own packet.
Status: Closed. The artifact reference now carries the bytes once something has actually been fetched, and works its own hash out from them rather than trusting one. A document sent through the simulator reaches Complete with the provider's receipt kept alongside our own canonical and XML. The same change is what lets a supplier's invoice be read in, which is why it was worth doing before receiving rather than after.

## D056 Three things the first provider needs that the contract cannot say

Choice: record these now rather than reshaping the contract for a provider we have not integrated yet.
The three, from reading the Suntech reference against the declaration:
- Searchable, but not by the key that was sent. The contract has one flag for whether a lost response can be settled. Suntech has list filters and a cursor and no ambiguity endpoint, so it has to declare that it cannot search, and every unknown outcome waits for a person. Safe, and stricter than it needs to be.
- Replacement in place. Their resubmit replaces a document under the same provider reference rather than issuing a new one. That maps to the correction path, but nothing in the declaration can say the provider replaces rather than reissues, which changes how a revision is matched up afterwards.
- Not supported at all. Participant lookup and withdrawal are simply undeclared, which the existing capability rule already handles correctly.
Reason: spec 9.1 says an undeclared capability does not exist, and all three answers are safe under that rule. The cost is being stricter than necessary, which is the right way round.
Affected: P10, where a real adapter is written.
Status: Proposed.

## D057 The scenario table was read out of the rules, not written from scratch

Choice: every requirement in `domain/scenarios.py` cites the rule that demands it, and the table was built by reading which rules key off the eight character transaction string in the pinned package.
The mapping, from the rule patterns to the published positions: free zone is position 1 and ibr-007-ae wants a beneficiary identifier; deemed supply is 2, with ibr-191-ae wanting a payment means and ibr-127-ae a due date; margin is 3 and ibr-116-ae requires every line to be category N; summary is 4 and ibr-138-ae wants the period; continuous supply is 5 and no rule adds anything; agent billing is 6, where ibr-137-ae wants the principal, ibr-177-ae the seller's own registration and ibr-176-ae that the two differ; e-commerce is 7 and ibr-142-ae wants a delivery address; export is 8, with ibr-152-ae wanting the delivery address and ibr-135-ae the buyer's identity.
Reason: spec 6.2 says to drive the flag patterns from the official use cases rather than ad hoc combinations. Reading the rules directly is the closest available thing, and it is checkable: every local finding carries the rule id, and on a real invoice each one fired alongside the official rule it cites.
Consequence: the local check tells somebody which field is missing before the XML is built, where the official rules would tell them a rule id afterwards. The official rules stay the authority and still run.
Status: Verified. Margin scheme is the one marked unsupported, because its accounting has not been settled.

## D058 Two serializer gaps the scenarios found

Choice: write the party identification element, and put the principal in the seller supplier element.
Reason: the serializer wrote an endpoint for every party but never a party identification. The endpoint is where a document is delivered and the identification is who the party is. Both ibr-007-ae and ibr-137-ae look for the second, so a free zone or agent invoice failed however complete it looked. The principal was also being written as a payee, which is a different party entirely, and the rules that check it look at the seller supplier element.
Consequence: only the beneficiary and the principal are written with an identification, because those are the two the rules ask for. The buyer identifier that ibr-135-ae mentions has no field in the canonical model yet and is met through the tax registration instead.
Source: found by running each scenario flag against a real invoice and comparing our finding with the official one.
Status: Verified.

## D059 Receiving comes before P09, not after it

Choice: build the receiving side now rather than at P12 where the spec puts it.
Reason: the maintainer asked for it, and the sequencing argument holds. Spec 12.2 makes P12 depend on P09, but that dependency was about provider contracts rather than anything technical, and the Suntech reference in 9.4 already documents how receiving works there. Buying is half of what an e-invoicing app is for on a UAE site, and finding out at P12 that the model does not fit would mean redoing work from P03 onward.
Consequence: the phase order in spec 12.2 no longer matches what was built. P09 will cover receiving as well, which makes it a larger gate rather than a different one.
Status: Verified. Accepted by the maintainer on 19-09-2026.

## D060 Nothing arriving becomes a purchase on its own

Choice: an arrived document lands as its own record and stops there. No supplier is created, no item is invented, nothing posts.
Reason: a supplier's invoice arriving is a claim about what we owe, not a fact. Creating a supplier record from a document somebody else wrote is how a forged invoice becomes a real payee, and spec 12.2 requires no supplier or item creation and no posting without review.
How a sender is matched: by tax number, or by the network address on a supplier profile. A name is never enough, and a near miss is not a match. Where nothing matches, the document waits and says so.
How the company is worked out: by the tax number the document was addressed to, and nothing else. This one nearly went wrong. Frappe fills a company link from the site default when nothing sets it, so the first run attributed two suppliers' invoices to whichever company happened to be the default. The field is now cleared before the record is written and written explicitly afterwards, either way.
Status: Verified.

## D061 Entering a supplier invoice is two steps, and never one

Choice: say what would happen first, then make a draft only if somebody asks. Never a submitted document.
Reason: posting somebody else's claim without anybody reading it is the thing this whole approach exists to avoid. Spec 12.2 requires no posting without configured review, and a draft that a person submits is exactly that review.
What stops an entry, each reported separately rather than as one refusal: it has been entered already; no supplier matches the sender; the company it was addressed to is not clear; it arrived through a simulation or sandbox connection; lines match nothing of ours and no fallback item is set; a tax category and rate the mapping does not cover.
How lines are matched: the supplier's own part number first, because somebody has already said it means this item, then an exact item code. A name is never a match. Where nothing matches, the company's binding may name one fallback item and expense account to enter it against. Leaving that blank makes unmatched lines stop the entry, which is the stricter setting and the default.
How taxes are matched: the same mapping the selling side uses, read the other way, by company, category and rate. Nothing unmapped is posted to something plausible.
How units are matched: the unit whose native code matches theirs, and the item's own stock unit where none does. Refusing a whole invoice over an unmapped unit helps nobody.
Status: Verified. Checked against a published example invoice: the draft came out at net 1000, tax 50, total 1050, matching what their document said it was owed.

## D062 A replaced revision is judged on what happened to it

Choice: Superseded no longer blocks a cancellation on its own. The replaced revision is judged on the same evidence as any other: what the provider received, what was delivered, what was reported, and whether a request is still out.
Reason: Superseded says a revision was replaced. It says nothing about whether that revision ever left. Treating it as settled made correcting an invoice the one thing that stopped it ever being cancelled, which is a worse answer than either of the two it was choosing between.
Consequence: an invoice corrected before anything was sent can be cancelled, and the replaced revision keeps saying it was replaced. One whose earlier version the provider took cannot, and the message says which version.
Status: Verified. The maintainer asked for this on 19-09-2026.

## D063 The fils a divided price cannot carry is stated

Choice: where the line amount and the unit price do not multiply out, the difference goes on the line as an allowance or a charge with its reason.
Reason: ibr-147-ae is exact. The line amount must equal the quantity times the unit price, plus line charges, less line allowances. ERPNext works the other way round when tax is inside the price: it takes the amount first and divides to get the unit price. Three items at 100 with five percent inside give a net of 285.71 and a unit price of 95.24, and three of those is 285.72. An ordinary invoice was being refused with nothing anybody could change about it.
Nothing is altered to make it fit. The amount, the price and the quantity are all what was posted, and the rule's own arithmetic makes room for the difference. A reader sees a one fils adjustment with its reason instead of a document that will not go.
The bound matters as much as the adjustment: it is only applied where rounding the unit price could actually have produced the difference, which is half a unit of price precision across the quantity. A row with an amount and no quantity disagrees by the whole amount and is still reported, because stating that as an adjustment would hide exactly what the arithmetic check exists to find.
Status: Verified. The maintainer asked for this on 19-09-2026.

## Unresolved facts carried from spec 14

| Fact | Owner | Consequence until resolved | Phase |
| --- | --- | --- | --- |
| Frappe v15 and v14 lanes | maintainer | No v15 or v14 claim | P09 |
| Reference deployment workload and company/invoice distribution | maintainer | No capacity claim; spec 11.2 fixture is the placeholder | P00/P09 |
| Real site tax templates, accounts, currency policy | deployment setup | Mappings incomplete | P02/P03 |
| Whether this app reads fta_compliance fields when co-installed (D014) | P01 | Stay independent for now | P01 |
| Currency precision fallback (D018) | money rules packet | No rounding table yet | P01/P03 |
| Whether payment means code 1 is acceptable when an invoice states no payment (D052) | maintainer with the tax adviser | A warning, and the code is sent | P03/P04 |
| Which registration a tax group member shows on its invoice (D016) | maintainer with the tax adviser | Seller profile keeps both identities separate | P02 |
| Issuance and date policy source | maintainer | No issuance deadline logic | P02 |
| Reporting the Volume discount example defect upstream (D008) | maintainer | Example excluded as an XSD positive case | P01 |
| Effective applicability and mandate dates | maintainer | No applicability claim; never hard-coded | P02 |
| Amending spec 5.2 for the changed tax breakup field (D019) | maintainer | We follow the stricter rule meanwhile | P03 |
| ASP contract facts | P10 | Simulation only | P10 |
