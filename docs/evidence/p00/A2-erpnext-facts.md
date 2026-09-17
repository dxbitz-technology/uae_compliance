# A2 ERPNext v16 facts

Date 17-09-2026. Pinned checkout `apps/erpnext` at tag v16.26.2, commit d1d3b241ae7bc21d18cf830a4bacd568e21a2a19. All paths below are repo-relative to the bench root. Every fact is labelled Verified, Proposed or Unresolved. Read-only inspection only.

---

## 1. Tax calculation

### 1.1 Entry point and sequence

**Verified.** The engine is the class `calculate_taxes_and_totals` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:32. Its `__init__` runs the calculation immediately on construction (apps/erpnext/erpnext/controllers/taxes_and_totals.py:41). There is no way to build the object without calculating.

**Verified.** `__init__` first loads two settings into `frappe.flags`: round-off applicable accounts (apps/erpnext/erpnext/controllers/taxes_and_totals.py:35) and `Accounts Settings.round_row_wise_tax` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:38). Both change the arithmetic. They are global flags, not arguments.

**Verified.** The inner sequence is `_calculate` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:80, in this fixed order:

| Step | Method | Line |
| --- | --- | --- |
| 1 | `validate_conversion_rate` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:81 |
| 2 | `calculate_item_values` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:82 |
| 3 | `validate_item_tax_template` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:83 |
| 4 | `update_item_tax_map` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:84 |
| 5 | `initialize_taxes` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:85 |
| 6 | `determine_exclusive_rate` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:86 |
| 7 | `calculate_net_total` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:87 |
| 8 | `calculate_taxes` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:88 |
| 9 | `adjust_grand_total_for_inclusive_tax` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:89 |
| 10 | `calculate_totals` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:90 |
| 11 | `calculate_total_net_weight` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:91 |

**Verified.** The outer method `calculate` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:48 wraps that sequence. It runs `_calculate` once (line 56), then `set_discount_amount` and `apply_discount_amount` (lines 58 to 60). `apply_discount_amount` calls `_calculate` a second time when a discount exists (apps/erpnext/erpnext/controllers/taxes_and_totals.py:912). A changed Item Tax Template can force a third full pass through recursion (apps/erpnext/erpnext/controllers/taxes_and_totals.py:62). A shipping rule triggers yet another `_calculate` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:418).

**Verified.** After the discount passes, `calculate` handles cash and non-trade discount by subtracting from grand total and zeroing rounding (apps/erpnext/erpnext/controllers/taxes_and_totals.py:66 to 70), then shipping charges (line 72), then advances for Sales Invoice and Purchase Invoice (lines 74 to 75), then the printed breakup HTML (lines 77 to 78).

**Consequence.** The document is calculated between two and four times per save. Any extraction that reads intermediate state is wrong. Read only after the controller returns.

### 1.2 Item-wise tax detail. The shape changed in v16

**Verified. Critical.** The field `item_wise_tax_detail` does not exist on Sales Taxes and Charges in v16.26.2. A full field dump of apps/erpnext/erpnext/accounts/doctype/sales_taxes_and_charges/sales_taxes_and_charges.json returns no such fieldname. The v15 JSON blob is gone.

**Verified.** It is replaced by a parent-level child table `item_wise_tax_details` on the transaction. On Sales Invoice the field is `{"fieldname": "item_wise_tax_details", "fieldtype": "Table", "hidden": 1, "no_copy": 1, "print_hide": 1, "options": "Item Wise Tax Detail"}` in apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.json. The same field exists on Sales Order (apps/erpnext/erpnext/selling/doctype/sales_order/sales_order.json:1668), Delivery Note (apps/erpnext/erpnext/stock/doctype/delivery_note/delivery_note.json:1415), Quotation (apps/erpnext/erpnext/selling/doctype/quotation/quotation.json:1103), Purchase Order, Purchase Receipt and Supplier Quotation.

**Verified.** The child DocType is apps/erpnext/erpnext/accounts/doctype/item_wise_tax_detail/item_wise_tax_detail.json. It has exactly five fields:

| fieldname | fieldtype | options |
| --- | --- | --- |
| item_row | Data | |
| tax_row | Data | |
| rate | Float | |
| amount | Currency | Company:company:default_currency |
| taxable_amount | Currency | Company:company:default_currency |

**Verified. Answers the key question.** The dictionary key is not `item_code`. Rows are keyed per source row pair. `set_item_wise_tax` appends one entry per item row per tax row with no deduplication (apps/erpnext/erpnext/controllers/taxes_and_totals.py:665 to 673). `process_item_wise_tax_details` then writes each entry with `"item_row": row.item.name` and `"tax_row": row.tax.name`, the child row names (apps/erpnext/erpnext/controllers/taxes_and_totals.py:1337 to 1338). The same `item_code` on two rows produces two separate stored records. Nothing is overwritten and nothing is summed at this layer.

**Verified.** Aggregation by `item_code` still happens, but only in the display helper `get_itemised_tax` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:1262. It builds `itemised_tax[item_code][tax.description]` and accumulates with `+=` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:1276 to 1289). That helper feeds the print breakup HTML and the UAE regional override. Repeated item codes collapse there.

**Verified.** Storage is not a normal child-table write. `process_item_wise_tax_details` runs from `AccountsController.on_update` (apps/erpnext/erpnext/controllers/accounts_controller.py:143 to 146) and inserts through `bulk_insert("Item Wise Tax Detail", docs)` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:1344). The guard flag `update_item_wise_tax_details` is set in `reset_item_wise_tax_details` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:284) and cleared after insert (apps/erpnext/erpnext/controllers/taxes_and_totals.py:1345). `on_update` does not run on update-after-submit, so the table is frozen after submission unless a full save happens.

**Verified.** During calculation the working list lives at `doc._item_wise_tax_details` as `frappe._dict` entries holding live object references to `item` and `tax` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:664 to 673). That attribute is in memory only. A fresh `frappe.get_doc` will have the persisted child table, not the underscore attribute.

**Verified.** Rows for tax rows with `dont_recompute_tax` are preserved across recalculation and not rebuilt (apps/erpnext/erpnext/controllers/taxes_and_totals.py:285 to 296). The recompute path skips them entirely at apps/erpnext/erpnext/controllers/taxes_and_totals.py:630.

**Verified.** A rounding fix-up writes the residual into the last stored row per tax row, at 5 decimal places, and throws if the gap exceeds 0.5 (or 1 for zero-precision currencies): apps/erpnext/erpnext/controllers/taxes_and_totals.py:516 to 566. So the stored breakup is forced to reconcile to `base_tax_amount_after_discount_amount`, not to a clean per-line product.

### 1.3 Currency of item-wise values

**Verified. Critical.** `amount` and `taxable_amount` are in company currency, not transaction currency. `set_item_wise_tax` multiplies the running transaction total by `self.doc.conversion_rate` and rounds to `base_tax_amount` / `base_net_amount` precision (apps/erpnext/erpnext/controllers/taxes_and_totals.py:642 to 659). The DocType confirms it with `options: "Company:company:default_currency"` on both fields.

**Verified.** The values are error-diffused deltas of a running cumulative base total, not independent per-row products. The comment at apps/erpnext/erpnext/controllers/taxes_and_totals.py:639 to 640 states the intent. Each stored `amount` is `new_base_tax_total - previous_base_tax_total`.

**Verified.** `get_itemised_tax` divides `taxable_amount` back by `conversion_rate` for display but leaves `tax_amount` in base currency (apps/erpnext/erpnext/controllers/taxes_and_totals.py:1287 to 1289). The two columns in that helper are therefore in different currencies.

**Consequence.** Reading `item_wise_tax_details` and treating the numbers as document-currency VAT is a double-conversion bug waiting to happen when company currency is not the invoice currency.

### 1.4 Discount handling

**Verified.** `set_discount_amount` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:814 converts `additional_discount_percentage` into `discount_amount` by applying the percentage to the field named by `apply_discount_on`, using `scrub` on that value (apps/erpnext/erpnext/controllers/taxes_and_totals.py:816 to 821). So "Net Total" reads `net_total` and "Grand Total" reads `grand_total`.

**Verified.** The Select options for `apply_discount_on` on Sales Invoice are blank, `Grand Total`, `Net Total`.

**Verified.** For a return with `return_against`, previously submitted return discounts are summed and added to the ceiling check (apps/erpnext/erpnext/controllers/taxes_and_totals.py:826 to 845).

**Verified.** `apply_discount_amount` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:859 distributes the discount across item rows in proportion to `net_amount` over `get_total_for_discount_amount()` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:879 to 882). It writes `item.net_amount`, `item.distributed_discount_amount` and `item.net_rate`, carries a rounding difference forward into the next row (apps/erpnext/erpnext/controllers/taxes_and_totals.py:886 to 903), sets `discount_amount_applied = True` and re-runs `_calculate` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:911 to 912).

**Verified.** `get_total_for_discount_amount` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:916 returns plain `net_total` when `apply_discount_on` is "Net Total" or when there are no tax rows (apps/erpnext/erpnext/controllers/taxes_and_totals.py:918 to 919). For "Grand Total" it returns grand total minus the sum of Actual and On Item Quantity charges and anything cascading off them (apps/erpnext/erpnext/controllers/taxes_and_totals.py:921 to 957). Percentage taxes are therefore inside the discount base, fixed charges are not.

**Verified.** On the second pass `calculate_item_values` returns immediately because `discount_amount_applied` is set (apps/erpnext/erpnext/controllers/taxes_and_totals.py:227 to 228). Item `amount` keeps its pre-discount value while `net_amount` is post-discount. `total` stays pre-discount, `net_total` becomes post-discount.

**Verified.** With "Grand Total" the second pass does not re-accumulate `tax.tax_amount` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:455 to 459) and `initialize_taxes` does not reset it (apps/erpnext/erpnext/controllers/taxes_and_totals.py:272 to 275). Only `tax_amount_after_discount_amount` is rebuilt. Those two fields diverge, and `tax_amount` is the pre-discount figure.

**Verified.** A residual is captured as `grand_total_diff` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:498 to 501 and added into `grand_total` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:736.

**Verified.** Cash or non-trade discount on Grand Total bypasses distribution entirely: `apply_discount_amount` returns early (apps/erpnext/erpnext/controllers/taxes_and_totals.py:869 to 871) and `calculate` subtracts the amount straight off grand total afterwards (apps/erpnext/erpnext/controllers/taxes_and_totals.py:66 to 70). Item net amounts are untouched, so the totals identity does not hold in that case.

### 1.5 Inclusive tax back-out

**Verified.** `determine_exclusive_rate` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:305 returns immediately if no tax row has `included_in_print_rate` (line 306).

**Verified.** For each item it accumulates `cumulated_tax_fraction` across all tax rows and a separate per-quantity amount, then derives net as `(item.amount - total_inclusive_tax_amount_per_qty) / (1 + cumulated_tax_fraction)` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:336 to 340). It keeps the unrounded figure on `item._unrounded_net_amount` and writes the rounded one to `net_amount`, then `net_rate = net_amount / qty`.

**Verified.** `get_current_tax_fraction` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:350 returns the fraction per charge type: `rate/100` for On Net Total (lines 364 to 365); `rate/100 * previous row tax_fraction_for_current_item` for On Previous Row Amount (lines 367 to 370); `rate/100 * previous row grand_total_fraction_for_current_item` for On Previous Row Total (lines 372 to 375); a flat per-quantity amount for On Item Quantity (lines 377 to 378). A `Deduct` row flips both signs (apps/erpnext/erpnext/controllers/taxes_and_totals.py:380 to 382). A rate of `N/A` contributes nothing (apps/erpnext/erpnext/controllers/taxes_and_totals.py:361 to 362).

**Verified.** The later tax pass reuses the unrounded net for inclusive On Net Total rows, to avoid rounding twice (apps/erpnext/erpnext/controllers/taxes_and_totals.py:611 to 617). That path is skipped once `discount_amount_applied` is set, so a discounted inclusive invoice takes the rounded branch.

**Verified.** `adjust_grand_total_for_inclusive_tax` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:702 computes the residual between `total` plus non-inclusive taxes and the last tax row's cumulative total, and only accepts it when it is within half the last unit of tax precision (apps/erpnext/erpnext/controllers/taxes_and_totals.py:722 to 726). Otherwise it is discarded.

### 1.6 Charge type cascade

**Verified.** In `get_current_tax_and_net_amount` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:593:

| charge_type | Base used | Line |
| --- | --- | --- |
| Actual | `item.net_amount * tax.tax_amount / doc.net_total`, prorated per item | apps/erpnext/erpnext/controllers/taxes_and_totals.py:601 to 605 |
| On Net Total | `tax_rate/100 * item.net_amount` (unrounded net when inclusive) | apps/erpnext/erpnext/controllers/taxes_and_totals.py:607 to 619 |
| On Previous Row Amount | `tax_rate/100 * taxes[row_id-1].tax_amount_for_current_item` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:620 to 622 |
| On Previous Row Total | `tax_rate/100 * taxes[row_id-1].grand_total_for_current_item` | apps/erpnext/erpnext/controllers/taxes_and_totals.py:623 to 625 |
| On Item Quantity | `tax_rate * item.qty`, no net amount | apps/erpnext/erpnext/controllers/taxes_and_totals.py:626 to 628 |

**Verified.** `On Item Quantity` exists and is one of the five Select options on Sales Taxes and Charges. Its `taxable_amount` in the item-wise table is forced to 0.0 (apps/erpnext/erpnext/controllers/taxes_and_totals.py:661 to 662).

**Verified.** Both cascade types index the tax list by `cint(tax.row_id) - 1`, a positional index into the in-memory list, not a link. `row_id` is a Data field.

**Verified.** `tax_amount_for_current_item` and `grand_total_for_current_item` are rebuilt for every item inside the loop (apps/erpnext/erpnext/controllers/taxes_and_totals.py:462 to 479). They are per-item scratch values, not row totals.

**Verified.** Actual charges use a divisional-loss correction: the running remainder is pushed onto the last item row (apps/erpnext/erpnext/controllers/taxes_and_totals.py:449 to 453).

**Verified.** `set_cumulative_total` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:584 builds `tax.total` as net total plus the running tax, using `tax_amount_after_discount_amount`, with Valuation rows contributing zero and purchase-side Deduct rows negated (apps/erpnext/erpnext/controllers/taxes_and_totals.py:570 to 582).

### 1.7 Rounded total and rounding adjustment

**Verified.** `set_rounded_total` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:793. It returns early for a consolidated invoice that already has a rounding adjustment (lines 794 to 795), and only acts if the DocType has a `rounded_total` field (line 797).

**Verified.** When rounding is disabled both `rounded_total` and `rounding_adjustment` are set to 0 (apps/erpnext/erpnext/controllers/taxes_and_totals.py:798 to 800). Otherwise `rounded_total = round_based_on_smallest_currency_fraction(grand_total, currency, precision)` and `rounding_adjustment = rounded_total - grand_total` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:803 to 810). Base values follow via `_set_in_company_currency` (line 812).

**Verified.** `disable_rounded_total` is honoured in `AccountsController.is_rounded_total_disabled` at apps/erpnext/erpnext/controllers/accounts_controller.py:2813. It reads the document field when the DocType has one, otherwise the `Global Defaults` single value (apps/erpnext/erpnext/controllers/accounts_controller.py:2814 to 2817). Sales Invoice has the field, so the per-document checkbox wins.

**Verified.** `rounding_adjustment` on Sales Invoice is `read_only`, `no_copy`, `print_hide`, and shown only when rounding is not disabled.

**Verified.** Status logic also depends on the flag: `get_total_in_party_account_currency` picks `grand_total` when rounding is disabled and `rounded_total` otherwise (apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:2318 to 2323).

### 1.8 Row-level Item Tax Template override

**Verified.** `update_item_tax_map` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:144 rewrites `item.item_tax_rate` on every calculation by calling `get_item_tax_map`. It is derived data, recomputed each pass, never user input.

**Verified.** `get_item_tax_map` at apps/erpnext/erpnext/stock/get_item_details.py:850 builds a dict of `account_head` to rate. It seeds from the document tax rows that were not added by an item tax template (apps/erpnext/erpnext/stock/get_item_details.py:853 to 854), then overlays the template rows whose account belongs to the same Company (apps/erpnext/erpnext/stock/get_item_details.py:856 to 863). A template row flagged `not_applicable` maps the account to the sentinel `"N/A"` (apps/erpnext/erpnext/stock/get_item_details.py:861, sentinel defined at apps/erpnext/erpnext/stock/get_item_details.py:44).

**Verified.** `_get_tax_rate` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:386 resolves per row: if the tax row's `account_head` is a key in the item map, the map's rate wins, rounded to the tax row's `rate` precision; otherwise `tax.rate` applies. `"N/A"` short-circuits to zero tax and zero taxable amount (apps/erpnext/erpnext/controllers/taxes_and_totals.py:598 to 599).

**Verified.** `item_tax_rate` is a `Small Text` read-only field on Sales Invoice Item holding that JSON dict. It is parsed by `_load_item_tax_rate` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:347).

**Verified.** When `Accounts Settings.add_taxes_from_item_tax_template` is on, ERPNext appends missing accounts to the document tax table as `On Net Total` rows with rate 0 and `set_by_item_tax_template = 1` (apps/erpnext/erpnext/controllers/accounts_controller.py:1249 to 1276). Those rows look like zero-rate rows on the parent but carry real per-item rates through the item map.

### 1.9 Arithmetic type

**Verified. Plainly.** The arithmetic is Python `float` with `flt(value, precision)`. There is no `Decimal` anywhere in the calculation path. `flt` is imported at apps/erpnext/erpnext/controllers/taxes_and_totals.py:11 and defined at apps/frappe/frappe/utils/data.py:1120. Its body does `num = float(s)` then `rounded(num, precision, rounding_method)` (apps/frappe/frappe/utils/data.py:1151 to 1153).

**Verified.** The rounding method is a runtime System Settings choice with three variants: `Banker's Rounding`, `Banker's Rounding (legacy)` (the default) and `Commercial Rounding` (apps/frappe/frappe/utils/data.py:1239 to 1257). Two sites with the same data and different settings produce different tax figures.

**Consequence.** The app cannot assume ERPNext totals are exact decimal arithmetic. It must reconcile its own decimal results against float figures and record the difference.

---

## 2. Sales Invoice lifecycle

**Verified.** `SalesInvoice.validate` is at apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:305. Its first act is `validate_auto_set_posting_time()` (line 306), then `super().validate()` (line 307), which reaches `SellingController.validate` at apps/erpnext/erpnext/controllers/selling_controller.py:59 and through it `AccountsController.validate` at apps/erpnext/erpnext/controllers/accounts_controller.py:219.

**Verified.** `calculate_taxes_and_totals` is called from `AccountsController.validate` at apps/erpnext/erpnext/controllers/accounts_controller.py:265, guarded by the presence of a `currency` field (line 264). The wrapper is `AccountsController.calculate_taxes_and_totals` at apps/erpnext/erpnext/controllers/accounts_controller.py:736.

**Verified.** Ordering inside `AccountsController.validate` that matters to extraction: `set_missing_values(for_validate=True)` at line 231 (skipped when the action is update-after-submit, line 230), `set_taxes_and_charges()` at line 262, calculation at line 265, regional hooks at lines 302 to 304, pricing rules at line 307, `validate_party_address_and_contact()` at line 312. Everything after line 265 sees calculated totals.

**Verified.** The two regional seams run inside a company flag context: `validate_regional(doc)` and `validate_einvoice_fields(doc)` (apps/erpnext/erpnext/controllers/accounts_controller.py:302 to 304). Both are `@erpnext.allow_regional` no-ops by default (apps/erpnext/erpnext/controllers/accounts_controller.py:4326 and 4331). Neither is overridden for the United Arab Emirates.

**Verified.** Other lifecycle methods:

| Method | Location | What it does |
| --- | --- | --- |
| `before_save` | apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:462 | sets paid amount and mode-of-payment accounts |
| `before_submit` | apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:466 | adds remarks only |
| `on_submit` | apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:469 | authority check, previous-document status, stock ledger, asset handling, `make_gl_entries()` at line 510, credit limit, loyalty, inter-company link |
| `before_cancel` | apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:598 | POS and consolidation guards, then `super().before_cancel()` which calls `validate_einvoice_fields` (apps/erpnext/erpnext/controllers/accounts_controller.py:375 to 376) |
| `on_cancel` | apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:606 | payment-entry link check, previous-document status, stock ledger, `make_gl_entries_on_cancel()`, `db_set("status", "Cancelled")` |
| `on_update_after_submit` | apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:881 | compares a fixed field list and reposts accounting entries when accounts changed |
| `on_update` (inherited) | apps/erpnext/erpnext/controllers/accounts_controller.py:143 | writes the item-wise tax detail rows |

**Verified.** `on_update_after_submit` watches only account-type fields: the parent list at apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:883 to 891 and child fields `income_account`, `expense_account`, `discount_account` on items and `account_head` on taxes (apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:892 to 895). Nothing else triggers a repost.

**Verified. Important for hook design.** `validate` does not run on update-after-submit. Frappe dispatches only `before_update_after_submit` for that action (apps/frappe/frappe/model/document.py:1361 to 1362). `validate` runs only for save and submit (apps/frappe/frappe/model/document.py:1353 to 1358).

### 2.1 allow_on_submit fields

**Verified.** Sales Invoice, 21 fields: `project`, `cost_center`, `po_no`, `po_date`, `loyalty_redemption_account`, `cash_bank_account`, `account_for_change_amount`, `write_off_account`, `letter_head`, `group_same_items`, `select_print_heading`, `sales_team`, `from_date`, `to_date`, `auto_repeat`, `update_auto_repeat_reference`, `unrealized_profit_loss_account`, `additional_discount_account`, `dispatch_address_name`, `dispatch_address`, `title`.

**Verified.** Sales Invoice Item, 10 fields: `income_account`, `expense_account`, `cost_center`, `service_stop_date`, `actual_batch_qty`, `actual_qty`, `page_break`, `project`, `discount_account`, `company_total_stock`.

**Verified.** Sales Taxes and Charges also allows `account_head` and `cost_center` after submit.

**Consequence.** `po_no`, `po_date`, `dispatch_address_name` and `letter_head` are all editable after submit and all feed the canonical document. Freeze policy must cover them.

### 2.2 Outstanding amount and status after payment

**Verified.** The path is `update_outstanding_amt` at apps/erpnext/erpnext/accounts/doctype/gl_entry/gl_entry.py:348. It sums GL entries for the voucher, then writes directly: `frappe.db.set_value(against_voucher_type, against_voucher, "outstanding_amount", bal)` at apps/erpnext/erpnext/accounts/doctype/gl_entry/gl_entry.py:414, followed by `ref_doc.set_status(update=True)` at apps/erpnext/erpnext/accounts/doctype/gl_entry/gl_entry.py:416.

**Verified.** `SalesInvoice.set_status` at apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:2265 ends with `self.db_set("status", self.status, update_modified=update_modified)` (apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.py:2309).

**Verified.** Both writes bypass the document save cycle. No `validate`, no `on_update`, no recalculation. The caller is the GL Entry on-submit path at apps/erpnext/erpnext/accounts/doctype/gl_entry/gl_entry.py:117 to 130, gated on `flags.update_outstanding == "Yes"`.

**Consequence.** A later payment changes `outstanding_amount` and `status` with no document event the app can hook. Any frozen payable figure must be captured at submission and never recomputed from `outstanding_amount`.

---

## 3. Field inventory

All entries below are **Verified** from the DocType JSON in the pinned checkout.

### 3.1 Sales Invoice

Source apps/erpnext/erpnext/accounts/doctype/sales_invoice/sales_invoice.json.

| fieldname | fieldtype | notes |
| --- | --- | --- |
| currency | Link (Currency) | reqd |
| conversion_rate | Float | reqd |
| price_list_currency | Link (Currency) | read_only, reqd |
| plc_conversion_rate | Float | reqd |
| is_return | Check | |
| return_against | Link (Sales Invoice) | single link only |
| tax_id | Data | read_only, fetch_from customer.tax_id |
| customer_address | Link (Address) | |
| address_display | Text Editor | read_only |
| shipping_address_name | Link (Address) | |
| dispatch_address_name | Link (Address) | allow_on_submit |
| company_address | Link (Address) | |
| company_tax_id | Data | read_only, fetch_from company.tax_id |
| posting_date | Date | reqd |
| set_posting_time | Check | |
| due_date | Date | |
| po_no | Data | allow_on_submit |
| po_date | Date | allow_on_submit |
| taxes_and_charges | Link (Sales Taxes and Charges Template) | |
| taxes | Table (Sales Taxes and Charges) | |
| discount_amount | Currency (currency) | |
| additional_discount_percentage | Float | |
| apply_discount_on | Select: blank / Grand Total / Net Total | |
| total | Currency (currency) | read_only |
| net_total | Currency (currency) | read_only |
| base_total | Currency (company default) | read_only |
| base_net_total | Currency (company default) | read_only, reqd |
| total_taxes_and_charges | Currency (currency) | read_only |
| base_total_taxes_and_charges | Currency (company default) | read_only |
| grand_total | Currency (currency) | read_only, reqd |
| base_grand_total | Currency (company default) | read_only, reqd |
| rounded_total | Currency (currency) | read_only |
| rounding_adjustment | Currency (currency) | read_only, no_copy |
| outstanding_amount | Currency (party_account_currency) | read_only |
| paid_amount | Currency (currency) | read_only |
| advances | Table (Sales Invoice Advance) | |
| total_advance | Currency (party_account_currency) | read_only |
| write_off_amount | Currency (currency) | |
| is_debit_note | Check | |
| incoterm | Link (Incoterm) | |
| named_place | Data | |
| tax_category | Link (Tax Category) | |
| payment_terms_template | Link (Payment Terms Template) | |
| payment_schedule | Table (Payment Schedule) | |
| letter_head | Link (Letter Head) | allow_on_submit |

Two fields not on the request list but load-bearing: `item_wise_tax_details` (Table, Item Wise Tax Detail, hidden, no_copy) and `disable_rounded_total` (Check). None of the requested Sales Invoice fields is absent.

Note the currency options. `outstanding_amount` and `total_advance` are in `party_account_currency`, which is neither `currency` nor company currency by definition.

### 3.2 Sales Invoice Item

Source apps/erpnext/erpnext/accounts/doctype/sales_invoice_item/sales_invoice_item.json. None absent.

| fieldname | fieldtype | notes |
| --- | --- | --- |
| item_code | Link (Item) | |
| item_name | Data | reqd |
| description | Text Editor | |
| item_group | Link (Item Group) | read_only |
| brand | Data | |
| qty | Float | |
| stock_qty | Float | read_only |
| uom | Link (UOM) | reqd |
| stock_uom | Link (UOM) | read_only |
| conversion_factor | Float | reqd |
| price_list_rate | Currency (currency) | read_only |
| discount_percentage | Percent | |
| discount_amount | Currency (currency) | |
| rate | Currency (currency) | reqd |
| amount | Currency (currency) | read_only, reqd |
| net_rate | Currency (currency) | read_only |
| net_amount | Currency (currency) | read_only |
| base_rate | Currency (company default) | read_only, reqd |
| base_amount | Currency (company default) | read_only, reqd |
| base_net_rate | Currency (company default) | read_only |
| base_net_amount | Currency (company default) | read_only |
| item_tax_template | Link (Item Tax Template) | |
| item_tax_rate | Small Text | read_only, JSON map |
| income_account | Link (Account) | allow_on_submit, reqd |
| delivery_note | Link (Delivery Note) | read_only |
| dn_detail | Data | read_only |
| sales_order | Link (Sales Order) | read_only |
| so_detail | Data | read_only |
| customer_item_code | Data | read_only |
| sales_invoice_item | Data | read_only |
| pricing_rules | Small Text | read_only |
| margin_type | Select: blank / Percentage / Amount | |
| rate_with_margin | Currency (currency) | read_only |
| is_free_item | Check | read_only |
| weight_per_unit | Float | read_only |
| total_weight | Float | read_only |
| delivered_qty | Float | read_only |

Also present and needed for discount extraction: `distributed_discount_amount` (Currency, currency, read_only).

### 3.3 Sales Taxes and Charges

Source apps/erpnext/erpnext/accounts/doctype/sales_taxes_and_charges/sales_taxes_and_charges.json.

| fieldname | fieldtype | notes |
| --- | --- | --- |
| charge_type | Select: blank / Actual / On Net Total / On Previous Row Amount / On Previous Row Total / On Item Quantity | reqd |
| row_id | Data | positional index into the tax list |
| account_head | Link (Account) | allow_on_submit, reqd |
| rate | Float | |
| tax_amount | Currency (currency) | pre-discount when apply_discount_on is Grand Total |
| base_tax_amount | Currency (company default) | read_only |
| total | Currency (currency) | read_only, cumulative |
| base_total | Currency (company default) | read_only |
| tax_amount_after_discount_amount | Currency (currency) | read_only, the authoritative tax figure |
| **item_wise_tax_detail** | **ABSENT** | removed in v16, see section 1.2 |
| included_in_print_rate | Check | |
| dont_recompute_tax | Check | read_only |
| account_currency | Link (Currency) | read_only, fetch_from account_head.account_currency |
| cost_center | Link (Cost Center) | allow_on_submit |

Also present: `net_amount`, `base_net_amount`, `set_by_item_tax_template`, `is_tax_withholding_account`, `included_in_paid_amount`, `project`.

---

## 4. Masters

All **Verified** from DocType JSON.

### 4.1 Customer

apps/erpnext/erpnext/selling/doctype/customer/customer.json.

| fieldname | fieldtype | options |
| --- | --- | --- |
| tax_id | Data | |
| customer_type | Select | Company / Individual / Partnership |
| customer_group | Link | Customer Group |
| tax_category | Link | Tax Category |
| customer_primary_address | Link | Address |
| customer_primary_contact | Link | Contact |
| language | Link | Language |

Also relevant: `email_id`, `mobile_no`, `first_name`, `last_name` are all `Read Only` and fetched from `customer_primary_contact`. `primary_address` is a read-only Text Editor. There are no `address_line1`, `city` or `country` fields on Customer.

### 4.2 Supplier

apps/erpnext/erpnext/buying/doctype/supplier/supplier.json. `tax_id` is Data. `supplier_type` is Select with Company / Individual / Partnership. `supplier_group`, `tax_category`, `supplier_primary_address`, `supplier_primary_contact` and `language` are all Links, mirroring Customer.

### 4.3 Company

apps/erpnext/erpnext/setup/doctype/company/company.json. `tax_id` Data, `country` Link to Country, `default_currency` Link to Currency, `abbr` Data. Note there is no guarantee `default_currency` is AED even when `country` is United Arab Emirates.

### 4.4 Address

apps/frappe/frappe/contacts/doctype/address/address.json.

| fieldname | fieldtype | options |
| --- | --- | --- |
| address_type | Select | Billing / Shipping / Office / Personal / Plant / Postal / Shop / Subsidiary / Warehouse / Current / Permanent |
| address_line1 | Data | |
| address_line2 | Data | |
| city | Data | |
| state | Data | free text, not a code list |
| country | Link | Country |
| pincode | Data | |
| is_primary_address | Check | |
| is_shipping_address | Check | |
| links | Table | Dynamic Link |

### 4.5 Contact

apps/frappe/frappe/contacts/doctype/contact/contact.json. `first_name` Data, `email_id` Data with Email options, `mobile_no` Data with Phone options, `links` Table of Dynamic Link. Also `last_name`, `phone`, `company_name`, `designation`, `is_primary_contact`.

### 4.6 Item

apps/erpnext/erpnext/stock/doctype/item/item.json. `item_code` Data, `item_name` Data, `item_group` Link to Item Group, `stock_uom` Link to UOM, `is_stock_item` Check, `customs_tariff_number` Link to Customs Tariff Number, `country_of_origin` Link to Country, `taxes` Table of `Item Tax`.

**Verified.** The `Item Tax` child (apps/erpnext/erpnext/stock/doctype/item_tax/item_tax.json) has `item_tax_template` (Link, Item Tax Template), `tax_category` (Link, Tax Category), `valid_from` (Date), `maximum_net_rate` (Float) and `minimum_net_rate` (Float). All three requested fields are present, plus the two rate-band fields.

### 4.7 Item Group

apps/erpnext/erpnext/setup/doctype/item_group/item_group.json. `taxes` is a Table of the same `Item Tax` child, so Item Group defaults carry the same tax_category and valid_from structure.

### 4.8 UOM

apps/erpnext/erpnext/setup/doctype/uom/uom.json. Full field list: `uom_name` (Data), `must_be_whole_number` (Check), `enabled` (Check), `symbol` (Data), `common_code` (Data), `description` (Small Text), a column break, `category` (Link).

**Verified. Useful.** A code field does exist. `common_code` is Data with length 3 and the description "According to CEFACT/ICG/2010/IC013 or CEFACT/ICG/2010/IC010". That is the UN/CEFACT Recommendation 20 common code. The app does not need its own UOM code field, but it must treat the value as unvalidated free text and it must handle it being blank.

### 4.9 Item Tax Template and Tax Category

apps/erpnext/erpnext/accounts/doctype/item_tax_template/item_tax_template.json has `title` (Data), `company` (Link to Company) and `taxes` (Table of Item Tax Template Detail). The detail child (apps/erpnext/erpnext/accounts/doctype/item_tax_template_detail/item_tax_template_detail.json) has `tax_type` (Link to Account), `tax_rate` (Float) and `not_applicable` (Check).

apps/erpnext/erpnext/accounts/doctype/tax_category/tax_category.json has only `title` (Data) and `disabled` (Check), autonamed from `title`. There is no country, treatment or category-code field. The app cannot read a tax treatment from Tax Category alone.

---

## 5. Party quick entry

**Verified.** The file exists at the cited path in this v16 checkout: apps/erpnext/erpnext/public/js/utils/contact_address_quick_entry.js, 117 lines. The specification's v15 path is still correct for v16.26.2.

**Verified.** One class is defined: `frappe.ui.form.ContactAddressQuickEntryForm`, extending `frappe.ui.form.QuickEntryForm` (apps/erpnext/erpnext/public/js/utils/contact_address_quick_entry.js:3 to 5).

**Verified.** Binding is by direct global assignment in two one-line files:
- apps/erpnext/erpnext/public/js/utils/customer_quick_entry.js:3 sets `frappe.ui.form.CustomerQuickEntryForm = frappe.ui.form.ContactAddressQuickEntryForm`.
- apps/erpnext/erpnext/public/js/utils/supplier_quick_entry.js:3 sets `frappe.ui.form.SupplierQuickEntryForm` to the same class object.

Both are plain assignments of the same reference, not subclasses. All three files are bundled at apps/erpnext/erpnext/public/js/erpnext.bundle.js:18 to 20.

**Consequence.** Reassigning `ContactAddressQuickEntryForm` replaces the form for both Customer and Supplier at once, and silently discards any other app's override. The app must subclass and reassign both named globals, after checking what is already there.

**Verified.** `get_variant_fields` at apps/erpnext/erpnext/public/js/utils/contact_address_quick_entry.js:37 adds, in order: a "Primary Contact Details" section; `map_to_first_name` and `map_to_last_name` (Data, shown only when the party type is Company); `email_address` (Data, Email); `mobile_number` (Data); a "Primary Address Details" section; `address_line1`, `address_line2`, `pincode`, `city`, `state`, `country_address` (Link to Country).

**Verified.** No field is unconditionally mandatory. Three are conditionally mandatory and mutually triggering: `address_line1` when city or country is filled (line 80), `city` when country or address line 1 is filled (line 99), `country_address` when city or address line 1 is filled (line 111). Entering any one of the three makes the other two required. All added fields are pushed into `this.mandatory` before rendering (apps/erpnext/erpnext/public/js/utils/contact_address_quick_entry.js:12).

**Verified.** There is no separate server method for address or contact creation from the dialog. `insert` at apps/erpnext/erpnext/public/js/utils/contact_address_quick_entry.js:16 renames the alias fields back to their real names (`email_address` to `email_id`, `mobile_number` to `mobile_no`, `map_to_first_name` to `first_name`, `map_to_last_name` to `last_name`, `country_address` to `country`) and then calls `super.insert()`. Aliases exist because the real Customer fields are read-only and therefore hidden (comment at lines 17 to 20, confirmed by the Customer JSON).

**Verified.** The extra keys travel on the Customer or Supplier document itself. `address_line1`, `city`, `state`, `pincode` and `country` are not Customer fields, so they arrive as transient attributes and are consumed server side.

**Verified.** Server side, `Customer.on_update` at apps/erpnext/erpnext/selling/doctype/customer/customer.py:261 calls `create_primary_contact()` (line 263) and `create_primary_address()` (line 264).
- `create_primary_contact` at apps/erpnext/erpnext/selling/doctype/customer/customer.py:286 builds a Contact through `make_contact(self)` only when there is no existing primary contact and no lead, and only if mobile, email, first name or last name is present. It then writes `customer_primary_contact`, `mobile_no` and `email_id` with `db_set`.
- `create_primary_address` at apps/erpnext/erpnext/selling/doctype/customer/customer.py:296 builds an Address through `make_address(self)` only when `flags.is_new_doc` is set and `address_line1` is present, then writes `customer_primary_address` and the rendered `primary_address` with `db_set`.

**Verified.** `make_contact` is at apps/erpnext/erpnext/selling/doctype/customer/customer.py:782. It links the Contact to the party through a Dynamic Link row, splits a full name for Individual parties and sets `company_name` otherwise, adds email and phone through `add_email` and `add_phone`, then inserts.

**Verified.** `make_address` is at apps/erpnext/erpnext/selling/doctype/customer/customer.py:827. It throws if `city` or `country` is missing (lines 828 to 836), sets `is_primary_address` and `is_shipping_address` to 1 by default, and links the Address to the party. `address_type` is not set, so the Address DocType default applies.

**Verified.** Supplier reuses the same helpers. `Supplier.on_update` at apps/erpnext/erpnext/buying/doctype/supplier/supplier.py:109 calls `create_primary_contact` (apps/erpnext/erpnext/buying/doctype/supplier/supplier.py:186, importing `make_contact` from the customer module) and `create_primary_address` (apps/erpnext/erpnext/buying/doctype/supplier/supplier.py:196, importing `make_address`). Supplier's contact branch checks only `mobile_no` or `email_id`, not names.

**Consequence.** Creation is already one server transaction driven by the party's own `on_update`. The app should add its profile write to that same transaction rather than issuing a second request after save.

---

## 6. Regional UAE code in v16

**Verified.** Everything UAE-specific sits in four places:
- apps/erpnext/erpnext/regional/united_arab_emirates/setup.py
- apps/erpnext/erpnext/regional/united_arab_emirates/utils.py
- apps/erpnext/erpnext/regional/doctype/uae_vat_settings and apps/erpnext/erpnext/regional/doctype/uae_vat_account
- apps/erpnext/erpnext/regional/report/uae_vat_201

### 6.1 Custom fields installed

**Verified.** `make_custom_fields` at apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:17 installs through `create_custom_fields(custom_fields, ignore_validate=True)` at apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:246. The map is at apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:185 to 244.

| DocType | Fields installed |
| --- | --- |
| Sales Invoice | `company_trn`, `customer_name_in_arabic`, `vat_emirate`, `tourist_tax_return`, `vat_section`, `permit_no` |
| POS Invoice | same six as Sales Invoice |
| Sales Order, Delivery Note | same six as Sales Invoice |
| Purchase Invoice, Purchase Order, Purchase Receipt | `company_trn`, `supplier_name_in_arabic`, `recoverable_standard_rated_expenses`, `reverse_charge`, `recoverable_reverse_charge`, `vat_section`, `permit_no` |
| Sales Invoice Item, POS Invoice Item | `tax_code`, `tax_rate`, `tax_amount`, `total_amount`, `delivery_date`, `is_zero_rated`, `is_exempt` |
| Purchase Invoice Item, Sales Order Item, Delivery Note Item, Quotation Item, Purchase Order Item, Purchase Receipt Item, Supplier Quotation Item | `tax_code`, `tax_rate`, `tax_amount`, `total_amount` |
| Item | `tax_code`, `is_zero_rated`, `is_exempt` |
| Customer | `customer_name_in_arabic` |
| Supplier | `supplier_name_in_arabic` |
| Address | `emirate` |

**Verified.** Field detail worth recording:
- `vat_emirate` is a Select on Sales Invoice with options blank, Abu Dhabi, Ajman, Dubai, Fujairah, Ras Al Khaimah, Sharjah, Umm Al Quwain, fetched from `company_address.emirate` (apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:116 to 123). It stores full emirate names, not codes.
- `tourist_tax_return` is a Currency field labelled in AED (apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:124 to 131).
- `permit_no` is a Data field inside a collapsible "VAT Details" section (apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:36 to 52).
- `reverse_charge` is a Select of Y and N, default N, and it is installed **only on purchase documents**, not on Sales Invoice (apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:79 to 87 and 228 to 234).
- `company_trn` is Read Only fetched from `company.tax_id` (apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:100 to 107).
- `Address.emirate` is a Select with the same seven emirate names (apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:219 to 227).

### 6.2 Installation triggers

**Verified.** Three triggers exist.

1. Company creation or country change. `Company.on_update` calls `install_country_fixtures(self.name, self.country)` at apps/erpnext/erpnext/setup/doctype/company/company.py:353, guarded by `frappe.flags.country_change` (line 352). `install_country_fixtures` at apps/erpnext/erpnext/setup/doctype/company/company.py:847 resolves the module name by string from the country name (`erpnext.regional.{scrub(country)}.setup.setup`, line 849) and calls it. A missing module is swallowed as ImportError (line 851). Any other failure is logged and thrown (lines 853 to 859).
2. Patches. apps/erpnext/erpnext/patches/v13_0/setup_uae_vat_fields.py runs the full `setup()` when at least one Company has country United Arab Emirates (lines 10 to 17). apps/erpnext/erpnext/patches/v13_0/create_uae_pos_invoice_fields.py and apps/erpnext/erpnext/patches/v15_0/update_uae_zero_rated_fetch.py call `make_custom_fields` directly.
3. Runtime overrides. `regional_overrides` in apps/erpnext/erpnext/hooks.py:605 maps, for United Arab Emirates, `erpnext.controllers.taxes_and_totals.update_itemised_tax_data` to the UAE version (apps/erpnext/erpnext/hooks.py:608) and `make_regional_gl_entries` for Purchase Invoice (apps/erpnext/erpnext/hooks.py:609). Saudi Arabia reuses the UAE `update_itemised_tax_data` (apps/erpnext/erpnext/hooks.py:612).

**Verified.** The setup wizard does not call UAE setup directly. It runs through Company creation, which sets the country flag. **Unresolved** whether every supported install route sets `frappe.flags.country_change`; confirming this needs a runtime trace on a real site, which section A3 covers.

**Verified.** `setup()` at apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:10 also enables three print formats by raw SQL (apps/erpnext/erpnext/regional/united_arab_emirates/setup.py:249 to 257), creates a Custom Role for UAE VAT 201 (lines 260 to 267) and grants permissions on UAE VAT Settings and UAE VAT Account (lines 270 to 277).

### 6.3 What the UAE override actually does

**Verified.** `update_itemised_tax_data` at apps/erpnext/erpnext/regional/united_arab_emirates/utils.py:9 writes `tax_rate`, `tax_amount`, `total_amount` and `is_zero_rated` back onto each item row. It derives export status purely by comparing Company country with the country of `customer_address` (apps/erpnext/erpnext/regional/united_arab_emirates/utils.py:32 to 37) and sets `is_zero_rated` when the rate is zero or the item is flagged (lines 52 to 53).

**Consequence.** This is exactly the blanket rule the specification rejects in section 6.2. A different country on the customer address makes ERPNext mark the line zero rated regardless of actual treatment. The app must not read `is_zero_rated` as evidence of tax treatment.

**Verified.** It sums rates across all templates on the item, acknowledging in a code comment that an Item Tax Template containing both input and output accounts would double the rate (apps/erpnext/erpnext/regional/united_arab_emirates/utils.py:44 to 50).

### 6.4 UAE VAT 201

**Verified.** The report exists. apps/erpnext/erpnext/regional/report/uae_vat_201/uae_vat_201.json declares report_name "UAE VAT 201", report_type "Script Report", ref_doctype "GL Entry", module "Regional", is_standard Yes, disabled 0. Implementation at apps/erpnext/erpnext/regional/report/uae_vat_201/uae_vat_201.py, with .js and .html siblings.

**Verified.** It resolves tax accounts from the `UAE VAT Account` child rows of `UAE VAT Settings` per company (apps/erpnext/erpnext/regional/united_arab_emirates/utils.py:77 to 80).

---

## 7. Exchange rates

**Verified.** `get_exchange_rate` is at apps/erpnext/erpnext/setup/utils.py:62. Signature `(from_currency, to_currency, transaction_date=None, args=None)`.

**Verified.** Order of resolution:
1. Returns nothing when either currency is missing (apps/erpnext/erpnext/setup/utils.py:63 to 65). Returns 1 when the currencies match (lines 66 to 67).
2. Defaults `transaction_date` to today when not supplied (apps/erpnext/erpnext/setup/utils.py:69 to 70). A caller that omits the date silently gets today's rate.
3. Reads `Accounts Settings.allow_stale` (apps/erpnext/erpnext/setup/utils.py:73).
4. Queries `Currency Exchange` for rows on or before the date, filtered by currency pair, and by `for_buying` or `for_selling` when `args` says so (apps/erpnext/erpnext/setup/utils.py:75 to 84). When `allow_stale` is off, `Accounts Settings.stale_days` bounds the lower edge (apps/erpnext/erpnext/setup/utils.py:86 to 89). It takes the single newest row by date (lines 92 to 96).
5. If nothing matches and `Currency Exchange Settings.disabled` is set, returns 0.00 (apps/erpnext/erpnext/setup/utils.py:98 to 99).
6. Optional pegged-currency resolution when `Accounts Settings.allow_pegged_currencies_exchange_rates` is on (apps/erpnext/erpnext/setup/utils.py:103 to 106).
7. **External network call.** It performs `requests.get` against the endpoint configured in `Currency Exchange Settings`, with a 6 hour cache in `frappe.cache` (apps/erpnext/erpnext/setup/utils.py:108 to 135). On any exception it logs an error, shows a message and returns 0.0 (apps/erpnext/erpnext/setup/utils.py:146 to 153).

**Consequence.** Calling `get_exchange_rate` during a validation preview can trigger outbound HTTP. The specification forbids network calls during preview. The app must read `Currency Exchange` records or the frozen invoice value directly, never call this helper.

**Verified.** `conversion_rate` is set on Sales Invoice in `AccountsController.set_price_list_currency` at apps/erpnext/erpnext/controllers/accounts_controller.py:956. Logic:
- `price_list_currency` is read from the Price List, and `plc_conversion_rate` is fetched when it differs from company currency (apps/erpnext/erpnext/controllers/accounts_controller.py:971 to 980).
- When `currency` is blank it inherits the price list currency and its rate (apps/erpnext/erpnext/controllers/accounts_controller.py:982 to 985).
- When `currency` equals company currency, `conversion_rate` is forced to 1.0 (apps/erpnext/erpnext/controllers/accounts_controller.py:986 to 987).
- Only when `conversion_rate` is empty is a rate fetched (apps/erpnext/erpnext/controllers/accounts_controller.py:988 to 991). An existing value is never overwritten on the sales side.
- `transaction_date` for the lookup is `posting_date` for Sales Invoice (apps/erpnext/erpnext/controllers/accounts_controller.py:957 to 960).
- The `use_transaction_date_exchange_rate` re-fetch applies only to Purchase Invoice (apps/erpnext/erpnext/controllers/accounts_controller.py:996 to 1001).

**Verified.** `validate_conversion_rate` inside the tax engine resets currency and rate to company currency and 1.0 when currency is blank or matches company currency (apps/erpnext/erpnext/controllers/taxes_and_totals.py:152 to 166). `check_conversion_rate` at apps/erpnext/erpnext/controllers/accounts_controller.py:2973 rejects a rate of 1.00 on a foreign-currency document and a non-1.00 rate on a company-currency document.

**Verified.** The stored `conversion_rate` converts invoice currency to **company** currency. There is no field anywhere on Sales Invoice that holds an invoice-to-AED rate when company currency is not AED. **Proposed.** The app must store its own AED reporting rate with provenance in the working record.

---

## 8. Hook order

**Verified.** `doc_events` begins at apps/erpnext/erpnext/hooks.py:344.

**Verified.** Handlers that apply to Sales Invoice, in the order the framework will encounter them:

| Event | Handler | Line |
| --- | --- | --- |
| validate (via `"*"`) | `erpnext.support.doctype.service_level_agreement.service_level_agreement.apply` | apps/erpnext/erpnext/hooks.py:347 |
| validate (via `"*"`) | `erpnext.setup.doctype.transaction_deletion_record.transaction_deletion_record.check_for_running_deletion_job` | apps/erpnext/erpnext/hooks.py:348 |
| validate (via `period_closing_doctypes`) | `erpnext.accounts.doctype.accounting_period.accounting_period.validate_accounting_period_on_doc_save` | apps/erpnext/erpnext/hooks.py:352 |
| on_submit | `erpnext.regional.italy.utils.sales_invoice_on_submit` | apps/erpnext/erpnext/hooks.py:381 |
| on_cancel | `erpnext.regional.italy.utils.sales_invoice_on_cancel` | apps/erpnext/erpnext/hooks.py:384 |
| on_trash | `erpnext.regional.check_deletion_permission` | apps/erpnext/erpnext/hooks.py:386 |

**Verified.** Sales Invoice is a member of `period_closing_doctypes` (apps/erpnext/erpnext/hooks.py:323 to 342, "Sales Invoice" at line 324), so the accounting-period check applies.

**Verified.** There is no `validate` entry under the Sales Invoice key. The only ERPNext validate handlers on Sales Invoice are the two wildcard ones plus the accounting-period one. The UAE handlers `update_grand_total_for_rcm` and `validate_returns` are registered for **Purchase Invoice only** (apps/erpnext/erpnext/hooks.py:388 to 393).

**Verified.** Beyond `doc_events`, the controller class chain runs first for each event. For validate that is `SalesInvoice.validate` to `SellingController.validate` to `AccountsController.validate`, the whole of section 2 above. For on_update it is `AccountsController.on_update`, which writes the item-wise tax detail rows (apps/erpnext/erpnext/controllers/accounts_controller.py:143 to 146).

**Verified.** The Italy on-submit and on-cancel handlers are registered unconditionally for every site. They early-return for non-Italian companies, but they are in the chain.

**Verified.** `Address.validate` also carries an Italy handler for every site (apps/erpnext/erpnext/hooks.py:398 to 402).

**Consequence.** The app's validate handler will run after ERPNext's calculation has completed, because the class method chain precedes `doc_events`. The app should not add a `validate` doc_event that assumes it runs before another app's.

---

## 9. Item tax resolution

**Verified.** Resolution is a two-level search. `get_item_tax_template` at apps/erpnext/erpnext/stock/get_item_details.py:711 tries the Item's own `taxes` rows first (lines 735 to 736), then walks up the Item Group tree (line 739). `_get_item_tax_template_from_item_group` at apps/erpnext/erpnext/stock/get_item_details.py:748 uses `get_ancestors_of` and checks the group itself before each ancestor, returning the first group whose rows produce a match.

**Verified.** `_get_item_tax_template` at apps/erpnext/erpnext/stock/get_item_details.py:761 does the real selection:
1. Skips any row whose template is disabled or belongs to a different Company (apps/erpnext/erpnext/stock/get_item_details.py:782 to 784). Company scoping is absolute.
2. Splits rows into those with `valid_from` or `maximum_net_rate` and those with neither (apps/erpnext/erpnext/stock/get_item_details.py:785 to 796).
3. The validity date is `bill_date`, else `posting_date`, else `transaction_date` (apps/erpnext/erpnext/stock/get_item_details.py:788 to 790). A row qualifies only when `valid_from <= validation_date` and the net rate falls inside any configured band (apps/erpnext/erpnext/stock/get_item_details.py:792). There is no valid-to date. Validity is open-ended forward.
4. **When more than one row matches**, dated rows win over undated rows entirely (apps/erpnext/erpnext/stock/get_item_details.py:798 to 801). Within the dated set, rows are sorted by `valid_from` descending, so the most recent applicable date wins.
5. An already-set template that is still in the candidate set is kept unchanged (apps/erpnext/erpnext/stock/get_item_details.py:815 to 818). Existing rows are not re-resolved.
6. Otherwise the first candidate whose `tax_category` string-equals the document's `tax_category` is returned (apps/erpnext/erpnext/stock/get_item_details.py:820 to 823). Comparison is `cstr` on both sides, so blank and None are equal. A document with no tax category matches rows with no tax category.
7. If no candidate matches the tax category, the function returns None. There is no fallback template.

**Verified.** `is_within_valid_range` at apps/erpnext/erpnext/stock/get_item_details.py:829 compares `base_net_rate`, the company-currency rate, against the band. Rate bands are evaluated in company currency, not document currency.

**Verified.** The engine's own guard, `validate_item_tax_template` at apps/erpnext/erpnext/controllers/taxes_and_totals.py:93, re-resolves each row that already has a template, combining Item rows and every Item Group ancestor's rows into one list (apps/erpnext/erpnext/controllers/taxes_and_totals.py:115 to 129). If the row's current template is not in the valid set, it **overwrites the user's choice** with `taxes[0]` and shows a message (apps/erpnext/erpnext/controllers/taxes_and_totals.py:132 to 139). The guard is skipped for a return with `return_against` (apps/erpnext/erpnext/controllers/taxes_and_totals.py:96 to 97) and when re-entered with the validation flag (lines 94 to 95).

**Verified.** There is no error on ambiguity. Multiple matching templates are resolved silently by sort order and first match. Nothing warns the user.

**Consequence.** The app must not re-derive the template. It must read the resolved `item_tax_template` and `item_tax_rate` from the calculated row, and it must reject its own mapping when more than one candidate would match, as section 5.2 requires.

---

## Consequences for the app

- **P02 and P03.** `item_wise_tax_detail` is gone. Build the source map against the `item_wise_tax_details` child table and the `Item Wise Tax Detail` DocType, and record the v15 field as removed.
- **P03.** `item_wise_tax_details.amount` and `taxable_amount` are company currency, produced by multiplying by `conversion_rate`. Never convert them again, and never read them as document-currency VAT.
- **P03.** The child rows are keyed by `item_row` and `tax_row`, so repeated item codes stay separate. Key the canonical line tax on those row names, never on `item_code`.
- **P03.** `item_wise_tax_details` values are error-diffused deltas forced to reconcile to `base_tax_amount_after_discount_amount`. Treat them as an allocation, not as a per-line VAT calculation, and recompute line VAT independently in decimal.
- **P03.** Use `tax_amount_after_discount_amount` as the authoritative tax figure. With `apply_discount_on = "Grand Total"`, `tax_amount` is the pre-discount value and will not match.
- **P03.** Item `amount` is pre-discount and `net_amount` is post-discount after a document discount. The document `total` stays pre-discount. Map the two separately.
- **P03.** Cash and non-trade discount on Grand Total is subtracted from grand total without touching line net amounts. The tax-exclusive plus tax identity does not hold there, so detect the case and treat it as a document allowance with an explicit rule.
- **P03.** ERPNext arithmetic is Python float with a site-configurable rounding method. Every reconciliation between decimal results and ERPNext figures must record the rounding method in the fixture.
- **P03.** No field holds an invoice-to-AED rate when company currency is not AED. Store the AED rate with its provenance in the working record.
- **P04.** `validate` does not run on update-after-submit, and `po_no`, `po_date`, `dispatch_address_name` and `letter_head` are all editable after submit. Guard those through `before_update_after_submit`, not `validate`.
- **P04.** Payments change `outstanding_amount` and `status` through direct database writes in `update_outstanding_amt`, with no document event. Freeze payable at submission and never rebuild it from `outstanding_amount`.
- **P04.** Quick entry for Customer and Supplier is one shared class assigned to two globals. Subclass it and reassign both, after preserving any existing override, and add the profile write inside the party's own `on_update` transaction rather than a second request.
