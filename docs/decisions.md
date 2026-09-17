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

## Unresolved facts carried from spec 14

| Fact | Owner | Consequence until resolved | Phase |
| --- | --- | --- | --- |
| Frappe v15 and v14 lanes | maintainer | No v15 or v14 claim | P09 |
| Reference deployment workload and company/invoice distribution | maintainer | No capacity claim; spec 11.2 fixture is the placeholder | P00/P09 |
| Real site tax templates, accounts, currency policy | deployment setup | Mappings incomplete | P02/P03 |
| Whether this app reads fta_compliance fields when co-installed (D014) | P01 | Stay independent for now | P01 |
| Currency precision fallback (D018) | money rules packet | No rounding table yet | P01/P03 |
| Which registration a tax group member shows on its invoice (D016) | maintainer with the tax adviser | Seller profile keeps both identities separate | P02 |
| Issuance and date policy source | maintainer | No issuance deadline logic | P02 |
| Reporting the Volume discount example defect upstream (D008) | maintainer | Example excluded as an XSD positive case | P01 |
| Effective applicability and mandate dates | maintainer | No applicability claim; never hard-coded | P02 |
| Whether the planned UOM code DocType is still needed (D026) | P02 with maintainer | Native common code used, with a fallback | P02 |
| Amending spec 5.2 for the changed tax breakup field (D019) | maintainer | We follow the stricter rule meanwhile | P03 |
| ASP contract facts | P10 | Simulation only | P10 |
