# A3: uae.local site inspection and bench coexistence survey

Phase P00 Baseline. Read-only. Date of inspection: 16-09-2026 (GST).
Spec sections in scope: 4.3 (native master customization budget), 7.3 (Customer, Supplier, Company entry), 11.4 (install, upgrade, release), with 1.2 and 1.4 as method.

Paths below are relative to /Users/aslam/frappe-local/loc16/apps unless absolute. F = frappe checkout at 567c05b6b7b736b52f08c372a620bd19cba168d1 (v16.22.0). E = erpnext checkout at d1d3b241ae7bc21d18cf830a4bacd568e21a2a19 (v16.26.2). Both HEADs confirmed with git rev-parse.

## 1. Installed apps and versions

Verified. frappe.get_installed_apps() on uae.local returns ['frappe', 'erpnext', 'uae_compliance']. Versions from each package __version__: frappe 16.22.0, erpnext 16.26.2, uae_compliance 0.0.1.

Verified. bench version lists 24 apps in the bench directory: bitz_dpr, bitz_finance, bitz_petty_cash, bitz_progress_billing, derma_zone, dxllm_core, dxsysui, erpnext, fpms, frappe, fta_compliance, hangcha, hrbitz, hrms, internal_pms, ksa_compliance, maildot, milestone_invoice, nawras, nextflow_core, synapse, tht, uae_compliance, v16ui_dx. Only three are installed on uae.local. uae_compliance is on branch main at 5f45c39 ("P00: repository baseline").

## 2. Company records

Verified. Company count: 1. Name: Dxbitz. country: United Arab Emirates. default_currency: AED. tax_id present: no. Record modified 2026-09-16 22:38:10, three seconds after the regional Custom Fields were created (22:38:07), so this is the setup-wizard company. It is not empty data in the strict sense; it is the wizard placeholder the task anticipated.

Consequence for 4.3 and 7.3: because a UAE company exists, ERPNext already ran its United Arab Emirates regional setup on this site (see section 3). Any uae_compliance test that assumes a bare site without regional fields will not match uae.local.

## 3. Custom Field and Property Setter rows on the eleven target DocTypes

Site totals: 98 Custom Field rows and 96 Property Setter rows. Every one of them has module NULL and owner Administrator (SQL group by module returned only NULL). No Custom Field has a fieldname starting with uae_ or containing peppol. No DocType belongs to module UAE e-Invoicing (count 0). uae_compliance has therefore written nothing to the site schema yet.

### 3.1 Custom Fields, with origin

All rows below except Customer.crm_deal are ERPNext regional fields. They come from E erpnext/regional/united_arab_emirates/setup.py: setup() at :10 calls make_custom_fields() at :17, which calls create_custom_fields(custom_fields, ignore_validate=True) at :246. The trigger is E erpnext/setup/doctype/company/company.py: Company.on_update at :336 sets frappe.flags.country_change (:344) and calls install_country_fixtures(self.name, self.country) at :352-353; install_country_fixtures at :847-850 resolves erpnext.regional.<scrub(country)>.setup.setup and calls it.

| DocType | fieldname | fieldtype | origin (E setup.py line) |
| --- | --- | --- | --- |
| Sales Invoice | company_trn | Read Only | :101 |
| Sales Invoice | customer_name_in_arabic | Read Only | :109 |
| Sales Invoice | vat_emirate | Select | :117 |
| Sales Invoice | tourist_tax_return | Currency | :125 |
| Sales Invoice | vat_section | Section Break | :38 |
| Sales Invoice | permit_no | Data | :46 |
| Sales Invoice Item | tax_code | Read Only | :136 |
| Sales Invoice Item | tax_rate | Float | :145 |
| Sales Invoice Item | tax_amount | Currency | :154 |
| Sales Invoice Item | total_amount | Currency | :164 |
| Sales Invoice Item | delivery_date | Date | :177 |
| Sales Invoice Item | is_zero_rated | Check | :19 |
| Sales Invoice Item | is_exempt | Check | :28 |
| Customer | customer_name_in_arabic | Data | :205 |
| Customer | crm_deal | Data | not regional; see below |
| Supplier | supplier_name_in_arabic | Data | :213 |
| Address | emirate | Select | :221 |
| Item | tax_code | Data | :187 |
| Item | is_zero_rated | Check | :189 |
| Item | is_exempt | Check | :196 |
| Contact | none | | |
| Company | none | | |
| Item Group | none | | |
| UOM | none | | |
| Sales Taxes and Charges | none | | |

Verified. Customer.crm_deal (created 2026-09-17 00:07:20) comes from E erpnext/crm/doctype/crm_settings/crm_settings.py: CRMSettings.on_update at :59 calls custom_fields_for_frappe_crm_data_sync at :64-88, which creates Quotation.crm_deal and Customer.crm_deal unconditionally on every CRM Settings save. On uae.local CRM Settings was modified 2026-09-17 00:07:20 with enable_frappe_crm_data_synchronization = 0. The field appears whenever CRM Settings is saved, regardless of that toggle. It is ERPNext core behaviour, not a Dxbitz customization.

### 3.2 Property Setters, with origin

All rows are ERPNext settings-driven and have module NULL. None is a Dxbitz customization.

| DocType | field_name | property | value | origin |
| --- | --- | --- | --- | --- |
| Sales Invoice | tax_id | hidden, print_hide | 0, 0 | E selling_settings.py:119-129 toggle_hide_tax_id |
| Sales Invoice | additional_discount_account | hidden, mandatory_depends_on | 1, blank | E selling_settings.py:143 toggle_discount_accounting_fields |
| Sales Invoice Item | discount_account | hidden, mandatory_depends_on | 1, blank | same |
| Sales Invoice | rounded_total, base_rounded_total | hidden, print_hide | 0, 0 / 0, 1 | E global_defaults.py:63 toggle_rounded_total (:77-106) |
| Sales Invoice | disable_rounded_total | default | 0 | same |
| Sales Invoice | in_words | hidden, print_hide | 0, 0 | E global_defaults.py:115 toggle_in_words (:129-137) |
| Sales Invoice | scan_barcode | hidden | 0 | E stock_settings.py:101-105 |
| Sales Invoice Item | barcode | hidden | 0 | same |
| Item | barcodes | hidden | 0 | same |
| Customer | naming_series | reqd 0, hidden 1 | | E erpnext/utilities/naming.py:9-42 set_by_naming_series, called from selling_settings.py:87 |
| Supplier | naming_series | reqd 0, hidden 1 | | same, called from buying_settings.py:58 |
| Item | naming_series | reqd 0, hidden 1 | | same, called from stock_settings.py:92 |
| Item | item_code | reqd 1, hidden 0 | | same |
| Address, Contact, Company, Item Group, UOM, Sales Taxes and Charges | none | | | |

Full E paths: erpnext/selling/doctype/selling_settings/selling_settings.py, erpnext/setup/doctype/global_defaults/global_defaults.py, erpnext/stock/doctype/stock_settings/stock_settings.py, erpnext/buying/doctype/buying_settings/buying_settings.py.

### 3.3 Reading for spec 4.3

Verified. The eleven target DocTypes carry no third-party customization on uae.local. What exists is ERPNext's own UAE regional layer plus settings-driven Property Setters.

Proposed. Because ERPNext regional fields have module NULL, uae_compliance must never export Custom Field or Property Setter fixtures without a module filter (module = UAE e-Invoicing) or it would capture and later overwrite these rows. This is the 4.3 rule "never overwrite another app's fields" applied to ERPNext itself.

Proposed. The regional fields customer_name_in_arabic, supplier_name_in_arabic, Address.emirate, Sales Invoice.vat_emirate and Item.is_zero_rated / is_exempt are candidates for the 4.3 "use existing fields" rule, but they exist only after a Company with country United Arab Emirates has been saved (company.py:352-353). Any reader must treat them as optional and check meta, not assume them.

## 4. Server Script and Client Script

Verified. Server Script count 0. Client Script count 0.

## 5. Module Def, Roles, Workspaces

Verified. Module Def with app_name uae_compliance: one row, name UAE e-Invoicing, module_name UAE e-Invoicing, custom 0. No other Module Def contains UAE.
Verified. Roles containing Peppol: none. Roles containing UAE: none.
Verified. Workspaces containing UAE: none.
Verified. frappe.get_module_list('uae_compliance') returns ['UAE e-Invoicing']. modules.txt holds the single line UAE e-Invoicing.

## 6. site_config.json

Verified. /Users/aslam/frappe-local/loc16/sites/uae.local/site_config.json exists. Key names: db_name, db_password, db_type, db_user, installed_apps. Values not recorded. encryption_key: absent. common_site_config.json also has no encryption_key (its keys: background_workers, default_site, developer_mode, file_watcher_port, frappe_user, gunicorn_workers, live_reload, rebase_on_pull, redis_cache, redis_queue, redis_socketio, restart_supervisor_on_update, restart_systemd_on_update, serve_default_site, shallow_clone, socketio_port, use_redis_auth, webserver_port).

Verified. Frappe creates the key on first use: F frappe/utils/password.py:223-231 get_encryption_key() checks "encryption_key" not in frappe.local.conf, generates Fernet.generate_key().decode(), writes it with update_site_config("encryption_key", ...) and returns it. It is called from encrypt() at :193 and decrypt() at :205, so the first Password-type field save on the site creates the key.

Consequence for 11.4: the app must not assume the key exists at install; any provider credential storage in later phases must go through frappe's Password fieldtype or get_decrypted_password so this path handles creation.

## 7. System Settings

Verified via frappe.db.get_single_value('System Settings', ...): time_zone Asia/Dubai; country United Arab Emirates; currency AED; float_precision '3'; currency_precision '' (blank); setup_complete 1. Global Defaults: country United Arab Emirates, default_currency AED.

Unresolved. currency_precision is blank, meaning frappe falls back to the currency's own precision rules. The exact fallback path was not read in this task. Owner: money-rules packet (spec 5.3). Consequence: rounding tests must not assume a System Settings value. Resolution: read F frappe/model/meta.py get_field_precision and frappe/utils/data.py flt handling, and cite.

## 8. Scheduler and workers

Verified. bench --site uae.local scheduler status prints "Scheduler is enabled for site uae.local"; System Settings enable_scheduler = 1.
Verified. Worker processes: pgrep -fl 'frappe worker' finds pid 26174 (python -m frappe.utils.bench_helper frappe worker), started by honcho (pid 26156) from the Procfile line "worker: OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES NO_PROXY=* bench worker". A schedule process (pid 26170, frappe schedule) and the web server (frappe serve --port 8002) also run. common_site_config background_workers = 1.
Verified. bench worker with no --queue consumes all queues: F frappe/commands/scheduler.py:186-190 (help text: "If not specified all queues are consumed.").
Note: the worker is bench-wide and serves every site in the bench, including uae.local.

## 9. Bench-wide coexistence survey (files only, no DB, no client data)

Scope: the 21 apps in /Users/aslam/frappe-local/loc16/apps other than frappe, erpnext and uae_compliance. node_modules and dist folders excluded.

### 9.1 Quick Entry overrides

Verified. No non-core app references CustomerQuickEntryForm, SupplierQuickEntryForm, ContactAddressQuickEntryForm or QuickEntryForm in any .js, .py, .json or .html file. uae_compliance would be the first app on this bench to touch the quick entry path.

Verified (spec 7.3 [S10] confirmation). ERPNext defines the shared form: E erpnext/public/js/utils/contact_address_quick_entry.js:3-4 declares frappe.ui.form.ContactAddressQuickEntryForm extending frappe.ui.form.QuickEntryForm; E erpnext/public/js/utils/customer_quick_entry.js:3 sets frappe.ui.form.CustomerQuickEntryForm = frappe.ui.form.ContactAddressQuickEntryForm; E erpnext/public/js/utils/supplier_quick_entry.js:3 does the same for Supplier. All three are bundled by E erpnext/public/js/erpnext.bundle.js:18-20. Frappe resolves the class by global name: F frappe/public/js/frappe/form/quick_entry.js:19-25 checks frappe.ui.form[trimmed_doctype + "QuickEntryForm"] and instantiates it. Reassigning that global replaces the class for every app; the 7.3 rule "do not unconditionally replace a global class" maps to this lookup.

Verified. Apps that add doctype_js on Customer (and would coexist with a quick entry extension): bitz_finance (hooks.py:46), dxsysui (:51), fta_compliance (:41), internal_pms (:73), ksa_compliance (:35), nextflow_core (:54), tht (:81). On Supplier: bitz_finance, fta_compliance. On Company: fta_compliance, hrbitz (:13), hrms (:49). None of these touch quick entry.

### 9.2 Custom fields targeting Sales Invoice, Customer, Supplier, Item

Fixture files (fixtures/custom_field.json), rows on target DocTypes only:

| App | File | Rows on targets |
| --- | --- | --- |
| bitz_finance | bitz_finance/bitz_finance/fixtures/custom_field.json | Customer 10 (custom_trade_license, custom_vat_certificate, custom_emirates, custom_country, custom_approved, others); Company 4 |
| dxsysui | dxsysui/dxsysui/fixtures/custom_field.json | Customer 2 (address/contact html sections) |
| hangcha | hangcha/hangcha/fixtures/custom_field.json | Sales Invoice 11 (shipment and secondary-currency fields); Sales Invoice Item 2; Customer 6 (custom_trn_certificate, custom_trade_licence_copy, others); Item 8; Company 3 |
| internal_pms | internal_pms/internal_pms/fixtures/custom_field.json | Customer 4; Sales Invoice 1 (sales_person) |
| milestone_invoice | milestone_invoice/milestone_invoice/fixtures/custom_field.json | Sales Invoice 5 (milestone billing); Sales Invoice Item 1 |
| nawras | nawras/nawras/fixtures/custom_field.json | Item 1 (custom_item_category) |
| tht | tht/tht/fixtures/custom_field.json | Customer 14 (custom_trn_form, custom_tax_type, custom_emirates, others); Item 12; Supplier 5 (custom_emirates, others); Item Group 1 |
| fpms | fpms/fpms/fixtures/custom_field.json | Company 3 only |
| hrbitz | hrbitz/hrbitz/fixtures/custom_field.json | Company 3 only |
| bitz_dpr, nextflow_core | fixtures present | no rows on target DocTypes |

Property Setter fixtures on target DocTypes: bitz_finance (Sales Invoice field_order, apply_discount_on.default), dxsysui (Customer: three hidden), hangcha (Sales Invoice: allow_auto_repeat, default_print_format, naming_series default and options), internal_pms (Customer account_manager.hidden), milestone_invoice (Sales Invoice field_order), nawras (Item field_order), tht (Customer and Supplier field_order; Sales Taxes and Charges five column properties).

Code paths that call create_custom_fields on target DocTypes:

| App | Path:line | Fields on targets |
| --- | --- | --- |
| fta_compliance | fta_compliance/fta_compliance/setup/install.py:321 (app fields) | Customer 6 (fta_vat_section, fta_customer_category, is_government, default_vat_treatment, two compliance html/cb); Supplier 5 (fta_vat_section, fta_supplier_category, rcm_applicable, two); Company 2; Sales Invoice 2 (fta_compliance_section, fta_voucher_compliance_html) |
| fta_compliance | install.py:87 ensure_regional_fields, :162-169 | re-creates ERPNext regional fields only when missing: Address.emirate, Item.is_zero_rated, Item.is_exempt, Sales Invoice.vat_emirate and tourist_tax_return, Purchase Invoice reverse_charge fields (constants at :32-45) |
| hangcha | hangcha/hangcha/setup/custom_fields.py:415 | same set as its fixtures: Customer 6, Sales Invoice 11, Sales Invoice Item 2, Company 3, Item 4 |
| bitz_progress_billing | bitz_progress_billing/bitz_progress_billing/setup.py:142 | Sales Invoice 3 (bitz_sales_order, bitz_billing_type, bitz_provisional_je) |
| fpms | fpms/fpms/api/progress_invoicing.py:18 | Sales Invoice 3 (custom_billing_type, custom_billing_sales_order, custom_progress_percentage) |
| tht | tht/tht/tht/api/mobile_setup.py:69 | Sales Invoice 2 (custom_transport_source_warehouse, custom_transport_destination_branch) |
| nextflow_core | nextflow_core/nextflow_core/install.py:315 | Customer 8 (nf_tier, nf_whatsapp_number, nf_health_*, nf_latitude, nf_longitude, nf_geofence_radius_m) |
| bitz_petty_cash | bitz_petty_cash/bitz_petty_cash/setup.py:18 | none on target DocTypes |
| hrms | hrms/hrms/setup.py:15, :40 | Company only |
| internal_pms | many patches | Company.custom_md only on targets |

Module customization exports (<app>/<app>/<module>/custom/<doctype>.json, sync_on_migrate = 1):

| App | File | Content on targets |
| --- | --- | --- |
| bitz_finance | bitz_finance/bitz_finance/bitz_finance/custom/customer.json | 4 custom fields including ERPNext regional customer_name_in_arabic (module null); Property Setters naming_series.hidden, naming_series.reqd, field_order |
| bitz_finance | .../custom/supplier.json | 4 custom fields including regional supplier_name_in_arabic (module null); same Property Setters |
| ksa_compliance | ksa_compliance/ksa_compliance/ksa_compliance/custom/sales_invoice_item.json | 5 custom fields including tax_amount, tax_rate, total_amount (module null): same fieldnames as ERPNext UAE regional fields on Sales Invoice Item |
| ksa_compliance | .../custom/sales_invoice.json, customer.json, address.json | custom_* fields (return reason, zatca discount reason, vat registration number, building number, area) |

### 9.3 Hooks on target DocTypes (doc_events)

Verified from each app's hooks.py (line of doc_events): Sales Invoice: bitz_progress_billing (:18; validate, on_submit, on_cancel), fpms (:156), fta_compliance (:16; validate, before_submit), hangcha (:189; validate, before_submit, on_submit, on_cancel), internal_pms (:186), ksa_compliance (:143; validate, on_submit, before_cancel), milestone_invoice (:153; before_insert, on_submit, on_cancel), tht (:214). Customer: fta_compliance (validate), hangcha (on_update), internal_pms (on_trash), nextflow_core (on_trash), tht (validate, on_trash). Supplier: fta_compliance (validate), tht (validate). Address: fta_compliance (validate). Company: hrms (:162).

No non-core app sets override_doctype_class on any target DocType.

### 9.4 How these customizations are applied on migrate (framework facts)

Verified. F frappe/migrate.py:171 calls sync_fixtures() and :180 calls sync_customizations() on every migrate.
Verified. Fixtures import overwrites by name: F frappe/utils/fixtures.py:12-13 ("Import, overwrite fixtures"), :41 import_doc(file_path, sort=True); F frappe/core/doctype/data_import/data_import.py:327-329 calls import_file_by_path(..., force=True, reset_permissions=True); F frappe/modules/import_file.py:229-238 deletes the existing document of the same name and inserts the file version.
Verified. Module customizations update in place: F frappe/modules/utils.py:167-177 finds an existing Custom Field by (dt, fieldname), calls update(d) and db_update(); :196-202 re-inserts Property Setters, relying on Property Setter.validate deleting the previous row (F frappe/custom/doctype/property_setter/property_setter.py:39-43).
Verified. create_custom_fields default update=True: F frappe/custom/doctype/custom_field/custom_field.py:316; existing fields matched at :351 and updated at :362-372 when the dict differs.

### 9.5 Fixture export filters

Verified. Every app that exports Custom Field or Property Setter fixtures filters them: by module (bitz_finance, dxsysui, fpms, hangcha, hrbitz, internal_pms, milestone_invoice, nawras, nextflow_core, tht) or by explicit name list (bitz_dpr, maildot). No app exports unfiltered Custom Field fixtures. uae_compliance hooks.py declares no fixtures yet.

### 9.6 Coexistence findings for spec 7.3 and 11.4

Verified. Fieldname collisions with uae_compliance planned names: none. No app other than uae_compliance uses uae_peppol, UAE e-Invoicing or UAE Peppol in any .py, .js, .json or .txt file.

Verified. Fieldname collisions between existing apps and ERPNext regional fields: bitz_finance module exports carry customer_name_in_arabic and supplier_name_in_arabic; ksa_compliance module export carries tax_amount, tax_rate, total_amount on Sales Invoice Item. On a site where both ERPNext UAE regional setup and one of these apps are installed, sync_customizations rewrites the regional rows on each migrate (utils.py:167-177). This is outside uae_compliance, but it means uae_compliance cannot trust the label, insert_after or fieldtype of those regional fields on a client site; only fieldname and existence.

Proposed. For 7.3, no installed app overrides the quick entry class, so the extension should wrap or subclass the class currently bound at frappe.ui.form.CustomerQuickEntryForm / SupplierQuickEntryForm at load time rather than assign a fresh class, so a future app that does the same still composes.

Proposed. For 11.4, on Dxbitz client sites the likely co-installed apps that also hook Sales Invoice validate / on_submit are fta_compliance, bitz_progress_billing, milestone_invoice, hangcha, internal_pms and tht. uae_compliance validation must not assume it runs first or last in doc_events order, and must not raise on fields these apps add.

Proposed. fta_compliance and uae_compliance both target UAE tax; fta_compliance adds its own fields on Customer, Supplier, Company and Sales Invoice (fta_* prefix) and re-creates ERPNext regional fields if missing. A decision entry is needed on whether uae_compliance reads fta_compliance data (for example default_vat_treatment, is_government, rcm_applicable) when present, or stays independent. Owner: P01 design. No blocker for P00.

## 10. Package import

Verified. /Users/aslam/frappe-local/loc16/env/bin/python -c "import uae_compliance, uae_compliance.hooks as h; print(h.app_license, h.app_title)" prints "agpl-3.0 UAE Compliance". uae_compliance.__version__ is 0.0.1. frappe.get_module_list('uae_compliance') returns ['UAE e-Invoicing'] in a site session. hooks.py: app_name uae_compliance (:1), app_title UAE Compliance (:2), app_publisher Dxbitz Technology (:3), app_license agpl-3.0 (:6); no fixtures, doc_events, after_install or after_migrate declared.

## Unresolved items

1. currency_precision blank fallback path (section 7). Owner: money-rules packet. Affects spec 5.3.
2. Whether uae_compliance should consume fta_compliance party fields when co-installed (section 9.6). Owner: P01 design decision entry. Affects 4.3 and 7.3.

## Commands used (all read-only)

- Python script through the bench env with frappe.init/connect and frappe.db.rollback() in finally (saved at scratch/p00/a3_inspect.py).
- bench version; bench --site uae.local scheduler status; bench --site uae.local mariadb -e (SELECT only).
- pgrep, ps, cat Procfile, json key listing of site_config.json.
- grep / sed over apps/frappe, apps/erpnext and the 21 non-core apps; a Python parser over fixtures/custom_field.json, fixtures/property_setter.json, custom/*.json and hooks.py (ast.literal_eval).
