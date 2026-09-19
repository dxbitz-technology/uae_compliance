# Build state

Phase: P00 to P04 are done and merged. P05 submission ledger is in progress.
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

State: Done.
Requirement IDs: spec 5.2 source map, 5.3 money rules, 12.2 P03, acceptance A03 to A06.

- P03a: the source map, master resolution and the address frozen per invoice. Done.
- P03b: lines, taxes, discounts and currency. Done.
- P03c: an ordinary invoice and credit note all the way to XML the official rules accept. Done.

Checked on uae.local against a real Sales Invoice built to the first money
fixture in spec 5.3, two units at AED 100 with a line discount of 20 and VAT
at 5 percent. ERPNext posted net 180, tax 9, total 189. Extraction, the money
rules, the schema, the shared rules and the AE rules all pass on the invoice.
The credit note made from it passes too once a reason code is supplied, which
is a person's input and arrives with the working record in P04. Until then
extraction reports it as missing.

To rebuild that invoice on a development site:

```
bench --site uae.local console
>>> from uae_compliance.development.build_invoice import run
>>> run()
```

It uses its own company, Peppol Demo Co, so it never collides with the site
tests, which own UAE Peppol Test Company.

Exclusions: no invoice hooks, no working record, no UI. Those are P04.

## P04 Draft workflow

State: In progress.
Requirement IDs: spec 4.2 the working record, 7.1 the one validation service, 7.2 the native lifecycle, 7.3 party and company entry, 7.5 the service surface, 12.2 P04, acceptance A07 to A10.

- P04a: the working record, its upsert on save, and the revision check. Done.
- P04b: Fast and Full preview, and the save and submit gates. Done.

One service answers both the form and the server, so what somebody sees
before saving is what the submit gate decides with. Fast covers scope,
masters, mapping and arithmetic. Full adds the canonical model, the XML, the
schema and both rule layers. Nothing reaches the network at any level.

Checked on uae.local against the demo invoice: Fast says further checks
required, Full says Ready locally with every stage passed. In Preparation an
invoice that would fail still submits and says what would have stopped it.
In Live it does not submit, and the message names what to fix rather than
repeating a rule id per failure. An incomplete draft still saves either way.
- P04c: the invoice notice and the details dialog. Done.
- P04d: the quick entry extension, company setup and the bulk item fix. Done.

The quick entry form takes whatever class is installed and puts itself on
top, so another app that already extended the same form keeps working. The
country moves up, because it decides which questions make sense, and the tax
section sits below and collapsed. Not sure stays a real answer everywhere.

The party, its address and contact, and its profile are made in one request,
so all of them arrive or none do. The country prefills both the postal and
the established country, which are separate facts from then on.

Company setup puts a company into Preparation and nothing more. It collects
and checks and sends nothing, so a company can be set up long before there is
a provider. Running it twice changes nothing.

Checked in the browser: the dialog shows the country first, the tax section
expands, the VAT number appears only once somebody says Registered, and
saving made the customer, the address and the profile together with the
lookup result left at Not checked.

The form carries one native headline notice and one button, and nothing at
all on a company that is switched off. The dialog groups findings by where
the fix is, your company, the customer, addresses, items or the invoice, and
carries the scenario flags and the credit note reason. A submitted invoice
gets the findings and no save button, because there is nothing left to edit.

Checked in the browser on uae.local. The notice sits alongside ERPNext's own
without replacing it. Ticking Export and saving moved the flag onto the
record, into the document, and into the official positional string as
00000001, where the AE rules then refused it under ibr-152-ae because a
standard rated domestic invoice is not an export. That is the scenario flags
doing their job rather than being decoration.

P04a holds to three rules. One record per invoice, ever. Nothing is created
for a company that is switched off, so a site that never asked for the app
sees no trace of it. And the record never writes back to the invoice calling
it, which would put the save into a loop.

Checked on uae.local: saving the demo invoice makes exactly one record and
saving it again does not make a second; an invoice for a company with no
seller binding makes none at all; a person's edit counts the input revision
up and a check result does not; and readiness cannot be set by hand.

## P05 Submission ledger

State: In progress.
Requirement IDs: spec 4.2 the submission record, 8.1 the independent states, 8.2 freeze and approval, 10.2 the artifact contract, 12.2 P05, acceptance A11 and A12.

- P05a: the frozen submission and its artifacts. Done.
- P05b: approval and the atomic claim. Done.

An approval names the exact content it agreed to. If that content moves the
approval stops applying, because otherwise a different document goes out
under somebody's name. Review is required unless a person has turned it off
for that company, and a missing setting means it is required. Where it is
off, the approval is recorded as a policy one so nobody later reads an
unreviewed document as a reviewed one.

A claim is one atomic update or nothing. Everything it tests sits in the
same where clause, so there is no gap between checking and taking. A fencing
token counts up on every claim, which is what stops a worker whose claim ran
out from writing over a newer answer.

The attempt record is written and committed before any request goes out. If
the process dies in between, that record is the only thing saying a request
may have reached them, and without it the next worker would send the same
invoice again believing nothing had happened.

Checked on uae.local: approving with the wrong hash is refused and with the
right one works; two workers reaching for the same submission means exactly
one gets it; a stale fencing token cannot write a result; policy approval
declines while review is required and works once it is off, recorded as
Policy; and a pause empties the due list without touching anything else.
- P05c: cancellation, correction and the immutable field controls.

Freezing happens in the invoice's own transaction, so the invoice and its
submission arrive together or neither does. The control row is locked first,
so two people submitting at once produce one submission rather than two
documents carrying the same number. Only Live freezes. Preparation checks,
shows and sends nothing, so it has nothing to freeze.

The bytes are written and read back before the work could ever be picked up.
A database transaction does not roll back a file, and work that can transmit
without its request evidence is worse than work that cannot transmit.

Checked on uae.local, five things:

- Submitting in Live froze a submission at revision 1, Awaiting review, not
  approved, with a stable key taken from the document identifier rather than
  from a display series, separate hashes for the business content and the
  exact bytes, and both artifacts stored and read back.
- A frozen field cannot be edited afterwards.
- An approval whose hash does not match the content is refused.
- Editing the buyer's address afterwards did not move the frozen hash.
- Rolling the transaction back left no submission and no sendable work.

One gap, for P07. A rollback removes the file records but the bytes stay on
disk with nothing pointing at them. Cleaning those up needs a sweep that can
prove a file is unreferenced, which belongs with the other operational
repair tools.

## Lane B, alongside

The connector work needed only the contract P01 settled, so it ran in
parallel and is finished for now. The adapter registry and the audited way
out, the local simulator over a real socket covering thirteen awkward cases,
and the two test adapters that prove one canonical document can be sent as
XML to one provider and as JSON to another. 105 checks, all over a real
socket.

Three things the Suntech capability map asks for that the contract cannot say
yet, listed for a later decision: a provider that can be searched but not by
the key that was sent; a provider that replaces a document in place rather
than issuing a new identifier; and the two it simply does not support, which
the existing rule already handles.

## Still open for the maintainer

- The published credit note example that fails its own schema (D008).
- Spec 5.2 names a tax breakup field version 16 no longer has (D019).
- Spec 9.4 cites a section 4.5 that does not exist in the document.
- Real tax templates, accounts and currency policy from a client site. Until then the mappings stay incomplete.
- No Frappe v15 bench on this host, so that lane is unverified. version-15 and version-14 are later work.
