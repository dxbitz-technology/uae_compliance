# Build state

Phase: P00, P01 and P02 are done and merged. P03 ERP extraction is in progress.
Baseline: spec version 2.1, 18-09-2026. It adds two self-billing document codes for P12, ties scenario flags to the sixteen official use cases, and names Suntech as the first real provider in section 9.4.
Branch: develop. Pull requests merge on a passing ci check. No review gate.
Last verified code commit: develop at the P02 merge. 290 pure tests, 33 site tests.
Development site: uae.local on bench /Users/aslam/frappe-local/loc16, served at localhost:8002. Frappe v16.22.0 (567c05b), ERPNext v16.26.2 (d1d3b24), Python 3.14.5, MariaDB 12.2.2, Node 24.16.0, macOS arm64. Not the reference host in spec 11.2, so no timing here is a capacity claim.

## Working rhythm from 18-09-2026

The maintainer asked for speed over evidence until every phase exists. Recorded because it changes what the phase gates below mean.

- One pull request per sub-phase, merged on a green lint and the existing tests.
- No new test suites, no deliberate breaks, no site tests per packet, no hand-test documents.
- The 290 pure tests still run because they cost under a second. The app still has to import and migrate before a pull request opens.
- Decisions are recorded only at a real fork in the road, in two lines.
- The deferred testing lands in P09, which the spec already defines as the acceptance and review pass. Every phase reached this way is In progress, never Accepted.

## Two lanes

Lane A is the invoice chain and is strictly sequential: P03 extraction, P04 draft workflow, P05 submission ledger, P06c events and recovery.

Lane B needs only the connector contract that P01 finished, so it runs alongside: the local simulator, the XML adapter, the JSON adapter, then the Suntech adapter against the sandbox reference. It touches connectors/ and nothing Lane A owns.

## What is built

| Phase | What it settled | Decisions |
| --- | --- | --- |
| P00 | Pinned rules, schema, examples and the XSLT runtime, with checksums | D001 to D026 |
| P01 | Encoding and hashes, findings and readiness, the canonical invoice, the adapter contract, money rules, company modes, the document type matrix, the serializer and the validator wrapper | D027 to D043 |
| P02 | Module and roles, settings, the provider connection and its credentials, seller and party profiles, tax category mapping | D044 to D049 |

## P03 ERP extraction

State: In progress.
Requirement IDs: spec 5.2 source map, 5.3 money rules, 12.2 P03, acceptance A03 to A06.

- P03a: the source map, master resolution and the address frozen per invoice. Done.
- P03b: lines, taxes, discounts and currency.
- P03c: an ordinary invoice and credit note all the way to XML the official rules accept.

Exclusions: no invoice hooks, no working record, no UI. Those are P04.

## Still open for the maintainer

- The published credit note example that fails its own schema (D008).
- Spec 5.2 names a tax breakup field version 16 no longer has (D019).
- Spec 9.4 cites a section 4.5 that does not exist in the document.
- Real tax templates, accounts and currency policy from a client site. Until then the mappings stay incomplete.
- No Frappe v15 bench on this host, so that lane is unverified. version-15 and version-14 are later work.
