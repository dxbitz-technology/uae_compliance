# UAE Compliance: UAE Peppol technical specification

Version 2.1 | 18 September 2026 | Status: implementation baseline, production gated

This document supersedes the original build manual and the subsequent architecture review. It specifies the application, work sequence, and acceptance gates. It contains no implementation and claims no completed tests or provider certification. Follow the referenced official rules where a regulatory interpretation remains unresolved. Version 2.1 completes the six-code document set, ties scenarios to the 16 official use cases, and records the first real ASP reference (Suntech sandbox) in sections 9.4 and 14; it adds no implementation and no production certification claim.

## 0. Fixed decisions

| Area | Decision |
| --- | --- |
| App | Technical name `uae_compliance`; display name UAE Compliance |
| Module and workspace | UAE e-Invoicing |
| App-owned DocTypes | Prefix `UAE Peppol`, including child tables |
| Initial product | Outbound Sales Invoice and credit-note preparation, validation, review, transmission, and recovery |
| ASP availability | Complete the provider-independent application first; real integration has its own gate |
| Company control | Off, Preparation, Live; no global mandatory fields on shared masters |
| Invoice customization | Zero custom fields on Sales Invoice and Sales Invoice Item |
| Master customization | Reuse native fields; add only the optional classification fields in section 4 |
| UI | Native forms, scripts, dialogs, indicators, and reports; custom visual design is deferred |
| Runtime | One Frappe app using the site's database, workers, queue, and private files |
| Standards | Versioned canonical model, PINT AE rules, reference UBL serializer, replaceable provider adapters |
| License | AGPL-3.0-only; preserve upstream licenses and notices [S12] |
| Deployment goal | Suitable for adoption by 5,000 companies across installations, including multi-company sites; capacity must be measured per workload |

Section ownership: working method 1; invariants 2; architecture 3; storage 4; canonical and money 5; standards 6; validation and UI 7; lifecycle 8; adapters 9; access 10; operations 11; phases 12; acceptance 13; evidence 14. Read the sections relevant to the current work packet. Do not duplicate this document in multiple instruction files.

## 1. Work control

### 1.1 Repository discipline

1. Inspect the repository, current branch, status, installed versions, and relevant existing implementation before editing. Preserve unrelated work. Do not recreate an existing app or run destructive resets.
2. Work on one bounded packet under a phase ID. Record its requirement IDs, expected behavior, affected interfaces, likely files, checks, and exclusions before implementation.
3. Prefer one behavior per pull request. Aim for 3 to 8 implementation files and under 400 changed handwritten lines. Split larger work at an interface boundary; record an exception when a coherent migration or rule change requires more. Generated metadata and fixtures are reviewed separately, not exempt from review.
4. Change tests alongside behavior. An accounting, permission, lifecycle, or migration defect needs a regression case. Do not add tests that only assert a mock was called or repeat the implementation's formula.
5. Review the complete diff after checks. Inspect unexpected files, deleted checks, changed snapshots, migration effects, permissions, and dependency changes. Remove debugging output and speculative scaffolding.
6. Keep changes reviewable in commits and pull requests. Never force-push shared history, bypass required checks, or merge a protected branch to satisfy a deadline.
7. A phase passes only with its exit evidence. A working screen, mock response, successful import, or self-review does not establish production readiness.

Use protected `main`, required CI, and a maintainer review. Require an additional competent review for tax calculations, identity/routing, submission recovery, permissions, and destructive migrations. A second pass by the implementer is useful but is not an independent review. Any change after review invalidates approval for the changed scope. Record checks against the reviewed commit; do not invent reviewer sign-off.

### 1.2 Evidence and unknowns

Verify framework symbols in the pinned source, not memory. Verify tax terms against official publications and provider behavior against that provider's contract. Label a claim as Verified, Proposed, or Unresolved. Unresolved facts include an owner, consequence, and affected phase.

Never assume an existing field, hook, API method, rule, endpoint, version, test result, or provider capability without evidence. New app fields follow the accepted storage contract. An unknown that affects money, legal identity, external side effects, or access blocks that path. Continue independent work. Do not weaken a validator, change expected results, return a fake success, or add an unreviewed fallback to get a phase through CI.

A changed architecture or dependency needs a short decision entry before dependent implementation. Routine implementation choices within the approved contract need no new approval ceremony.

### 1.3 Small, durable context

Keep only these development records, alongside executable schemas and tests:

| Record | Content |
| --- | --- |
| `docs/spec.md` | This specification, maintained as the single design baseline |
| `docs/build-state.md` | Current phase/packet, branch, last verified code commit, relevant paths, exact checks and outcomes, blockers, next action; target 80 lines maximum |
| `docs/decisions.md` | Durable decisions and unresolved items; ID, choice, reason, source, affected contract |
| `docs/standards-lock.json` | Official release URLs, download dates, actual hashes, versions, runtime, and code-list provenance |
| Phase pull requests | Requirement IDs, changed behavior, evidence, migration/recovery implications, reviewer outcome |

An optional root `AGENTS.md` is a short index to these records and verified project commands. Keep it portable. Do not copy the specification into it or create separate model-specific rulebooks.

At session start, read the state record, current phase, needed interfaces, and actual diff. Search targeted paths with `rg`. Read callees before changing their callers. Summarize large command output; retain exact failing output and evidence references. Do not repeatedly dump entire repositories, dependency trees, official rule archives, or passing test logs into context.

At a checkpoint, record what changed, what was checked, what remains uncertain, and the exact next packet. Reconcile stale notes against Git and executable tests before continuing. Store no conversation transcripts, speculative task diaries, credentials, or customer data in these records.

### 1.4 House style

- Plain, short, active text. No em dashes in app-authored code, UI, documentation, or commits.
- No promotional wording, decorative dashboards, excessive icons, gradients, animated status effects, or invented interface terminology.
- Labels explain the field. Add help only where a tax concept or consequential action would otherwise be ambiguous. Comments explain a constraint or unusual decision, not obvious code. No verbose docstrings.
- No generated-by notices, tool/model branding, assistant credits, or automatic co-author trailers in repository content or commits. Use the configured, authorized user or Dxbitz Git identity; do not fabricate authorship or remove required third-party attribution.
- Preserve legal texts and upstream notices verbatim even where their punctuation differs from house style.
- Use translatable strings and stable error codes. Example: `3 details missing. Review details.` Example: `Transmission outcome unknown. Check the provider status.`

## 2. Product boundaries and invariants

### 2.1 Company policy

| Mode | Master/draft behavior | ERP submission | External work |
| --- | --- | --- | --- |
| Off | Native behavior; existing app data remains readable | No new app compliance gate | No new transmission intent |
| Preparation | Collect information, validate, show gaps, save incomplete drafts | App compliance findings are advisory | Explicit local export/simulation only |
| Live | Same saveable drafts | Block in-scope submission on applicable local errors or unavailable required validation | Queue validated, approved snapshots |

Missing configuration means Off. A company without an ASP can use Preparation. Mode is company-specific and separate from connection environment and health. Initial Live activation requires the release gate, complete seller identity, verified appointment/onboarding, a verified production connection, and supported transaction scope. A later outage must not introduce a synchronous network dependency into invoice submission.

Store the current mode and effective date in the seller-to-company binding. Record changes with actor, reason, and old/new values. A posting date alone cannot bypass current issuance obligations: resolve activation and statutory applicability using the documented issuance/date policy. No deadline or legal scope is inferred from a user-selected mode. Do not hard-code the current rollout dates into invoice logic.

Turning Off prevents new intents. Existing submissions retain their original obligations and remain reconcilable. The separate operational pause stops new sends/retries without changing validation policy, destroying queued work, or stopping status recovery. Resuming must not bulk-send previously unapproved documents.

### 2.2 Non-negotiable invariants

| ID | Invariant |
| --- | --- |
| I01 | ERPNext remains authoritative for accounting values; the app must not quietly alter tax, revenue, quantities, or payments in its payload. |
| I02 | Company policy determines enforcement. Party country controls entry and contributes to scenario evaluation, not automatic VAT treatment. |
| I03 | Compliance gaps may not block draft save. Standard ERP validation, authorization, and storage failures still apply. |
| I04 | One working record per source invoice; no submission or transmission log per draft save. |
| I05 | Each sent business payload is immutable and versioned. Retry uses the same business bytes and idempotency key. |
| I06 | An unknown send outcome is reconciled before any unsafe resend or correction. |
| I07 | Exchange, FTA reporting, and local validation are independent facts. Simulation never produces a production acceptance claim. |
| I08 | Every external request passes through the audited transport boundary. No network call runs inside an ERP document transaction. |
| I09 | Company/document permissions apply to actions, reads, jobs, reports, event correlation, and private files. |
| I10 | Existing master data and submitted evidence survive installation, upgrades, and policy changes. |
| I11 | Unsupported scenarios fail explicitly in Live; they are never approximated or silently omitted. |
| I12 | No provider-specific schema or status code enters domain logic. |

### 2.3 Supported scope

The first release supports the scenarios actually implemented and accepted in section 13. At minimum, cover ordinary B2B/B2G invoices and credit notes, registered/unregistered seller cases, repeated items, tax-inclusive/exclusive prices, discounts, charges, mixed applicable tax categories, and AED/foreign invoice currencies.

Exports, domestic reverse charge, free-zone cases, deemed supply, margin, summary/continuous supply, agency, e-commerce, advances, and retention each require an explicit capability row. The initial default for an unimplemented row is Unsupported. No generic checkbox can activate an unfinished workflow.

Customer type `Individual` alone does not establish consumer use. Determine transaction purpose explicitly where needed. A customer agreement to self-bill is not sufficient to discard outbound obligations silently. Incoming purchase automation and purchase-side self-billing have a later phase and separate direction controls.

Until receiving automation exists, deployment must document and verify the appointed ASP's operational receiving path, such as its inbox/export process. Do not claim that deferring ERP purchase automation removes receiving obligations.

## 3. Architecture and dependency limits

Use a modular monolith. Thin DocType controllers and hooks call application services. Domain calculations and validation consume plain typed data and do not import Frappe or a provider SDK. The ERP adapter owns framework-specific extraction. Provider adapters translate the canonical contract and normalize external evidence.

| Boundary | Responsibility | Must not own |
| --- | --- | --- |
| `domain/` | Canonical schema, money, scope/scenario rules, findings, lifecycle transition rules | Database, HTTP, UI, provider schemas |
| `erpnext/` | Source extraction, master resolution, version-specific hooks | Alternative accounting calculations hidden from the source invoice |
| `services/` | Transactions, authorization, snapshots, approval, worker scheduling | Provider-specific response interpretation |
| `connectors/` | Registry, contract, adapter packages, audited HTTP transport | Domain tax policy or direct source-document mutation |
| `validation/` | Versioned semantic checks, safe XML serialization, official XSD/Schematron execution | Network-dependent form validation |
| Module DocTypes and `public/js/` | Native storage and UI integration | Independent business-rule implementations |

These are ownership boundaries, not an instruction to create empty directories or one-class wrapper layers. Use normal functions and existing Frappe facilities. Add an abstraction when two real implementations need it, with the connector contract being the planned exception.

No separate production API service, message broker, frontend framework, search cluster, event-sourcing platform, custom workflow engine, mandatory telemetry service, or central Dxbitz service. A local HTTP simulator is test infrastructure only. Prefer existing dependencies; pin new packages and document purpose, supported CPU platforms, license, and installation cost.

Target Frappe/ERPNext v15 and v16 through separately verified compatibility lanes. P00 selects exact compatible release pairs and runtimes. Implement against one lane first; advertise the other only after its acceptance suite passes. A mutable branch name is not a release pin.

Use a pinned XSLT engine capable of the official artifacts. Do not assume an XSLT 1.0 engine can execute XSLT 2.0/3.0 rules. Select one validated runtime in P00, cache compiled artifacts safely per worker, and block full-validation claims when it is unavailable. Do not download rules on each invoice.

## 4. Storage contract

All new DocTypes below start with `UAE Peppol`. Ordinary field names inside them need no repeated prefix. Do not rename native ERPNext DocTypes. The names below are actual DocType names, not display aliases [S11]. P01/P02 turn these logical fields into one reviewed field/type/default/permission registry before generating metadata; later changes update that registry once.

### 4.1 Master and configuration records

| DocType | Minimum field groups | Constraints |
| --- | --- | --- |
| UAE Peppol Settings, Single | `pause_outbound`, bounded retry/poll settings, installed ruleset/version status | No site-wide mandatory ASP; no global environment overriding connections; ruleset identifiers are release-owned |
| UAE Peppol ASP | `provider_key`, label, environment, base URL, enabled, config revision, capabilities, connection health, credential rows, token expiry | Environment is Simulation/Sandbox/Production; provider and environment cannot be repurposed after use |
| UAE Peppol ASP Credential, child | key, encrypted Password value, expiry where applicable | Keys validated against adapter schema; write-only in app APIs; never return decrypted values |
| UAE Peppol Seller Profile | display label, participant TIN/scheme/value, VAT registration state, tax-group context, missing legal registration details, onboarding evidence, current ASP, company rows | Stable internal name independent of a still-missing TIN; verified identity unique when present; no VAT-group identity merging |
| UAE Peppol Seller Company, child | Company, mode, effective-from date, review-required, default Address | Company belongs to one current seller binding; database-enforced uniqueness; selected invoice address may override the default |
| UAE Peppol Party Profile | allowed party DocType, Dynamic Link party, establishment country, business/government/consumer context, VAT state, declared Peppol state, endpoint scheme/value, missing legal IDs, verification evidence | Unique `(party_doctype, party)`; Customer/Supplier only; creation allows incomplete compliance details |
| UAE Peppol Tax Category | Company, source tax account/template selectors, category code, rate applicability, reason mapping | Deterministic company-aware key; no ambiguous wildcard winner; zero rate alone cannot determine category |
| UAE Peppol UOM Code | UOM, UN/ECE code | Unique UOM; code from pinned list; map invoiced UOM, not only stock UOM |

Store connection credentials in the native encrypted facility. Confirm its behavior for the chosen child-table implementation in both compatibility lanes. If it cannot safely persist and rotate child passwords, resolve the storage design in P02; do not silently substitute plaintext JSON. Non-secret provider options use validated, size-bounded typed configuration. Do not create a free-form override mechanism for URLs, code, or business rules.

Profile fields requiring external evidence remain incomplete until that evidence exists. Manual participation states are Registered, Not registered, Not sure. Lookup outcomes are separate: Verified, Not found, Unavailable, Expired. Keep method, connection, scheme/value checked, timestamp, and validity horizon. A manual selection must never set `verified`.

Use native Customer/Supplier tax identifiers and Company tax registration when their jurisdictional meaning matches. Postal data belongs to Address. Native names/contact fields remain authoritative. A foreign party may need an additional UAE VAT registration without overwriting its domestic identifier; use a conditional profile field for that additional value, with an explicit source policy. Do not maintain two editable copies of the same identifier.

Seller profiles contain the missing legal/participant information. The selected Company's native identity, applicable VAT registration, and chosen linked address are resolved and frozen per invoice. Many Company records may represent one legal participant; sharing a VAT-group TRN alone does not establish that relationship.

### 4.2 Transaction records

| DocType | Minimum field groups | Ownership |
| --- | --- | --- |
| UAE Peppol Invoice | unique Sales Invoice, Company, resolved scope/mode, editable scenario inputs, input revision, source/master fingerprint, readiness, finding counts/details, latest submission link, native audit history | Mutable working control; source link immutable; update after source save |
| UAE Peppol Submission | control link, Company, revision, business document identity, predecessor, canonical schema/version/hash, frozen source/canonical, connection/environment/config version, routing, ruleset/serializer/adapter versions, approval, queue/lease/retry fields, independent status fields, provider IDs, evidence manifest | Frozen business inputs; operational state changes only through services |
| UAE Peppol Transmission Log | Company where applicable, submission/connection, operation, attempt ID, Pending/result, request digest, sanitized metadata, external IDs, timings, error class, retry hint | One durable external attempt; append-only business history |
| UAE Peppol Event | connection/environment, provider event ID or documented fallback key, payload digest, private payload reference, signature metadata, received/provider timestamps, correlation, Company when resolved, processing state/error | Immutable received evidence; processing metadata may change |

Use native File for private artifacts and native Version for local configuration/scenario/approval history. Do not add separate DocTypes for findings, every tax term, each lifecycle transition, generic logs, or artifacts. JSON fields must have versioned schemas and payload limits.

Keep the app's operational DocTypes non-submittable. Their guarded application states are separate from Sales Invoice `docstatus`; do not add a second generic Workflow to mirror them. Track meaningful local edits and decisions, not every regenerated finding or polling timestamp, in Version history.

Do not duplicate the entire canonical model into editable invoice line/tax child tables. Native dialogs may render read-only projections. Add a projection table only for a demonstrated query requirement; it must be rebuildable and must not become a second source of truth. This supersedes the original mandatory line/tax satellite tables.

Freeze business snapshots on a successful Live source submission, before approval/send. In Preparation, incomplete sources keep only a working record; an explicit successful simulation/export may create a clearly marked non-production snapshot. Never later convert that snapshot to Production.

Required uniqueness/indexes:

- Working invoice: unique source Sales Invoice; index `(company, readiness)`.
- Party profile: unique party type/name. Seller binding: unique current Company. Known seller participant identity: unique normalized scheme/value, with missing identity handled without empty-string uniqueness collisions.
- Submission: unique `(control, revision)` and idempotency key; indexes for `(processing_state, next_attempt_at)`, `(company, created_at)`, lease expiry, provider correlation.
- Log: unique attempt ID; indexes for submission/time and Pending/time. Event: unique connection/event key; indexes for processing state/time and correlation.
- Enforce a single active submission with a locked control row or atomic compare-and-set. Do not rely on a pre-insert existence query.

Store dates as dates, timestamps consistently in UTC, and display through the site's timezone. Do not use a display naming series as an idempotency mechanism.

### 4.3 Native master customization budget

| Native DocType | Allowed app additions |
| --- | --- |
| Sales Invoice / Sales Invoice Item | None |
| Customer / Supplier / Address / Company | No new persisted fields by default; use profile/setup actions and existing fields |
| Item | Optional `uae_peppol_item_type` with Goods/Services/Both; optional compatible classification/HS field only where no suitable field exists |
| Item Group | Optional `uae_peppol_item_type` default, if Item Group suggestions are implemented |

All additions are optional on master save. Conditional invoice requirements belong to validation. Never infer service from `is_stock_item = 0`. Use native Item Tax Templates/accounts and company-aware mapping for tax treatment. Arabic names remain optional: reuse native localized fields or approved profile/line overrides; do not install three extra bilingual fields by default or invent unsupported XML elements.

Additional fields, DocTypes, dependencies, or global overrides require a decision entry with the unmet requirement and rejected simpler option. Export only app-owned fixtures. Install, update, and removal must never overwrite another app's fields, roles, scripts, or Property Setters.

## 5. Canonical model and ERP extraction

### 5.1 Canonical v1

Define an executable schema before writing adapters. Use decimal strings for quantities, prices, rates, and money; ISO dates/currencies/countries; explicit identifier scheme/value pairs; stable source row IDs. Distinguish absent, zero, and not applicable. Reject unknown fields at controlled input boundaries; version intentional extensions.

| Group | Required structure |
| --- | --- |
| Provenance | schema version, source DocType/name, Company, source business fingerprint, relevant master revisions, extraction version |
| Context | jurisdiction, company policy revision, resolved scope/reason, environment, supported scenario, standards version |
| Document | legal number, invoice/credit-note type, issue date, due date when applicable, tax-point date, invoice period, document currency, tax currency |
| Parties | seller, buyer, optional agent principal/beneficiary; legal/trading names, participant IDs, applicable tax/legal registrations, selected postal addresses, contacts where required |
| Lines | stable ID, source row, item/reference, description, classification, invoiced quantity/UOM, price base quantity, gross/net price, price discount, allowances, charges, net amount, tax category/rate/reason |
| Tax breakdown | category, rate, reason where required, taxable base, VAT amount; document-currency amounts and applicable AED tax totals |
| Adjustments | Line/document allowances and charges with amount, base/percentage when applicable, reason, and tax attribution |
| Totals | line net, allowances, charges, tax-exclusive, tax, tax-inclusive, legally applicable prepaid amount, rounding, payable |
| References | multiple preceding invoices with date/ID, credit reason, contract, purchase order, supporting documents where supported |
| Payment/delivery | payment means and instructions, delivery party/address/date, terms, incoterms/customs references where applicable |
| Scenario | Typed inputs for the enabled scenario; named flags internally, exact official transaction code only at serialization |
| Exchange rates | from/to currencies, value, date, source/evidence; separately record invoice-to-company and invoice-to-AED where required |

Do not create a database field for every canonical property. Store one authoritative frozen JSON document and artifact hashes. Query only indexed operational fields. The reference XML and provider payload are derived artifacts, not alternate editable records.

Define deterministic JSON encoding: UTF-8, stable key ordering, documented decimal representation, stable meaningful array order, and a fixed null/omission policy. The business hash excludes volatile request timestamps, auth tokens, mutable status, and later payment collection. Hash exact serialized payload bytes separately. A signed envelope may change transport metadata on retry only where the provider contract requires it; business content and logical key remain unchanged.

### 5.2 Source map

P03 maintains one term matrix: canonical path, native source path or explicit input, currency/precision, condition, transformation, official term/rule, and fixture ID. Never treat `item_wise_tax_detail[item_code]` as an authoritative per-line ledger: repeated item codes can be aggregated and values can already be converted in ERPNext [S07].

| Value | Source rule |
| --- | --- |
| Invoice identity/date | Source name and validated issue/date policy; preserve posting, tax-point, and legal issue meanings separately |
| Party/address | Selected Company/Customer and selected invoice billing/delivery addresses; no fallback to today's primary address after freeze |
| Item classification/UOM | Explicit row data and resolved Item/Item Group defaults; selected invoice UOM mapping |
| Line amounts | Transaction-currency row values using the pinned ERP calculation behavior |
| Effective taxes | Native invoice tax rows, account/template context, row overrides, and actual tax/discount calculation order |
| Currency | `currency` denotes transaction currency; `base_*` denotes company currency, which is not automatically AED |
| Previous invoice | `return_against` plus explicit supported references; support more than one reference |
| Payments | Freeze applicable paid/prepaid semantics at issue; later `outstanding_amount` must not regenerate historical payable |
| Scenario inputs | Validated working-record input revision; never arbitrary provider fields |

Tax mapping first matches the effective item-template/VAT-account context within the Company, then an explicit Company/VAT-account fallback if unambiguous. Reject multiple matches. Use the source's actual rate and treatment; a zero rate needs an explicit category/reason context. Scenario rules may require a different representation only when their documented mapping reconciles to the source. Never select the first available mapping or silently replace posted tax.

Source extraction must be deterministic and read-only. Reuse verified ERP calculation behavior where available; do not call generic document validation for a preview if it can write data or trigger unrelated hooks. Verify the hook ordering and supported calculation entry points in each pinned release.

### 5.3 Money rules

Use Decimal arithmetic with precision from the pinned rules and currency policy. Document rounding separately for quantities, unit prices, line amounts, VAT breakdowns, exchange rates, and document totals. No binary floating-point math in domain calculations.

Reconcile, in document currency:

- Tax-exclusive total = sum of line net amounts - document allowances + document charges.
- Tax-inclusive total = tax-exclusive total + VAT total.
- Payable = tax-inclusive total - applicable prepaid amount + rounding.

These identities do not authorize changing the ERP accounting treatment. Explain every difference from the frozen source. A difference outside the documented rounding rule is an error, not a tolerance to increase until tests pass. Preserve the effect of ERP additional discounts, inclusive tax, cascading charges, and row tax overrides.

Price discounts already included in net unit price must not be deducted again as allowances. Classify non-VAT charges separately; `total_taxes_and_charges` is not necessarily VAT. Allocate document adjustments according to the verified ERP behavior and applicable tax grouping; use stable row IDs for residual allocation. Group VAT by every dimension required by the rules, not rate alone.

For foreign-currency invoices, preserve original-currency amounts and calculate the required AED reporting values from an evidenced, frozen rate. A current rate lookup must not change an old invoice. A non-AED company currency needs an explicit tested conversion path. Do not multiply already converted tax values twice. Missing rate provenance is a local finding; no rate is invented.

Credit-note extraction converts ERP signs according to an explicit invoice/credit-note mapping. Do not apply absolute value to every field. Test quantities, amounts, allowances, charges, taxes, and payable together.

Minimum independently calculated money fixtures:

| Fixture | Expected control |
| --- | --- |
| Two units at AED 100, line discount AED 20, VAT 5% | Net 180, VAT 9, total 189 |
| Same item code on AED 100 and AED 50 rows, VAT 5% | Row VAT 5 and 2.50; total 157.50 |
| AED 105 VAT-inclusive at 5% | Net 100, VAT 5 |
| AED 200 net, document allowance AED 10, VAT 5% | Taxable 190, VAT 9.50, total 199.50 |
| USD 100 net, example rate 3.6725 AED/USD | USD amount remains 100; corresponding AED amount 367.25 before applicable VAT |
| Submitted invoice subsequently partly paid | Original submission bytes/hash unchanged |

The exchange rate above is a test value, not a live rate. Add mixed categories, non-AED company currency, rounding edges, surcharges, returns, and partial payments before claiming their support.

## 6. Standards and scenario resolution

### 6.1 Locked rule set

PINT AE Billing 1.0.4 is the checked starting publication [S01]. P00 verifies the release in use, retrieves official resources, and records actual checksums and dates. Keep official artifacts unchanged and licensed correctly. Updates occur through a reviewed release with regression evidence, never an automatic runtime download.

The lock records: specification/profile identifiers, billing versus self-billing family, XSD and shared/AE Schematron artifacts, code lists, examples, XML runtime, canonical version, serializer version, effective applicability, and source URLs. Preserve old version identities in evidence. Missing official artifacts or a schema/runtime mismatch means Validation unavailable, not Passed.

### 6.2 Required corrections to the original manual

| Topic | Required implementation |
| --- | --- |
| Document codes | Six PINT AE types: tax invoice 380; tax credit note 381; commercial invoice 480; commercial credit note 81; self-billing invoice 389; self-billed credit note 261. Select through the verified category matrix, not `is_return` alone. The UNCL1001 code list is split by transaction family, so no single code-list page shows all six; confirm each against its own transaction path [S03a] [S03b] [S14]. Self-billed 389/261 are enabled in P12. |
| Tax categories | Use the applicable pinned list. Margin uses ASCII `N`, not `M`; implement its full rules before enabling it [S04]. |
| VAT identifiers | Apply the AE format in its published context, including 15 digits, initial 1 and final 03. Do not apply the AE rule to all foreign tax IDs [S05]. |
| Participant versus VAT identity | Keep the participant's TIN distinct from VAT-group registration. Do not enforce an unconditional TIN/TRN prefix equality [S02]. |
| Credit notes | Require a reason and the applicable reference collection. Implement the published Volume Discount reference exception [S06]. |
| Free-zone scenario | Include beneficiary ID as required by IBR-007-AE; a beneficiary name alone is insufficient [S06]. |
| Export | Determine actual transaction treatment and route; foreign customer country does not force zero VAT or a generic endpoint [S02]. |
| Scenario structure | Agency needs principal identity; summary needs period; e-commerce/export need applicable delivery data; price calculation needs base quantity [S06]. Drive flag patterns and allowed VAT categories from the 16 official transaction use cases UC1 to UC16, not ad hoc combinations [S01]. |
| Advance/retention | Define advance tax invoice, payment, final balance invoice, and retention-release documents explicitly. Never subtract an advance only in the ASP payload [S02]. |

Required field counts are not a validator. Resolve each term's conditional requirement from the pinned model and scenario matrix. Do not copy the old blanket TRN/category, self-billing, or exemption-reason rules without confirming their exact context.

### 6.3 Routing and scope

Separate tax treatment, document category, counterparty identity, and delivery route. A UAE seller can invoice a foreign party; a foreign seller can invoice a UAE party without activating this app's UAE issuance policy.

Resolve routing from the actual scenario, declared facts, current verified endpoint evidence, and official fallback policy. Store route, rationale, verification evidence, and required acknowledgement dimensions. Special deemed/not-onboarded/export endpoint values come from the locked official source and scenario rules. A lookup timeout or Not found response alone does not authorize a fallback.

Keep recipient endpoint scheme and value explicit, including foreign schemes. Do not force `0235` or a UAE TIN onto every buyer. Before a live send, the endpoint or permitted fallback must be established. If evidence has expired, hold for verification; do not mutate the frozen route silently.

Represent the official transaction flags by named booleans/typed inputs internally. Generate the published positional string in one serializer function with fixtures for every enabled combination. Reject contradictory or unsupported combinations. Do not combine arbitrary checkboxes into a seemingly valid invoice.

For advanced scenarios, complete a row containing source documents, issuer/recipient role, accounting effect, mandatory terms, permitted codes, routing, acknowledgement requirements, correction rules, and acceptance cases. An unresolved row stays disabled. Customer-side self-billing agreements and received documents remain visible in reconciliation; an agreement must not make source invoices disappear.

## 7. Validation, hooks, and native UI

### 7.1 One validation service

Expose one service with Fast and Full levels. Fast checks scope, locally available master facts, item/UOM/tax mapping, and cheap arithmetic. Full includes complete extraction, canonical checks, reference XML, XSD, shared and AE Schematron, and any applicable installed local provider validator.

The same rule implementation supplies server findings to the UI. Small client checks may improve entry but must not become an independently maintained tax engine. No provider HTTP request runs during selection, draft save, preview, or source submission.

Each finding contains: stable code, severity, stage, canonical/source field path, source DocType/name or row ID, safe short message, optional official rule ID, and a named repair action. Return all independent actionable errors without flooding the user with consequences of the same missing value. If prerequisite data prevents a stage, mark it Not run with its reason.

Each result contains: level, checked input/master fingerprint, ruleset/version, stage states, timestamp, findings, and applicable scope. Stage states are Passed, Failed, Not run, Unavailable, and Skipped where genuinely optional. An absent optional SDK is Skipped. It cannot skip mandatory local rules. Schematron runs on XML, never on JSON.

Only a current successful Full result can show Ready locally. Fast success alone means Further checks required. Live source submission always reruns required server checks on authoritative values; it never trusts a cached browser result.

For providers that generate XML, validate the reference XML and semantic input locally, document provider-owned fields, then retrieve and validate actual returned XML when available. Local reference validity is not evidence that the provider's output or FTA reporting succeeded. Missing provider-generated values and provisional test values must not be described as verified production evidence.

### 7.2 Native lifecycle integration

Confirm these hook semantics/order on the pinned framework before implementation [S08]. Use app hooks and controllers, not site-only Server Script records or core edits.

| Event/action | Required behavior |
| --- | --- |
| Form load / default Company | Resolve mode/scope and display local readiness; do not create temporary-named records |
| Company / party / selected Address change | Invalidate readiness; batch local checks after native fetches settle |
| Item / tax / quantity / scenario change | Debounce Fast checks; ignore responses for older form fingerprints |
| Server `validate` | Collect applicable findings after verified native calculation ordering; do not throw for ordinary draft compliance gaps |
| Server `on_update`, draft | Upsert one working record inside the source transaction, after the source exists; preserve independently saved scenario inputs |
| Validate button | Check a permission-checked copy of current form values, including unsaved edits; no implicit save or database writes |
| Server `before_submit` | Fresh Full checks; enforce Live policy; Preparation stays advisory |
| Server `on_submit` | Freeze a successful Live snapshot and intent in the source transaction; approval determines whether work is sendable |
| Server `before_cancel` | Apply locked cancellation policy in section 8 before source cancellation commits |
| Allowed update-after-submit paths | Prevent material changes conflicting with frozen evidence; later payment/status updates never rebuild payloads |

`on_update` can also run on insertion/submission: guard `docstatus` and make the operation idempotent. Do not write recursively to the source invoice from its satellite hook. Enqueue only after commit; the durable database intent remains recoverable if enqueue fails [S09]. No manual database commit inside a web document hook.

A scope change on an existing draft updates its working status and audit history rather than deleting it. New Off-mode invoices need no working record. Source save must not overwrite an input revision edited concurrently in the satellite.

To retain zero invoice custom fields, scenario details live in the working record. In the initial native UI, save the invoice draft first, then use its UAE e-Invoicing action to edit those details. Saving details uses expected-revision checking. Preview may include unapplied dialog inputs, but it never approves them. Submission reads persisted details and current source values.

Master changes invalidate readiness through dependency fingerprints, checked on use. Batch the relevant `modified`/revision reads; do not synchronously rewrite thousands of drafts when a shared Item changes. Submitted snapshots remain unchanged.

### 7.3 Customer, Supplier, and Company entry

Extend the shared native Customer/Supplier Quick Entry contact/address experience. Both entry points use a shared form in the checked ERPNext source [S10]. Preserve installed extensions; do not unconditionally replace a global class. Full-form creation, imports, and APIs must remain valid entry points.

Move the existing Country selector near the top. Use native name/contact/address fields. Reveal UAE VAT/Peppol registration and missing legal identity inputs progressively. Keep Not sure as an available state. Preserve an optional path for a foreign party's UAE registration or foreign endpoint. Initial country may prefill establishment and postal country; retain their separate meanings thereafter.

Create party, supplied valid Address/Contact, and profile through one server transaction with validated permissions. Reuse native address creation. No duplicate address insert, blank dummy address, invented TRN, or independent after-save profile request. Incomplete compliance is permitted; native required fields still apply. If a user cannot edit a shared field, provide a native assignment/request action instead of expanding their access.

Company setup prefills native data, links/creates the seller profile, and selects Preparation without an ASP. Native setup shows local completeness, connection health, and onboarding separately. Connect/Test/Verify actions explicitly schedule audited worker operations; no network registration occurs merely because the profile was saved.

### 7.4 Invoice and Item interface

Use native buttons, indicator styles, `frappe.ui.Dialog`, field controls, and Query/Script Reports. A small app-scoped notice provides the requested ribbon behavior without replacing native notices. No new badge artwork, standalone application shell, bespoke CSS framework, or frontend dependency in the core phases.

Show: Not checked, Checking, Needs details, Ready locally, Preparation, or the relevant transmission summary. A details dialog groups findings by Company, Party, Address, Items, and Invoice, with direct permission-checked actions. Use one submit-error summary. Keep the required exchange/reporting facts available beneath the summary.

Item fixes use one native bulk dialog, deduplicated by Item and linked to affected rows. Item Group classification is a suggestion; Item-specific values take precedence. Save item defaults is an explicit master write. Apply to this invoice, if supported, writes a typed row override in the working record keyed by stable source row ID. Never silently change Item masters on invoice save.

Provide UAE e-Invoicing Readiness and UAE e-Invoicing Reconciliation reports with Company/date/status filters. Batch list indicators if implemented; never add a Sales Invoice status field to obtain filtering. Reports remain useful without custom visual design.

Use the existing ERP print format for required human-readable output. Preserve the issued data/template identity if the PDF forms part of retained evidence; do not regenerate historical content from changed masters. Custom print design, branded badges, and new QR generation are outside the initial UI scope.

### 7.5 Application service surface

Define typed request/result contracts in P01. Names below specify responsibilities, not existing framework methods.

| Action | Contract |
| --- | --- |
| `preview_invoice` | Source name or allowed unsaved document, optional preview inputs, expected fingerprint, Fast/Full; returns findings only |
| `save_invoice_inputs` | Saved source, expected source/input revision, allowed scenario/row overrides; draft-only mutation |
| `get_readiness_batch` | Bounded source list; returns permission-filtered summaries |
| `approve_submission` | Submission ID and expected canonical/context hashes; current approver permission required |
| `retry_submission` | Existing immutable submission; state/capability check; no payload edit |
| `correct_submission` | Explicit permitted correction path, predecessor, reason, new revision; never a generic retry |
| `refresh_status` | Schedules reconciliation of a known connection/submission |
| `download_artifact` | Opaque evidence identifier; checks originating Company/document access |

Never accept trusted status, Company, provider URL, method path, user, or approval fields from a client. Resolve them server-side. Bound input size and batch counts. Mutating actions use authenticated POST, CSRF behavior appropriate to the authentication method, permissions, and optimistic concurrency.

Submitted-document inspection uses its frozen snapshot/evidence. It must not invoke the draft preview path to rebuild an old submission from current masters.

## 8. Submission, review, and recovery

### 8.1 States

Keep these dimensions independent. Display text may be shorter; stored meaning must remain explicit. The official flow supplies distinct exchange and reporting acknowledgements [S13].

| Dimension | States |
| --- | --- |
| Working readiness | Not checked, Stale, Needs details, Ready locally, Unavailable, Out of scope |
| Processing | Awaiting review, Ready, Sending, Awaiting outcome, Retry scheduled, Unknown, Attention required, Complete, Stopped, Superseded |
| ASP receipt | Not sent, Unknown, Received, Rejected |
| Exchange | Not started, Pending, Delivered, Rejected, Unknown, Not applicable |
| FTA reporting | Not started, Pending, Accepted, Rejected, Unknown, Not applicable only where permitted |
| Evidence | Complete, Pending, Unavailable, Invalid |

Store provider raw codes and timestamps with their originating event/attempt. Interpret them through the adapter's documented mapping. HTTP success proves transport success only. Complete requires all route-required acknowledgements and required evidence; do not stop recovery merely because one dimension succeeded. If only optional artifacts are unavailable, report that separately instead of falsifying the reporting outcome.

### 8.2 Freeze and approval

At Live source submission, lock the relevant control row, establish a coherent view of source/master inputs, validate, allocate a revision and stable idempotency key, and persist the frozen submission in the same database transaction. Use deterministic lock ordering or verify revisions again to prevent mixed snapshots during concurrent master edits. Prepare required payload/evidence before making work sendable. A rollback must leave no sendable intent.

File storage is not rolled back by a database transaction automatically. Stage artifact writes safely, verify required bytes before enabling the intent, and clean up only proven unreferenced files after rollback. A file-write failure must not leave work that can transmit without its retained request evidence.

Review-required defaults to true per Company. A sendable submission must have its canonical and business request frozen before approval. Approval references their exact hashes, connection/environment, routing, and ruleset versions. Preparation-only exports without a provider request cannot become live submissions. On approval, recheck those identities and the approver's permissions. A corrected revision needs new approval. An unchanged transport retry does not.

No change to Company, party, tax treatment, scenario, route, or connection silently updates approved content. Master updates after freeze do not rebuild it. A new business revision follows the correction policy. Connection credential rotation may retain the same connection identity; changing provider/environment requires a new connection and an explicit transition.

If review is disabled for a verified Company, record policy-based automatic approval on the same immutable revision. Operational alerts must identify unreviewed documents approaching their configured reporting deadline.

### 8.3 Durable worker boundary

The submission is the outbox. Redis is a delivery mechanism, not the only record that work exists. Worker transactions are explicit and separate from source-document transactions.

1. Select a bounded set of due database intents using indexes. Claim one atomically with a lease and fencing token, verifying approval, environment, pause state, and single-active-submission rule.
2. Verify the already frozen business request and approved hashes. Reject missing bytes or an unsupported adapter-version change; workers may construct authentication/transport envelopes but cannot regenerate approved business content. Persist a Pending attempt and request digest. Commit before the HTTP request.
3. Call the provider through the audited transport, with finite connect/read deadlines and safe response limits. Do not hold a database row lock across the request.
4. Persist normalized results/evidence and update allowed state transitions in a new transaction. Use fencing/version checks so an older worker cannot overwrite newer status.
5. On failure or lost response, classify whether the external effect is known. Recover abandoned Pending attempts and expired leases through reconciliation, not blind resend.

A lease expiry does not prove the prior worker stopped or the provider did not accept. Lease length must exceed the normal request deadline, with controlled renewal if needed. Another worker must not send the same ambiguous request unless the provider's verified idempotency contract makes it safe.

Crash windows to cover: before claim; after claim; after Pending commit but before HTTP; after remote acceptance but before response; after response but before local result commit; after event receipt but before processing; after source commit but before enqueue. Conservative Unknown is acceptable. Duplicate legal invoices are not.

### 8.4 Retry rules

| Outcome | Action |
| --- | --- |
| Known rejection before acceptance | Preserve findings; require a permitted correction or configuration repair |
| Confirmed temporary failure with no acceptance | Schedule bounded retry with the same payload/key |
| Request may have reached provider, including some 5xx/timeouts | Unknown; reconcile by correlation/key first |
| Ambiguous outcome with proven provider idempotency | Reconcile or repeat the identical operation only within the documented idempotency guarantee |
| No safe idempotency or reliable lookup | Hold for manual resolution; never assert exactly-once delivery |
| Authentication expired | Refresh once under a connection lock; repeat only if the original operation's effect is known/safe |
| Rate limit | Honor Retry-After; do not retry earlier merely because a local backoff cap is shorter |
| Missing artifact or acknowledgement | Retry retrieval/status, never resubmit the invoice to obtain it |

Starting engineering defaults: five automatic retry attempts, exponential delay from 30 seconds with jitter, normal backoff capped at 15 minutes, with provider Retry-After and deadlines taking precedence. Store attempts, next time, error class, and attention reason. Review these settings against the first ASP's contract; they are product defaults, not regulatory deadlines.

Reconciliation polls webhook-capable providers too. Query pending/unknown/partial outcomes by connection and bounded batches. Record the last checked time, provider cursor when applicable, and next due time. Avoid one scheduled job per historical invoice.

### 8.5 Events

Authenticate the raw request before status mutation. Use the provider's verified signature/mTLS/token scheme, replay window, connection/environment binding, payload limit, and constant-time signature comparison where applicable. Endpoint secrecy alone is not authentication.

Persist verified evidence before acknowledging receipt; then process asynchronously. Deduplicate by `(connection, provider_event_id)` or a documented stable alternative. Store a payload digest so reused IDs with different bodies raise an integrity issue. An event that arrives before the submit response is retained and correlated later. Unmatched events are manager-only until their Company is established.

Use provider sequence/version semantics where supplied. Received order is not event order. Duplicate or late events must not regress a newer confirmed status. If a provider lacks ordering semantics or sends conflicting facts, retain both and reconcile. Do not erase evidence to make the displayed state look consistent.

### 8.6 Cancellation and correction

| Situation | Permitted path |
| --- | --- |
| Unsaved/draft source, no external intent | Native draft edit/delete, subject to native permissions |
| Frozen but provably unsent and unclaimed | Atomically stop intent before a permitted native cancellation; preserve snapshot/audit |
| Sending, Pending attempt, or Unknown | Block conflicting cancellation/correction until outcome is resolved |
| Provider rejected before issuance and documented correction is allowed | Correct through the approved source/input workflow; new revision, predecessor, reason, validation, approval |
| Issued/delivered/reported document | Controlled credit-note/correction workflow; no generic Cancel accepted invoice action |
| Provider-specific withdrawal | Expose only when its supported stage and legal effect are verified |

No transmission attempts alone are not proof that a document was never issued elsewhere. Respect the documented issue/correction policy. `on_cancel` must never label a remote document Cancelled merely because ERP cancellation succeeded. Preserve the relationship between original, credit note, amendment, and replacement. Never delete transmitted evidence.

## 9. Connector contract and simulator

### 9.1 Adapter boundary

Use a versioned contract and an explicit registry of installed trusted modules. Support a documented app hook for third-party adapters. Do not import a Python path supplied by a browser or arbitrary configuration. Unknown capabilities remain unsupported.

Metadata: provider key/label, contract version, adapter version, supported environments/scenarios, request format, configuration schema, authentication method, idempotency scope/expiry, reconciliation/search guarantees, event authentication/ordering, artifact support, and pagination behavior. Capability claims require tests and provider evidence.

Operation names must match the contract exactly:

| Operation | Meaning |
| --- | --- |
| authenticate | Obtain/refresh credentials; explicit exception to token preflight recursion |
| submit | Transmit a frozen business request with stable correlation/idempotency |
| get_status | Retrieve known submission status |
| find_submission | Resolve an ambiguous outcome using a supported key/search |
| lookup_participant | Return documented endpoint/participation evidence |
| fetch_artifact | Retrieve evidence for a known remote document |
| withdraw | Optional, only with verified semantics |
| fetch_inbound | Later receiving support, with durable cursor and deduplication |

Local serialization, validation, parsing, review, and stored-file downloads are not external attempts. Optional SDK validation is local unless its contract explicitly performs network access; a network validator runs as an audited asynchronous operation.

Each adapter uses the injected audited HTTP transport for every external exchange, including auth, pagination, artifact download, and polling. A direct network call in an adapter or SDK may not bypass attempt records. Multi-request operations create linked attempts. Store no secrets in job arguments.

Normalize results into transport disposition, effect certainty, retry hints, external IDs, independent acknowledgements, structured findings, participant evidence where relevant, artifacts, safe diagnostic references, and provider event/cursor metadata. Separate business rejection from authentication, transport, and local validation failure. Persist raw sensitive evidence privately rather than in general log text.

Adding a provider may require an adapter package, fixtures, and a mapping document. Do not promise a one-file integration or let provider request fields leak into the core. Adapter-specific optional dependencies must not prevent the app from starting when that adapter is unused.

### 9.2 ASP-independent completion

Provide two test adapters over the same canonical corpus: one accepts the reference XML; one maps to a simulated JSON API. The second catches accidental assumptions that every ASP consumes the same XML. Neither establishes compatibility with an untested real ASP.

The local simulator uses a real HTTP boundary and a durable test document store. It can accept a document before the caller times out. Simulate authentication, duplicate keys, response loss, rate limiting, validation rejection, callback-before-response, duplicate/reordered callbacks, partial exchange/reporting success, missing artifacts, worker crashes, and providers without safe lookup/idempotency.

The successful demo path uses the production orchestration and validators with synthetic data. Identify Simulation on every record and generated evidence; display Accepted by simulator. Demo-only credentials and identifiers cannot be sent to Production. Tests deny outbound internet by default; only the local simulator is allowed. No artificial sleeps in normal form flows.

### 9.3 Real-provider gate

Before production: record the actual appointment/onboarding requirements, endpoint and credential ownership, contract limits, payload mapping, document-ID ownership, status/acknowledgement meaning, idempotency guarantees, cancellation/correction behavior, event verification, retrieval/retention, and provider-exit process. Verify actual emitted/returned XML and acknowledgements against the supported scenarios.

Keep old submissions bound to their original connection/configuration evidence. Credential rotation is supported; silently repointing historical polling to a new ASP is not. The registry may expose only capabilities that have been implemented and verified for that adapter version.

### 9.4 First real provider reference: Suntech

Verified from the Suntech (Tax Compliance Agent) sandbox API reference and Postman collection [S14]. This records the contract shape only. Real onboarding, returned-XML and acknowledgement verification, and production certification remain P10.

- Base `/api/v1`. Auth is OAuth2 client credentials (`client_id`, `client_secret`) to `/oauth/token/`, refresh at `/oauth/token/refresh/`, Bearer thereafter. One API client per organisation.
- Submit is `POST /invoices/` in three modes: PINT AE XML by `source_file_path` (preferred), inline JSON `detail`, or an uploaded JSON file. `invoice_type_code` is top level. This confirms the XML-first preference in section 4.5.
- Status is `GET /invoices/{id}/`. Lifecycle is Processing, Completed, Rejected, Failed, with `c3_mls_status` (exchange/delivery) and `c5_mls_status` (FTA reporting). Map these onto the independent dimensions in section 8.1; do not collapse them into one status.
- Resubmit is `PUT /invoices/{id}/resubmit/`, a full replacement on the same ID, not permitted after Completed. It maps to the correction path in section 8.6, not a byte-identical transport retry.
- Documents: `POST /documents/` returns an upload URL, `PUT` uploads the file, the invoice references it by path; download is `POST /documents/download/` with the artefact URI.
- Receiving is `GET /invoices/?direction=2` with cursor pagination. Webhook events `invoice.received` and `invoice.updated` are configured in the portal, not through the API.

Capability map for this adapter:

| Operation | Suntech |
| --- | --- |
| authenticate, submit, get_status, fetch_artifact, fetch_inbound | Supported |
| find_submission | Via list filters and cursor only; there is no dedicated ambiguity-resolution endpoint, so a lost response stays Unknown and is reconciled by correlation |
| lookup_participant | Unsupported by the API; onboarding and endpoint registration are portal-only, so buyer endpoints must exist before a live send |
| withdraw | Unsupported; a Completed invoice is corrected by credit note |

Unsupported operations stay off under the section 9.1 capability rule; the app must not synthesise them.

## 10. Permissions and evidence

### 10.1 Access model

Use UAE Peppol User and UAE Peppol Manager plus native document permissions. A role does not confer access to every Company. Shared party access follows native party permissions; own-company seller/connection administration is more restricted.

| Object/action | Required access |
| --- | --- |
| Preview/read invoice status | Native source read; create permission and allowed Company for an unsaved preview |
| Edit invoice scenario | Native source write plus app user; source must be an editable draft |
| Create/fix party or Item data | Native create/write and explicitly allowed profile fields |
| Approve/retry/correct | App manager or expressly delegated role plus Company/source access and lifecycle permission |
| Configure seller/connection/policy | App manager with allowed Company scope; credential actions separately restricted |
| Read submission/evidence/logs | Originating Company/source access; connection-only auth logs are manager-only |
| Receive callback | Provider authentication followed by server-side connection/document correlation |

Generic DocType REST writes must not bypass service transitions or immutable-field enforcement. Guard changes in controllers as well as whitelisted methods. Query reports, list counts, batch APIs, error messages, file URLs, and event search must not leak another Company's data. Background jobs re-resolve site, object, policy, and current state; they do not trust a user-supplied Company or administrator flag.

Internal service elevation, if unavoidable, is narrowly scoped after an explicit authorization check. No blanket `ignore_permissions` in public flows. Test reads and mutations as restricted users, not only Administrator.

### 10.2 Artifact contract

Store frozen canonical/source snapshots, submitted business payload, reference XML, returned invoice XML, acknowledgements, TDD where available/required, and validation evidence. Each manifest entry records kind, version, private File/reference, SHA-256, size, MIME type, source, received/created time, and relation to submission/attempt/event.

Private-file authorization must work through standard File APIs as well as custom download actions. Bind files to permission-protected records, reject public conversion, and prevent normal users from replacing/deleting evidence. Application immutability is not protection against a database administrator; backup integrity and controlled operational access are separate controls.

Redact request headers, passwords, tokens, secrets embedded in URLs/bodies, and sensitive customer data from general diagnostics before persistence. Use an allowlist for logged metadata. Do not serialize exception objects containing complete HTTP requests. Diagnostic exports are explicit, permission checked, and sanitized.

XML parsing disables external entities, DTD/network resolution, and unsafe transforms. Bound document sizes, nesting, processing time, archive expansion, and artifact downloads. Provider URLs and redirects are validated against the configured trusted hosts; do not fetch arbitrary URLs from a webhook. Production must not reach loopback, link-local/metadata, or unapproved private targets through provider configuration.

Retention, legal holds, deletion eligibility, and evidence retrieval are configuration/operating decisions tied to current obligations [S02]. Do not invent one universal number of years. Release initially preserves legal evidence by default, with no automatic purge until the retention policy is configured and tested. Temporary operational logs may have a separate bounded policy.

## 11. Operations, scale, and release quality

### 11.1 Lightweight runtime

No network requests on ordinary form events. Batch master reads and readiness queries; avoid one database query per invoice row. Cap list/report/API batches, paginate large scans, and use indexed due-work selection. Cache code lists and compiled validators by exact version; cache identity evidence with provenance and expiry.

Business caches, rate limits, locks, and jobs include the site and relevant Company/connection/environment identity. Never keep cross-site credentials or business documents in module-global caches. Share only immutable public validation artifacts by version.

Default worker concurrency is conservative per connection and site, respects provider limits, and does not starve other companies. Implement bounded claims/backpressure using existing worker infrastructure. A custom queue is justified only by measured contention; a separate broker is outside scope.

Working records keep only current findings; immutable submissions keep legal revisions. Do not store full payloads repeatedly in every log, list response, child row, or checkpoint. Reports request summary fields first; artifacts load on demand.

### 11.2 Capacity evidence

5,000 companies is an adoption target, not a requests-per-second specification. P00 records a reference deployment and expected company/invoice distribution. P09 measures one site, a multi-company site, and isolated sites without claiming that one small server can host all adopters.

Starting benchmark fixture: 4 vCPU, 8 GiB RAM, local database/Redis, pinned runtime, no ASP latency included in local measurements. Measure warm/cold behavior with 1/20/100/1,000 invoice rows, repeated/shared items, 100,000 stored invoice/control records, and 1/10/50 concurrent sessions. Dataset limits and test environment must be stated with every result.

Initial engineering targets, subject to evidence-backed review: p95 Fast check under 400 ms for 20 rows; incremental draft-save overhead under 300 ms for 20 rows; p95 Full local validation under 2 seconds for 20 rows and 10 seconds for 1,000 rows on the reference host. Measure query count, memory, queue lag, throughput, artifact growth, and error rate. These are acceptance targets, not measured claims or universal deployment guarantees.

Tests must demonstrate that master-query count does not grow by one query per row, due-work scans stay indexed as history grows, and one connection's outage does not monopolize workers. Never reduce validation coverage or permission checks to meet a timing target.

### 11.3 Recovery and observability

Use existing Frappe logging, error reporting, scheduler, and notifications. Track oldest unreviewed/unsent invoice, Unknown attempts, partial outcomes, missing evidence, invalid events, retry backlog, token expiry, scheduler health, and connection errors. Notify actionable exceptions; do not create one alert per polling attempt.

Reconciliation reports must include in-scope submitted sources with missing working records/intents, stale draft checks, unapproved submissions, abandoned Pending attempts, unknown/partial outcomes, and missing evidence. Repair tools are idempotent and permission checked. Historical-source scans never automatically transmit old documents; a manager must review scope and authorize any backfill.

Back up database, private artifacts, and required encryption-key material securely. Test restoration, hash verification, resuming pending work, and access boundaries. A restored site starts with outbound transmission held until it reconciles remote state. Non-production clones use fresh environment safeguards and cannot reuse production send capability merely because the database was copied.

Require a deployment-level production-send enablement outside restored application data, bound to the verified site/host environment. The documented restore/clone procedure starts workers paused and resets this enablement before serving requests. A database flag alone cannot provide clone safety.

### 11.4 Install, upgrade, and release

Ship idempotent migrations and app-scoped fixtures. Clean install starts Off. Re-running installation/migration cannot duplicate roles, profiles, mappings, fields, or work. Do not create profiles for every historical party synchronously during migration.

Use additive schema changes first. For large backfills, use resumable bounded batches with progress and validation. Do not modify historical frozen JSON to fit a new schema. Version readers/validators or supply explicit migration adapters for operational metadata. Test upgrade from the previous released version with pending, unknown, and completed submissions present.

Define rollback per change. Reverting application code does not reverse a data migration. Destructive schema changes require a verified backup/restore or forward-repair plan and maintainer approval. Do not automatically uninstall an app that holds legal evidence; provide a controlled export/archive and decommissioning procedure.

Release checks: locked runtime/dependencies, vulnerability/license review, required tests, migration/restore evidence, supported-scenario list, supported ERP versions, concise release notes, security-reporting route, and maintainer approval. Pin CI actions/dependencies appropriately; no credentials in pull-request jobs, fixtures, or released archives. Third-party adapters run as trusted installed code and need their own review.

Use semantic versions and document contract/migration compatibility. Promote through internal fixtures, a controlled preparation cohort, one verified live company, then staged cohorts with pause/rollback criteria. Broad rollout requires evidence from each cohort; a single successful invoice is not a release gate. No built-in telemetry is required to adopt the app.

## 12. Delivery phases

### 12.1 Gate rules

Phase states: Not started, In progress, Blocked, In review, Accepted. Code existing on a branch does not mean the phase is Accepted. Acceptance requires executable evidence and the required reviewer, recorded against the relevant commit. Critical issues stay open; never mark a phase complete because its time budget expired.

Execute one work packet at a time. Each packet ends with targeted tests, diff review, and a checkpoint. Each phase ends with the affected integration/regression suite and a reviewable pull request. Run the full release suite at P09/P10 and after a change affecting shared money, schema, permissions, or recovery contracts. Do not run every expensive test after a text-only change.

Before crossing a phase boundary, verify: entry prerequisites accepted; no unresolved critical decisions; promised tests actually ran; scope/capability flags match what works; rollback or recovery defined; state record points to the next bounded packet. Do not build downstream behavior on an invented placeholder result.

### 12.2 Sequence and acceptance

| Phase | Bounded work packets | Exit evidence | Depends on |
| --- | --- | --- | --- |
| **P00 Baseline** | a. Inspect repository/runtime and existing customizations. b. Pin source/rules/runtime candidates and verify official examples. c. Record scope, compatibility lanes, workload, and field/permission decisions. | Real source references and artifact hashes; compatible runtime starts; official positive and negative validation example runs; unresolved facts explicitly block affected paths. No application feature claims. | None |
| **P01 Contracts and domain** | a. Canonical/finding/adapter schemas and deterministic hashing. b. Scope/document/tax decision tables and money examples. c. Reference serializer and locked validator wrapper. | Pure tests independent of Frappe/providers; schema round trips; official examples and altered negative cases; repeatable serialization; no money or rule assumptions without evidence. | P00 |
| **P02 Configuration and masters** | a. App/module/roles, settings/ASP configuration and encryption proof. b. Seller/company/party mapping and native forms. c. Tax/UOM mappings and idempotent fixtures. | Clean install starts Off; incomplete profiles save; uniqueness under concurrent creation; restricted users cannot obtain secrets or configure other companies; repeated migrate is safe. | P01 |
| **P03 ERP extraction** | a. Pinned ERP source map and selected-address resolution. b. Line/tax/discount/currency extraction. c. Ordinary invoice/credit-note canonical-to-XML path. | Independently calculated ERP fixtures pass Full validation and reconcile to source; duplicate item codes, inclusive VAT, mixed taxes, foreign currency, and return signs covered. No invoice event hooks yet. | P02 |
| **P04 Draft workflow** | a. Working-record upsert and revision checks. b. Fast/Full preview and save/submit gate integration. c. Native Quick Entry extension, Company setup, invoice notice/dialog, Item bulk fixes. | Saveable incomplete drafts; current unsaved preview; one working row; no temporary records; company/address changes invalidate readiness; zero invoice fields; browser and API paths agree. Live activation remains gated. | P03 |
| **P05 Submission ledger** | a. Frozen revisions and private artifact manifests. b. Approval and atomic outbox/claim logic. c. Cancellation/correction and immutable-field controls. | Transaction rollback creates no sendable work; concurrent approval/submit does not duplicate intent; retries preserve bytes; source/master changes do not rewrite snapshots; permissions and cancellation races covered without real ASP calls. | P04 |
| **P06 Transport and simulator** | a. Audited transport/auth/result contracts. b. Stateful HTTP simulator plus XML and JSON adapters. c. Events, retries, reconciliation, lease/crash recovery. | Same production orchestration passes the failure matrix; no unlogged external requests, duplicate remote invoices under supported guarantees, false acceptance, or unsafe resend when guarantees are absent. | P05 |
| **P07 Operations and upgrade** | a. Readiness/reconciliation reports, notifications, pause/resume. b. Private downloads, diagnostic redaction, attack and cross-company tests. c. Upgrade, backup/restore, provider-change and clone safeguards. | Restricted-user and hostile-input tests; recoverable pending/unknown work after restart/restore; install/upgrade fixtures retain evidence and other apps' customizations. Security checks already exist in earlier phases; this phase broadens them. | P06 |
| **P08 Scenario coverage** | One separate packet per enabled advanced scenario from section 6.3; extend source map, schema only if required, fixtures, routing, and correction rules together. | Every advertised scenario has positive/negative/accounting tests and evidence. Deferred scenarios remain visibly unsupported. Ordinary invoice corpus still passes. | P07 |
| **P09 Pre-ASP candidate** | a. Run both supported framework lanes and workload suite. b. Independent financial/security/recovery review. c. Package installable preparation release and concise operations/support documentation. | All applicable section 13 cases pass; unresolved capabilities published; local app works without real ASP credentials; native UI acceptance; measured capacity evidence; maintainers approve the candidate. | P08 |
| **P10 Real ASP and Live** | a. Verify contract and implement one provider adapter. b. Real sandbox fixtures, status/evidence/correction/recovery tests. c. Approved Company activation and staged live rollout. | Real provider evidence for supported routes; no unmapped required statuses; credentials/onboarding verified; local and returned XML checks; reporting/delivery evidence; recovery and monitoring proven before broader rollout. | P09 plus real ASP access |
| **P11 Optional UI design** | a. Identify measured usability gaps in native workflows. b. Approve a bounded design. c. Implement without changing domain/service contracts. | Native baseline remains usable; no new source of business rules; accessibility, permissions, responsive behavior, and workload targets remain satisfied. No new frontend framework without a justified decision. | P09; independent of ASP timing |
| **P12 Receiving and self-billing** | a. ASP inbox/cursor/deduplication and matching review. b. Controlled Purchase Invoice creation. c. Separate supported self-billing issuance model/rules/agreements. | Authenticated inbound evidence, stable cursor recovery, no duplicate purchases, no supplier/item auto-creation or automatic posting without configured review, correct issuer/recipient roles, dedicated official self-billing validation. | P09 plus verified receiving/provider contracts |

P09 is the main completion milestone while ASP access is unavailable. P10 is an external integration dependency, not a reason to leave P01-P09 unfinished. P11 is optional. P12 is a new scope increment; do not scaffold its UI or purchase-posting behavior in the initial release. If its inbox needs a landing record, introduce `UAE Peppol Inbound` through that phase's reviewed schema change.

### 12.3 Required review artifacts

Keep each pull request short and factual:

- Problem and resulting behavior.
- Requirement/test IDs and affected contracts.
- Exact checks run, result, and evidence reference; clearly label Not run.
- Data migration, operational recovery, or compatibility impact, if any.
- Remaining limitations that affect the advertised scope.

Do not produce a new narrative report for every function. Prefer executable fixtures and concise decision entries. Interface, rule, or schema changes update their authoritative contract once and link the affected tests. Review source changes separately from generated metadata and downloaded rules.

### 12.4 Release authorization

Maintainer review gates code promotion; finance/compliance review gates interpretation of supported business scenarios; verified provider evidence gates Live capability. Routine local implementation/checkpoints can proceed within approved scope. Creating or modifying real provider appointments, live transmission, production deployment, public releases, and destructive data operations require the applicable owner's authorization. No test tool or coding session may invent it.

## 13. Acceptance matrix

Test IDs are stable and referenced by phases/pull requests. Tests use real domain functions and database behavior where the risk concerns those boundaries. Use pure fixtures for arithmetic, database integration tests for transactions/permissions, and the HTTP simulator for external uncertainty. Mock only the boundary being isolated.

| ID | Acceptance case | Required evidence | First gate |
| --- | --- | --- | --- |
| A01 | Supported source/spec/runtime pins | Resolved commits/releases, actual artifact hashes, validator result on official samples | P00 |
| A02 | Canonical determinism and validation | Stable decimal/hash output; unknown fields rejected; intentionally invalid XML fails the expected official rule | P01 |
| A03 | Ordinary money | Independent expected values for section 5 fixtures; posted source and canonical/XML reconcile | P03 |
| A04 | Tax complexity | Inclusive/exclusive, repeated codes, mixed categories, allowances/charges, row overrides, rounding, and both currency paths | P03 |
| A05 | Credit notes | Correct tax/commercial codes, sign treatment, reason/references including supported exception; no blanket absolute-value conversion | P03 |
| A06 | Shared master identity | Own TIN versus VAT-group registration; foreign endpoint; same party used by UAE and foreign companies; no country-driven tax rewrite | P02/P03 |
| A07 | Quick Entry transaction | Customer and Supplier each create one supplied address/contact/profile set; failure rolls back coherently; full-form fallback works | P04 |
| A08 | Draft/save/preview | Missing information saves; unsaved preview changes no records; repeated/concurrent save creates one working row; stale responses ignored | P04 |
| A09 | Scope enforcement | Off/Preparation/Live behavior; default company and company/address switch; unsupported case blocked in Live; API matches browser | P04 |
| A10 | Explicit master fix | Repeated Item needs one fix; user permissions enforced; invoice-only override does not change global Item data | P04 |
| A11 | Atomic source/submission | Rollback after source validation, after snapshot creation, and before enqueue leaves no external work; committed intent survives queue loss | P05 |
| A12 | Approval/immutability | Wrong revision/hash cannot be approved; financial/route/connection changes require new revision; retry after master/payment change preserves payload | P05 |
| A13 | Concurrent sends | Multiple workers and expired leases cannot produce unsafe duplicate sends; fencing prevents stale local results overwriting newer state | P06 |
| A14 | Ambiguous send | Simulator accepts then drops response; recovery finds one remote document; provider without safe guarantees remains held | P06 |
| A15 | Retry classes | 429, 401, known rejection, network loss, ambiguous 5xx; stable key/bytes; bounded retry and Retry-After honored | P06 |
| A16 | Event integrity | Forged, duplicate, replayed, reordered, conflicting-ID, wrong-environment, and callback-before-response cases | P06 |
| A17 | Independent outcomes | Delivery success/report failure and reverse; report-only path; missing optional/required artifacts; no false Complete | P06 |
| A18 | Correction/cancellation | Stop-unsent versus sending/Unknown race; transmitted correction path preserves original; no generic remote cancellation claim | P05/P06 |
| A19 | Company access | Restricted users cannot read/mutate another Company's statuses, counts, logs, events, artifacts, or source-derived errors | Every storage/API phase; complete P07 |
| A20 | Secrets and hostile input | Credential encryption/rotation, redaction, signed event checks, XXE/entity expansion, URL/redirect controls, request/file limits | P02/P06/P07 |
| A21 | Migrations and coexistence | Clean install, repeated migration, previous-version upgrade, rename/merge conflicts, another app's Quick Entry/fields/notice preserved | P02/P04/P07 |
| A22 | Operational recovery | Queue loss, stranded Pending, scheduler restart, disk/file failure, backup restore, hash check, production clone send prevention | P07 |
| A23 | Scenario completeness | Each enabled advanced scenario has source/amount/identity/routing/reference/correction cases; unsupported combinations rejected | P08 |
| A24 | Resource behavior | Declared reference workload, p95 timings, bounded memory/batches, indexed scans, no row-wise query explosion or connection starvation | P09 |
| A25 | Real provider | Actual API mapping, auth/onboarding, idempotency/search limits, returned XML, acknowledgements, event checks, retrieval and recovery | P10 |
| A26 | Receiving/self-billing | Inbound cursor/deduplication, restricted matching/posting, role reversal and applicable official schema family | P12 |

Additional failure checks apply when their boundary is introduced: out-of-space while persisting evidence must prevent a send lacking required durable payload; duplicate party/profile requests must not merge legal entities by name/TRN; renamed/merged masters must resolve profile conflicts without altering historical evidence; a new ruleset must not mutate old payloads or silently reuse an old approval.

A property-based arithmetic check may supplement explicit expected examples. It does not replace independent fixtures or official validation. Golden files require review of their substantive changes; no bulk update of expected XML to match a changed serializer without investigating why.

There is no mandatory arbitrary line-coverage percentage. Critical invariants need behavioral coverage, including failure paths. Skipped database/concurrency/security/provider tests remain Not run and block the gate that needs them. CI must not pass a required job merely because its fixture, dependency, or secret was missing.

## 14. Evidence baseline and unresolved implementation facts

The sources below establish the starting reference, not perpetual applicability. P00 pins the exact supported snapshots. A later official change needs a decision, implementation impact assessment, regression fixtures, and reviewed release. Do not silently reinterpret this specification through an unversioned URL.

| ID | Source | Use |
| --- | --- | --- |
| S01 | [PINT AE Billing publication][S01] and its downloadable resources | Semantic model, XML bindings, shared/AE validation, examples, versions |
| S02 | [MoF Guidelines v1.1][S02] | Identity/tax groups, scenarios, storage, advance/retention clarification |
| S03a / S03b | [Invoice codes][S03a] / [Credit-note codes][S03b] | Document type values |
| S04 | [IBR-116-AE][S04] | Margin category rule |
| S05 | [IBR-132-AE][S05] | UAE VAT identifier validation context |
| S06 | [PINT AE rules][S06] | Scenario and reference requirements; follow individual rule links for exact conditions |
| S07 | [ERPNext tax controller, v15][S07] | Starting source evidence; pin actual supported commits and compare v16 |
| S08 | [Frappe controller lifecycle][S08] | Hook order/availability, verified against the selected release source |
| S09 | [Frappe background jobs][S09] | Queue/after-commit behavior; durable outbox remains an application responsibility |
| S10 | [ERPNext shared Quick Entry, v15][S10] | Native party/contact/address extension baseline |
| S11 | [Frappe DocType conventions][S11] | Names and database-table conventions |
| S12 | [AGPL-3.0-only license text][S12] | Chosen license, required notices, source obligations |
| S13 | [MoF UAE eInvoicing portal][S13] | Current programme documents and five-corner exchange/reporting model |
| S14 | [Suntech sandbox API reference][S14] and Postman collection | First real ASP contract shape: OAuth2, submit modes, status/MLS model, resubmit, documents, events, receiving; production certification remains P10 |

Resolve these facts in the named phase rather than guessing:

| Fact | Owner phase | Consequence until resolved |
| --- | --- | --- |
| Exact ERPNext/Frappe pairs, native fields/hooks, existing extension behavior | P00 | No compatibility claim or undocumented override |
| Official resource hashes, validator engine/platform support, effective rules | P00/P01 | No Full validation or Live readiness claim |
| Real site's tax templates/accounts, currency/rate policy, scope and issue dates | P02/P03 and deployment setup | Affected mappings remain incomplete |
| Child credential encryption behavior and private-file authorization | P02/P05 | No real credential or evidence release path |
| Advanced scenario interpretation/accounting | P08 | Scenario remains unsupported |
| ASP payload/auth/onboarding/IDs/status/idempotency/evidence guarantees | P10 | First target is Suntech; sandbox access and API reference obtained [S14], so P10 can begin against it; production certification and returned-XML/acknowledgement evidence remain Unresolved |
| Deployment workload, retention, reporting deadlines, operational recovery targets | P00/P07/P09 and deployment setup | No capacity, retention, or timing compliance claim |

Do not add forecasts, marketing promises, model-specific prompts, UI mockups, or a code handover to this specification. Keep implementation evidence in version control and the application's behavior in executable contracts and tests.

[S01]: https://docs.peppol.eu/poac/ae/pint-ae/
[S02]: https://mof.gov.ae/wp-content/uploads/2026/06/UAE-Electronic-Invoicing-Guidelines_V-1.1-01June2026.pdf
[S03a]: https://docs.peppol.eu/poac/ae/pint-ae/trn-invoice/codelist/UNCL1001-inv/
[S03b]: https://docs.peppol.eu/poac/ae/pint-ae/trn-creditnote/codelist/UNCL1001-cn/
[S04]: https://docs.peppol.eu/poac/ae/pint-ae/trn-invoice/rule/ibr-116-ae/
[S05]: https://docs.peppol.eu/poac/ae/pint-ae/trn-invoice/rule/ibr-132-ae/
[S06]: https://docs.peppol.eu/poac/ae/pint-ae/trn-invoice/businessrule/
[S07]: https://github.com/frappe/erpnext/blob/version-15/erpnext/controllers/taxes_and_totals.py
[S08]: https://docs.frappe.io/framework/user/en/basics/doctypes/controllers
[S09]: https://docs.frappe.io/framework/user/en/api/background_jobs
[S10]: https://github.com/frappe/erpnext/blob/version-15/erpnext/public/js/utils/contact_address_quick_entry.js
[S11]: https://docs.frappe.io/framework/user/en/basics/doctypes
[S12]: https://spdx.org/licenses/AGPL-3.0-only.html
[S13]: https://mof.gov.ae/en/about-us/initiatives/einvoicing/
[S14]: https://portal-sandbox.taxcomplianceagent.com/docs/api
