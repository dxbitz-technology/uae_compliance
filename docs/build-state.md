# Build state

Phase: P00 to P07 are done and merged, bar receiving events and upgrade testing, neither of which can be done yet. P08 scenario coverage is in progress.
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

State: Done.
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
- P05c: cancellation, correction and the immutable field controls. Done.

Cancelling in ERPNext and cancelling at the other end are not the same act.
ERPNext cancelling succeeded says nothing about a document that has already
left, so nothing here ever marks a remote document cancelled because a local
one was.

And no attempts having been made is not proof that nothing was issued. It is
proof that we made no attempts. Where that bites is the request that went out
and never came back, which is held rather than guessed either way.

A correction is not a retry. A retry sends the same bytes because nothing
about the document was wrong. A correction says it was, so it gets a new
revision, points back at the one it replaces, carries a different key, and
needs approving on its own.

Checked on uae.local, six cases:

| Submission | Cancelling the invoice |
| --- | --- |
| Ready, nothing sent | Allowed, and the intent is stopped first |
| Sending | Refused, still in flight |
| Unknown | Refused, still in flight |
| Delivered | Refused, a credit note is the way |
| Reported and accepted | Refused, a credit note is the way |
| A request that never came back | Refused, reconcile first |

And a correction on a rejected submission made revision 2 pointing back at
revision 1, unapproved, with its own key, while revision 1 went to
Superseded carrying the reason.

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

## P06 Transport and simulator

State: In progress.
Requirement IDs: spec 8.3 the durable worker boundary, 8.4 the retry rules, 9.1 the adapter boundary, 10.2 redaction, 12.2 P06, acceptance A13 to A17.

- P06a: the audited transport and the result contract. Done, in the connector lane.
- P06b: the simulator and the two test adapters. Done, in the connector lane.
- P06c: sending and retries. Done.
- P06d: reconciliation and the event record. Reconciliation done, events recorded but not yet received.

Reconciliation does two jobs. It asks a provider where a document has got
to, and it deals with attempts that went out and never came back. The second
is the one that matters: an attempt whose claim ran out is not evidence that
the worker stopped or that the provider did not take the document. It is
evidence that we stopped hearing. So nothing retries one. It asks, and where
it cannot ask it holds the work and says why.

Checked against the simulator. Asking moved delivery from Pending to
Delivered and reporting to Accepted, and the document still did not become
Complete, because the route also needs its evidence and the provider says
that is still pending. An attempt left hanging for half an hour was marked
abandoned and its submission moved to Unknown, not to failed, and nothing
sent anything again.

The evidence gap is real and recorded as D055. The contract hands back a
reference to a provider's file and has nowhere to put the bytes, so the file
cannot be kept. That needs a change to something P01 settled, so it has its
own packet rather than being half done here.

The order in the sender is the whole point. Claim the work, write down that
an attempt is starting, commit. Only then make the request, holding no
database lock while it is in flight. Then, in a new transaction, write down
what came back after checking that a newer worker has not been and gone.

What the provider said is never read here. The adapter turns it into the
contract's own words and the sender reads those, so a provider status code
never reaches the app.

Checked on uae.local against the simulator over a real socket. A frozen
document went out and came back accepted: receipt Received, delivery
Pending, reporting Pending, and the state Awaiting outcome rather than
Complete, because transport succeeding says nothing about either of the
other two. Three attempt records were written for one send: the business
attempt, the sign in, and the send itself.

Two things this turned up, both now fixed. The recorder was writing a
timestamp the database would not take, and it failed quietly rather than
taking the send down with it, which is what it is supposed to do but meant
the audit rows were missing. And the provider reference was being read under
a key no adapter uses.

Worth recording: a run that died mid-flight left the submission in Sending
with a Pending attempt, and it was not picked up again. That is the design.
Clearing it is reconciliation's job, which is the next packet.

## P07 Operations and upgrade

State: In progress.
Requirement IDs: spec 7.4 the two reports, 11.3 recovery and what to watch, 12.2 P07, acceptance A19 and A22.

- P07a: the reports, the alerts and pause and resume. Done.
- P07b: private downloads, redaction, and the cross company checks. Done.

The framework already ties a private file to whatever it is attached to, so
reading a submission's evidence needs permission on that submission. What it
did not stop was somebody turning a private file public, or swapping the
bytes under a hash that is supposed to prove what was sent. Both are refused
now, and so is deleting evidence.

The check that mattered found a real leak. A restricted user could list
submissions and attempt records belonging to a company they had no
permission for. `frappe.get_all` does not check permissions and
`frappe.get_list` does, which is the framework's own design, and the reports
were using the first. They use the second now, and the same user gets no
rows. The workers still use `get_all` on purpose, which is written down in
AGENTS.md so it is not tidied away later.
- P07c: restore and clone safeguards. Done. Upgrade testing waits for a previous release to upgrade from.

Restoring a production backup onto a test server gives you a database that
believes everything it believed before, including that it may transmit. That
is how a staging box sends live invoices to real customers.

So the permission to send in Production does not live in the database. It
lives in the site's configuration file, which a restore does not bring, and
it names the site it was granted for. Copy the database anywhere and the
copy cannot send.

The database still records which machine last sent from this site. When that
changes, outbound work pauses and says why, because the likeliest
explanation is that somebody restored it somewhere else. A manager lifts it
deliberately after a genuine move.

Checked on uae.local: a deployment that was never granted the key cannot
send in Production; pointing the database at a different machine paused
outbound, gave a reason and emptied the work queue; and confirming the move
lifted it.

Two reports. Readiness carries the reason across in its last column, so
somebody can work through a morning's worth without opening anything.
Reconciliation is the one to open when you want to know whether anything has
been forgotten, and it deliberately does not only list provider problems.
Most of what goes wrong in a system like this is work that fell between two
steps: an invoice submitted with nothing watching it, a submission nobody
approved, an attempt that went out and never came back.

One message a day carrying everything, rather than one per problem. A system
that sends an alert per polling attempt teaches people to ignore its alerts,
and then the one that mattered is ignored too.

Fixed something the report exposed. A raw Python error was reaching a field
people read. The plain sentence goes in the field now and the technical
detail goes to the error log, which is where it belongs.

## P08 Scenario coverage

State: In progress.
Requirement IDs: spec 2.3 the capability rows, 6.2 and 6.3 scenario structure, 12.2 P08, acceptance A23.

- P08a: the scenario table and the two parties it needs. Done.
- P08b: reverse charge, advances and retention, which need the accounting settling first.

The table was read out of the pinned rules rather than written from scratch.
Thirteen rules key off the eight character transaction string, and each one
says what its scenario makes necessary. Every row cites the rule that
demands it, and on a real invoice each local finding fired alongside the
official rule it names, which is how the reading was checked.

| Scenario | State | What it needs |
| --- | --- | --- |
| Free zone | Supported | The beneficiary's identifier |
| Deemed supply | Supported | A payment means, and a due date once anything is payable |
| Margin scheme | Not supported | Every line at category N, and the margin worked out |
| Summary | Supported | The period it covers |
| Continuous supply | Supported | Nothing beyond an ordinary invoice |
| Billed by an agent | Supported | The principal, and a seller registration that differs from it |
| E-commerce | Supported | Where it was delivered |
| Export | Supported | Where the goods went, and who the buyer is |

Checked on uae.local against a real invoice, every flag one at a time and
two together. Each one that was missing something said which field, before
the XML was built. Each one that had what it needed passed the schema and
both rule layers. Margin scheme is refused rather than approximated.

Two serializer gaps came out of it, recorded as D058. The party
identification element was never written, and the principal was going into
the payee element rather than the seller supplier one, so the two rules
looking for it never found it.

## Receiving, brought forward

The maintainer asked for the buying side before P09 rather than at P12. The
reasoning is in D059: buying is half of what this app is for on a UAE site,
and finding out at P12 that the model does not fit would mean redoing work
from P03 onward.

Done: the connector contract now carries fetched bytes, the simulator has an
inbox, the adapter reads a page of it with a cursor, and arrived documents
land as their own records, parsed, matched where they can be matched and
deduplicated.

Turning one into a Purchase Invoice is done, in two steps and never one.
The first says what would happen and what stands in the way. The second
makes a draft, which a person submits. Never a submitted document, because
posting somebody else's claim without anybody reading it is what this whole
approach exists to avoid.

Checked against a published example invoice: the draft came out at net 1000,
tax 50, total 1050, which is what their document said it was owed. Entering
it a second time is refused, naming what it became the first time. The one
whose sender matches nothing is refused and says so.

Nothing arriving becomes a purchase on its own. No supplier is created, no
item is invented, nothing posts. A sender is matched by tax number or by the
network address on a supplier profile, never by name, and where nothing
matches the document waits and says so.

Checked against the simulator with two real published invoices seeded into
an inbox, neither of them written by this app. Both were pulled in, read,
and landed. The one whose sender matched a supplier came in as Received and
the other as Unmatched. Collecting again from the start stored nothing new.

One bug worth knowing about. Frappe fills a company link from the site
default when nothing sets it, so the first run quietly attributed two
suppliers' invoices to whichever company happened to be default. On a
document somebody else wrote that is worse than leaving it blank.

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
