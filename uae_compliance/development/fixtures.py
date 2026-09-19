"""Records the acceptance tests build for themselves.

They live here rather than beside the tests because the tests directory is a
namespace package on purpose, which means one test module cannot import
another. AGENTS.md explains why it has to stay that way.

Everything here builds its own company. A test that leans on whatever the
site happens to hold is not a test of anything, and taking a company another
test owns makes that one fail somewhere unrelated.
"""

import frappe

COMPANY = "Acceptance Test Co"
ABBR = "ATC"
CUSTOMER = "Acceptance Buyer LLC"
ITEM = "ACCEPTANCE-ITEM-1"


def a_company() -> str:
	if not frappe.db.exists("Company", COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": COMPANY,
				"abbr": ABBR,
				"default_currency": "AED",
				"country": "United Arab Emirates",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	return COMPANY


def a_customer() -> str:
	if not frappe.db.exists("Customer", CUSTOMER):
		frappe.get_doc({"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company"}).insert(
			ignore_permissions=True
		)
	return CUSTOMER


def an_item() -> str:
	if not frappe.db.exists("Item", ITEM):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": ITEM,
				"item_name": "Acceptance item",
				"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name")[0],
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
	return ITEM


def an_address(title: str, doctype: str, name: str) -> str:
	existing = frappe.db.exists("Address", {"address_title": title})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": title,
				"address_type": "Billing",
				"address_line1": "Office 1, Test Tower",
				"city": "Dubai",
				"emirate": "Dubai",
				"country": "United Arab Emirates",
				"links": [{"link_doctype": doctype, "link_name": name}],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def a_seller(mode: str = "Preparation") -> str:
	"""The seller binding for our own company, at the mode asked for."""
	company = a_company()
	existing = frappe.db.get_value(
		"UAE Peppol Seller Company",
		{"company": company, "parenttype": "UAE Peppol Seller Profile"},
		"parent",
	)
	if existing:
		profile = frappe.get_doc("UAE Peppol Seller Profile", existing)
		for row in profile.companies:
			if row.company == company:
				row.mode = mode
				row.effective_from = "2026-01-01"
		profile.flags.ignore_permissions = True
		profile.save()
		frappe.db.commit()
		return profile.name

	profile = frappe.get_doc(
		{
			"doctype": "UAE Peppol Seller Profile",
			"label": "Acceptance Seller",
			"participant_scheme": "0235",
			"participant_value": "100000000000003",
			"vat_state": "Registered",
			"vat_number": "100000000000003",
			"legal_scheme": "TL",
			"legal_value": "9999999",
		}
	)
	profile.append(
		"companies",
		{
			"company": company,
			"mode": mode,
			"effective_from": "2026-01-01",
			"default_address": an_address("ATC Office", "Company", company),
		},
	)
	profile.insert(ignore_permissions=True)
	frappe.db.commit()
	return profile.name


def an_invoice(**values):
	company = a_company()
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": a_customer(),
			"customer_address": an_address(CUSTOMER, "Customer", a_customer()),
			"company_address": an_address("ATC Office", "Company", company),
			"currency": "AED",
			"conversion_rate": 1,
			"posting_date": "2026-09-19",
			"due_date": "2026-10-19",
			"items": [
				{
					"item_code": an_item(),
					"qty": 2,
					"uom": "Nos",
					"rate": 100,
					"income_account": frappe.db.get_value(
						"Account",
						{"company": company, "account_type": "Income Account", "is_group": 0},
						"name",
					),
					"cost_center": frappe.db.get_value(
						"Cost Center", {"company": company, "is_group": 0}, "name"
					),
				}
			],
			**values,
		}
	)
	invoice.set_missing_values()
	invoice.calculate_taxes_and_totals()
	invoice.insert(ignore_permissions=True)
	return invoice
