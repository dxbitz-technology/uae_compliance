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

## Next packet

P02a: the app module, roles, settings and provider connection records, with proof that credentials are stored encrypted. First write the packet record here, then the work. P02 is the first phase that installs anything on a site, so a clean install starting switched off is part of its evidence.
