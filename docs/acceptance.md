# What the acceptance matrix actually covers

Spec 13 lists twenty six cases. This says which of them have tests behind
them, which do not, and why. It is written to be read against the spec, so
the ids and the order are its.

Written for the gate rather than for reassurance. A case with nothing
behind it says so.

## Covered

| Case | What it is | Where |
| --- | --- | --- |
| A01 | Source, spec and runtime pins | `docs/standards-lock.json`, `scripts/standards/check_lock.py` |
| A02 | Canonical determinism and validation | `domain/tests/test_encoding.py`, `test_canonical.py`, `validation/tests/test_validator.py`, the example runs in `scripts/check.sh` |
| A03 | Ordinary money | `domain/tests/test_money.py`, `test_extraction_money.py` |
| A04 | Tax complexity | `domain/tests/test_extraction_money.py`, `validation/tests/test_serializer_amounts.py`, `test_serializer_dirhams.py` |
| A05 | Credit notes | `domain/tests/test_extraction_money.py`, `test_scope.py` |
| A06 | Shared master identity | `doctype/uae_peppol_party_profile/test_uae_peppol_party_profile.py` |
| A07 | Quick entry transaction | `tests/test_services.py` |
| A08 | Draft, save and preview | `tests/test_acceptance.py` |
| A09 | Scope enforcement | `tests/test_acceptance.py` |
| A10 | Explicit master fix | `tests/test_services.py` |
| A11 | Atomic source and submission | `tests/test_services.py` |
| A12 | Approval and immutability | `tests/test_acceptance.py` |
| A13 | Concurrent sends | `tests/test_acceptance.py`, `domain/tests/test_recovery.py` |
| A14 | Ambiguous send | `connectors/tests/test_recovery.py` |
| A15 | Retry classes | `connectors/tests/test_adapters.py`, `test_recovery.py` |
| A17 | Independent outcomes | `connectors/tests/test_adapters.py`, `domain/tests/test_connector.py` |
| A18 | Correction and cancellation | `tests/test_acceptance.py` |
| A19 | Company access | `tests/test_access.py` |
| A20 | Secrets and hostile input | `validation/tests/test_safe_xml.py`, `connectors/tests/test_transport.py`, `doctype/uae_peppol_asp/test_uae_peppol_asp.py` |
| A21 | Migrations and coexistence | `tests/test_install.py` |
| A23 | Scenario completeness | `domain/tests/test_scenarios.py` |
| A24 | Resource behaviour | `tests/test_workload.py`, `docs/capacity.md` |
| A26 | Receiving | `tests/test_receiving.py` |

## Not covered, and why

| Case | What it is | Why not |
| --- | --- | --- |
| A16 | Event integrity | Nothing receives an event yet. The record exists and its shape holds the digest and the signature flag, but no provider sends one and the simulator's callbacks are not wired to a receiver. Belongs with P10. |
| A22 | Operational recovery | Mostly covered, in `tests/test_services.py`. Clone and restore safeguards, queue loss, evidence read back against its recorded checksums, and what a configuration backup carries. A real restore onto a second machine is not covered and cannot be: it needs a second site. |
| A25 | Real provider | No provider has been connected. Everything has run against the local simulator. This is P10 and it is the reason no production claim is made anywhere. |
| A26 | Self-billing | The receiving half is covered. Self-billing uses a separate official package this release does not carry, so there is nothing to validate against. |

## How the tests were checked

Passing is not the same as testing. Every suite written for this phase was
checked by breaking the code it covers and confirming a named test fails.

Twenty two deliberate breaks so far. Five were not caught first time, and
each one was a test that looked like it covered something and did not:

- The claim's state test, which the lease was already covering.
- The in flight cancellation guard, where a later guard refused the same
  case with a worse message.
- The company defence on an arriving document, which is doubled, so
  removing either layer alone still looked fine.
- The serializer reading the posted line tax, which the domain suite could
  not see.
- A crafted verified claim at party entry, which the profile controller
  stops rather than the field list.

All twenty two are caught now. The ones that were missed are listed because
the misses are the useful part.
