# Build state

Phase: P01 Contracts and domain is complete and merged. P02 is next.
Branch: develop. It takes pull requests with a passing ci check; an approving review is not required, which the maintainer relaxed on 17-09-2026. Tags stay immutable.
Last verified code commit: develop at the merge of the serializer, all eight gates passing, 290 tests.
Development site: uae.local on bench /Users/aslam/frappe-local/loc16. Frappe v16.22.0 (567c05b), ERPNext v16.26.2 (d1d3b24), Python 3.14.5, MariaDB 12.2.2, Node 24.16.0, macOS arm64 host. This is not the reference host in spec 11.2, so no timing here is a capacity claim.

## What P01 delivered

| Packet | What it settled | Decisions |
| --- | --- | --- |
| P01a | Deterministic encoding and two hashes, the finding shape and the readiness rule, the schema machinery, the canonical invoice, the adapter contract | D027 to D035 |
| P01b | The money rules against the six worked examples, company modes, the document type matrix | D036 to D039 |
| P01c | The wrapper that runs the official rules, and the serializer that produces XML they accept | D040 to D043 |

Exit evidence for P01: pure tests with no framework and no provider; the canonical model round trips and unknown fields are refused; the published examples pass and deliberately broken copies fail the expected rule by id; invoices we build ourselves are accepted by the real published schema and both rule layers; writing the same document twice gives the same bytes. No money or rule value was taken on trust: each is cited to the pinned publication.

## Still open for the maintainer

- Report the published credit note example that fails its own schema, or wait for a later release (D008).
- Amend spec 5.2, which names a tax breakup field version 16 no longer has (D019).
- Decide whether the UOM code DocType is still needed, since UOM already carries a common code field (D026).
- Decide whether docs/evidence/p00 stays now that P01 has used it.
- Three contract changes the serializer forced on the canonical model are recorded in D043 and worth a look, since they change the model P02 and P03 build on.

## Blockers

- No Frappe v15 bench on this host, so that lane stays unverified. version-15 and version-14 are the maintainer's later work.
- uae.local has no hosts entry and this session has no sudo, so browser access needs one line from the maintainer. This starts to matter in P02, which is the first phase with anything to look at.

## Packet P02a Module, roles, settings and the provider connection

State: In progress on branch p02a-settings, one pull request against develop.
Requirement IDs: spec 4.1 (the settings and provider connection records and their constraints), 10.1 (the two roles and what each may do), 2.1 (a clean install starts off), 11.4 (a repeated migration is safe), 12.2 P02a, 13 A20 and A21.
Expected behavior: the module, the two roles, one settings record per site and the provider connection record with its credential rows. Credentials are stored through the framework's encrypted field and never returned.
Affected interfaces: everything P02b and P02c add to, and the connection the worker reads in P06.
Likely files: the DocType definitions under uae_compliance/uae_e_invoicing, their controllers, site tests, a decision entry.
Checks: a clean install leaves every company switched off; a provider and an environment cannot be repurposed once the connection has been used; a credential value is never returned by any read path; deleting a credential row or its parent leaves no secret behind; a restricted user cannot read a credential or configure another company; running the migration twice changes nothing.
Exclusions: no seller or party profiles, no tax or unit mappings, no fixtures beyond the roles, no invoice behaviour. Those are P02b and P02c.

Note on evidence. This is the first packet whose checks need a real site, and the current CI has none. A second workflow that stands up a database and runs site tests is being built alongside this packet. Until it passes, every site test here is Not run in CI and proved locally only, which is stated rather than glossed over.

## Next packets

P02b seller and party profiles. P02c tax and unit mappings with the install and migrate evidence. The UOM DocType question in D026 is still open and decides part of P02c.
