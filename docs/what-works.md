# What this release does

Generated from the code by `scripts/capabilities.py`. A hand written
list of this kind drifts away from the software, so this one is read
out of it and checked on every build.

Rules: PINT AE Billing 1.0.4, `urn:peppol:pint:billing-1@ae-1`.

## Documents

| Code | Document |
| --- | --- |
| 380 | Tax invoice |
| 480 | Commercial invoice |
| 381 | Tax credit note |
| 81 | Commercial credit note |

The type is chosen from the tax categories on the document and whether
the seller is registered, not from whether the source is a return.

## Tax categories

S, E, O, AE, Z, N. Margin is the letter N.

## Kinds of supply

| Supply | Supported | What it needs |
| --- | --- | --- |
| Free zone | Yes | parties.beneficiary.participant |
| Deemed supply | Yes | payment.means_code |
| Margin scheme | No | Nothing beyond an ordinary invoice |
| Summary invoice | Yes | document.period |
| Continuous supply | Yes | Nothing beyond an ordinary invoice |
| Billed by an agent | Yes | parties.principal.participant, parties.seller.tax_registration |
| E-commerce | Yes | delivery.address |
| Export | Yes | delivery.address, parties.buyer.tax_registration |

Margin scheme is off because: Every line has to carry tax category N and the margin itself has to be worked out, which ibr-116-ae enforces. The accounting for it has not been settled.

## Not built

| Thing | Why not |
| --- | --- |
| Domestic reverse charge | The accounting has not been settled. |
| Advance invoices and retention | Needs the advance, payment, balance and release documents defined together. |
| Self billing | Uses a separate official package this release does not carry. |
| Receiving by callback | Documents are collected by asking. Nothing listens for a push yet. |

An unsupported case is refused in Live rather than approximated. There
is no switch that turns an unfinished one on.

## Company modes

| Mode | What happens |
| --- | --- |
| Off | Nothing. No record, no notice, no field. |
| Preparation | Collects and checks. Sends nothing. |
| Live | Blocks a submission that would fail, and queues what passes. |

A company nobody configured is Off.

## Buying

Documents suppliers send are collected by asking the provider, read,
matched to a supplier by tax number or network address, and kept. One
can then be entered as a draft purchase invoice, which a person
submits.

No supplier is created from an arriving document, no item is invented
to make a line fit, and nothing posts on its own.

## Sending

Against the local simulator only. No real provider has been connected
and no production certification is claimed.
