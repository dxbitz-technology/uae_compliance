# Source map

Where every value in the canonical invoice comes from. Spec 5.2 asks for one
matrix and this is it. Each row names the canonical path, the ERPNext field
behind it, when it applies and what happens to it on the way, the official
term or rule it answers, and the packet that filled it in.

Amounts carry the invoice's own currency and the precision the money rules
set for that currency. Where a row says nothing about precision, that is what
it uses. Rows still to be filled say so rather than being left out, so the
gaps are visible.

Two rules run through the whole table. ERPNext owns the numbers and this app
only reads them, so nothing here recalculates a posted amount. And what the
invoice itself selected beats what a master says today, because the document
has to keep meaning what it meant when it was issued.

## Provenance and context

| Canonical path | Source | Condition and transformation | Official term | Packet |
| --- | --- | --- | --- | --- |
| `provenance.source_name` | Sales Invoice `name` | Always | | P03a |
| `provenance.company` | `company` | Always | | P03a |
| `provenance.source_fingerprint` | The watched field list in `fingerprint.py` | Covers the fields a check depends on, including unsaved edits, because `modified` has not moved during a preview | | P03a |
| `provenance.master_fingerprint` | The `modified` time of every master read | Sorted, so the same set gives the same string | | P03a |
| `context.in_scope` | Seller binding mode | Missing configuration means Off | | P03a |
| `context.customization_id`, `profile_id` | Pinned release | Never from a site field | ibr-cl-01 context | P01 |

## Document

| Canonical path | Source | Condition and transformation | Official term | Packet |
| --- | --- | --- | --- | --- |
| `document.number` | Sales Invoice `name` | Always | BT-1 | P03b |
| `document.uuid` | Generated once and frozen | Stays with the document wherever it travels. Not the ERPNext name | BT-1 context | P03b |
| `document.type_code` | Tax categories on the document, seller registration, scenario flags | Never from `is_return` alone. The matrix in `scope.py` decides | ibr-122-ae, ibr-134-ae, ibr-151-ae, ibr-157-ae | P03c |
| `document.issue_date` | `posting_date` | Posting, tax point and legal issue are three meanings and stay apart | BT-2 | P03b |
| `document.due_date` | `due_date` | Not applicable when the invoice is already settled | BT-9 | P03b |
| `document.period` | `from_date`, `to_date` | Only when the summary scenario is on | BT-73, BT-74 | P03b |
| `document.currency` | `currency` | The transaction currency. `base_*` is the company's, which is not automatically AED | BT-5 | P03b |
| `document.purchase_order` | `po_no` | When filled | BT-13 | P03b |

## Parties

| Canonical path | Source | Condition and transformation | Official term | Packet |
| --- | --- | --- | --- | --- |
| `parties.seller.legal_name` | Company `company_name` | Always | BT-27 | P03a |
| `parties.seller.participant` | Seller profile `participant_scheme`, `participant_value` | A seller with no network identity is a finding, not a blank | BT-34 | P03a |
| `parties.seller.tax_registration` | Company `tax_id`, else seller profile `vat_number` | The native field wins where it is filled. A seller marked registered with no number is a finding | BT-31 | P03a |
| `parties.seller.legal_registration` | Seller profile `legal_scheme`, `legal_value`, `legal_authority` | The authority is carried because a trade licence needs to say who issued it | BT-30 | P03a |
| `parties.seller.address` | Invoice `company_address`, else the seller binding's default | The invoice's own choice wins | BG-5 | P03a |
| `parties.buyer.legal_name` | Customer `customer_name` | Always | BT-44 | P03a |
| `parties.buyer.participant` | Party profile `endpoint_scheme`, `endpoint_value` | Never forced to the UAE scheme. A missing endpoint is a finding | BT-49 | P03a |
| `parties.buyer.country` | Party profile `establishment_country`, else the billing address country | Established in and posted to are separate facts and neither overwrites the other | BT-55 | P03a |
| `parties.buyer.tax_registration` | Customer `tax_id`, else party profile `vat_number` | | BT-48 | P03a |
| `parties.buyer.extra_tax_registration` | Party profile `extra_vat_number` | A foreign party may hold a UAE registration as well as its own. Both are kept | D016 | P03a |
| `parties.buyer.address` | Invoice `customer_address` | No fallback to whichever address is primary today | BG-8 | P03a |
| `delivery.address` | Invoice `shipping_address_name` | When filled. Dispatch and shipping are different and this is where the customer received it | BG-15 | P03a |

## Lines

| Canonical path | Source | Condition and transformation | Official term | Packet |
| --- | --- | --- | --- | --- |
| `lines.source_row` | Item row `name` | Stable, so a finding can point back at the row | | P03b |
| `lines.quantity` | Item row `qty` | The invoiced quantity, not the stock quantity | BT-129 | P03b |
| `lines.uom_code` | UOM `common_code` for the row's `uom` | The invoiced unit. A unit with no code is reported, never guessed | BT-130 | P03a |
| `lines.item_type` | Item `uae_peppol_item_type`, else the item group's | Never read from `is_stock_item` | D042 | P03a |
| `lines.classifications` | Item `customs_tariff_number` | Goods are classified by tariff heading, services by activity code | BT-158 | P03a |
| `lines.net_price` | Item row `net_rate` | Already has the row discount taken off | BT-146 | P03b |
| `payment.means_code` | Mode of Payment `type` on the payments table | Cash is 10, bank is 42. Nothing recorded sends 1, the published value for an instrument not stated, with a warning | ibr-191-ae | P03b |
| `parties.*.address.subdivision` | Address `emirate`, else `state` | Required by ibr-143-ae and ibr-144-ae. On a UAE site the emirate is its own field, put there by ERPNext | ibr-143-ae | P03a |
| `lines.price_discount` | Item row `discount_amount` | Carried for the record. Must not be taken off a second time as an allowance | BT-147 | P03b |
| `lines.net_amount` | Item row `net_amount` | The posted figure, never recalculated | BT-131 | P03b |
| `lines.tax_category`, `tax_rate` | The tax mapping for the company and the row's tax template or account | Template first, account second. Two matches is refused, not resolved | BT-151, BT-152 | P03a |

## Taxes, adjustments and totals

| Canonical path | Source | Condition and transformation | Official term | Packet |
| --- | --- | --- | --- | --- |
| `tax_breakdown` | The `Item Wise Tax Detail` table, grouped through the lines | Per invoice row, not per item code. Version 16 replaced the old map, so the warning in spec 5.2 no longer applies here | BG-23 | P03b |
| `allowances` | Nothing | ERPNext has already taken the document discount off every line, so stating it again would take it off twice. A cash discount on the grand total is the one shape this cannot carry and is reported | BG-20 | P03b |
| `charges` | Tax rows that are not VAT | `total_taxes_and_charges` is not necessarily VAT | BG-21 | P03b |
| `totals.tax_exclusive` | `net_total` | Checked against the line sum, never recalculated from it | BT-109 | P03b |
| `totals.prepaid` | `total_advance` | Frozen at issue. A payment made later never rewrites it. `outstanding_amount` is not used | BT-113 | P03b |
| `totals.rounding` | `rounding_adjustment` | Turns with the totals on a credit note, because ERPNext writes it as the rounded total less the grand total and both of those are negative | BT-114 | P03b |
| `totals.payable` | `rounded_total`, else `grand_total`, less `total_advance` | Follows `disable_rounded_total`. ERPNext keeps the grand total whole and records the advance beside it, so the advance comes off here or the invoice asks for it twice | BT-115, ibr-co-16 | P03b |
| `exchange_rates.to_company` | `conversion_rate` with `posting_date` | Frozen. A rate looked up later never changes an old invoice | | P03b |
| `exchange_rates.to_aed` | Still to be decided | Needed when neither the invoice nor the company is in dirhams. Missing provenance is a finding and no rate is invented | | P03b |

## References and scenario

| Canonical path | Source | Condition and transformation | Official term | Packet |
| --- | --- | --- | --- | --- |
| `references.preceding` | `return_against`, plus any explicit extra references | More than one is supported, because a credit note can answer several invoices | BG-3 | P03c |
| `references.credit_reason_code` | Explicit input on the working record | One of DL8.61.1.A to E or VD, and nothing else. Extraction reports it missing because ERPNext holds no such field | ibr-001-ae, ibr-055-ae | P04 |
| `scenario.*` | Explicit input on the working record | Named booleans. The eight character official string is built only at serialization | ibr-154-ae | P01 |

## Not yet decided

- Which registration a company in a VAT group shows on its invoices (D016).
- Where the dirham rate comes from when neither the invoice nor the company is in dirhams.
- The issue date policy, which decides what `document.issue_date` means when posting and issuing fall on different days.
