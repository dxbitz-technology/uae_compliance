"""Build one ordinary invoice on a development site, so the chain can be run.

This exists because the only honest way to check extraction is against an
invoice ERPNext actually posted. It builds the first worked example in spec
5.3: two units at AED 100, a line discount of 20 and VAT at 5 percent, which
should post as net 180, tax 9 and total 189.

It uses its own company so it never collides with the site tests, which own
UAE Peppol Test Company. Safe to run again. Every record is reused if it is
already there.

	bench --site <site> execute uae_compliance.development.build_invoice.run

Development only. It creates masters and posts a document, so do not point it
at anything real.
"""

import frappe

COMPANY = "Peppol Demo Co"
BUYING_COMPANY = "Peppol Buying Demo"
BUYING_ABBR = "PBD"
# The tax number the published example invoices are addressed to, so a
# document seeded into the simulator inbox finds a company here.
BUYING_TAX_ID = "134567890123003"
ABBR = "PDC"
ITEM = "PEPPOL-DEMO-001"
CUSTOMER = "Gulf Trading LLC"


def run():
	company = _company()
	seller_address = _address("PDC Head Office", "Company", company, "Office 101, Business Tower")
	customer = _customer()
	buyer_address = _address(CUSTOMER, "Customer", customer, "Warehouse 4, Al Quoz")
	item = _item()
	vat_account = _vat_account(company)
	_seller_profile(company, seller_address)
	_party_profile(customer)
	_tax_mapping(company, vat_account)
	frappe.db.commit()

	name = _invoice(company, customer, buyer_address, seller_address, item, vat_account)
	frappe.db.commit()
	print(f"invoice {name}")
	return name


def _company():
	if frappe.db.exists("Company", COMPANY):
		return COMPANY
	frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": COMPANY,
			"abbr": ABBR,
			"default_currency": "AED",
			"country": "United Arab Emirates",
			"tax_id": "100000000000003",
		}
	).insert(ignore_permissions=True)
	return COMPANY


def _address(title, link_doctype, link_name, line1):
	existing = frappe.db.exists("Address", {"address_title": title})
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": title,
				"address_type": "Billing",
				"address_line1": line1,
				"city": "Dubai",
				# ibr-143-ae and ibr-144-ae both want the country subdivision.
				"emirate": "Dubai",
				"country": "United Arab Emirates",
				"links": [{"link_doctype": link_doctype, "link_name": link_name}],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _customer():
	if frappe.db.exists("Customer", CUSTOMER):
		return CUSTOMER
	frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": CUSTOMER,
			"customer_type": "Company",
			"tax_id": "100000000000003",
		}
	).insert(ignore_permissions=True)
	return CUSTOMER


def _item():
	if frappe.db.exists("Item", ITEM):
		return ITEM
	# The tariff number is a link, so the record has to exist before an item
	# can point at it. Its name is the code itself, which is what goes on the
	# document.
	if not frappe.db.exists("Customs Tariff Number", "7326"):
		frappe.get_doc(
			{
				"doctype": "Customs Tariff Number",
				"tariff_number": "7326",
				"description": "Other articles of iron or steel",
			}
		).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": ITEM,
			"item_name": "Steel bracket",
			"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name")[0],
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"uae_peppol_item_type": "Goods",
			# ibr-184-ae wants a classification once the type says Goods.
			"customs_tariff_number": "7326",
		}
	).insert(ignore_permissions=True)
	return ITEM


def _vat_account(company):
	existing = frappe.db.get_value(
		"Account", {"company": company, "account_name": "VAT 5 percent", "is_group": 0}, "name"
	)
	if existing:
		return existing
	parent = frappe.db.get_value(
		"Account", {"company": company, "account_name": "Duties and Taxes", "is_group": 1}, "name"
	)
	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "VAT 5 percent",
				"parent_account": parent,
				"company": company,
				"account_type": "Tax",
				"root_type": "Liability",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _seller_profile(company, address):
	if frappe.db.exists("UAE Peppol Seller Profile", {"label": "Peppol Demo Seller"}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "UAE Peppol Seller Profile",
			"label": "Peppol Demo Seller",
			"participant_scheme": "0235",
			"participant_value": "100000000000003",
			"vat_state": "Registered",
			"vat_number": "100000000000003",
			# ibr-173-ae accepts only TL, EID, PAS or CD here.
			"legal_scheme": "TL",
			"legal_value": "1234567",
			"legal_authority": "Dubai Department of Economic Development",
		}
	)
	doc.append(
		"companies",
		{
			"company": company,
			"mode": "Preparation",
			"effective_from": "2026-09-01",
			"default_address": address,
		},
	)
	doc.insert(ignore_permissions=True)


def _party_profile(customer):
	if frappe.db.exists("UAE Peppol Party Profile", {"party": customer}):
		return
	frappe.get_doc(
		{
			"doctype": "UAE Peppol Party Profile",
			"party_doctype": "Customer",
			"party": customer,
			"establishment_country": "United Arab Emirates",
			"party_context": "Business",
			"vat_state": "Registered",
			"vat_number": "100000000000003",
			"peppol_state": "Registered",
			"endpoint_scheme": "0235",
			"endpoint_value": "100000000000003",
		}
	).insert(ignore_permissions=True)


def _tax_mapping(company, vat_account):
	if frappe.db.exists("UAE Peppol Tax Category", {"company": company, "account_head": vat_account}):
		return
	frappe.get_doc(
		{
			"doctype": "UAE Peppol Tax Category",
			"company": company,
			"account_head": vat_account,
			"category": "S",
			"rate": 5,
		}
	).insert(ignore_permissions=True)


def _invoice(company, customer, buyer_address, seller_address, item, vat_account):
	existing = frappe.db.exists("Sales Invoice", {"company": company, "docstatus": ["<", 2]})
	if existing:
		return existing
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": company,
			"customer": customer,
			"customer_address": buyer_address,
			"company_address": seller_address,
			"currency": "AED",
			"conversion_rate": 1,
			"posting_date": "2026-09-18",
			"due_date": "2026-10-18",
			"items": [
				{
					"item_code": item,
					"qty": 2,
					"uom": "Nos",
					"price_list_rate": 100,
					"discount_amount": 10,
					"rate": 90,
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
			"taxes": [
				{
					"charge_type": "On Net Total",
					"account_head": vat_account,
					"description": "VAT 5%",
					"rate": 5,
				}
			],
		}
	)
	invoice.set_missing_values()
	invoice.calculate_taxes_and_totals()
	invoice.insert(ignore_permissions=True)
	return invoice.name


def set_up_buying():
	"""Prepare a company that can take in a supplier's invoice.

	Its own company on purpose. UAE Peppol Test Company belongs to the site
	tests, and taking it makes them fail in ways that look unrelated.
	"""
	if not frappe.db.exists("Company", BUYING_COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": BUYING_COMPANY,
				"abbr": BUYING_ABBR,
				"default_currency": "AED",
				"country": "United Arab Emirates",
				"tax_id": BUYING_TAX_ID,
			}
		).insert(ignore_permissions=True)

	# The sender of one of the published examples, so it matches something.
	if not frappe.db.exists("Supplier", "Seller Legal Name"):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "Seller Legal Name",
				"supplier_type": "Company",
				"tax_id": "198765432102003",
			}
		).insert(ignore_permissions=True)

	item = "INBOUND-UNMATCHED"
	if not frappe.db.exists("Item", item):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item,
				"item_name": "Supplier line, not yet matched",
				"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name")[0],
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)

	expense = frappe.db.get_value(
		"Account", {"company": BUYING_COMPANY, "root_type": "Expense", "is_group": 0}, "name"
	)
	vat = _vat_account(BUYING_COMPANY)
	if not frappe.db.exists("UAE Peppol Tax Category", {"company": BUYING_COMPANY, "account_head": vat}):
		frappe.get_doc(
			{
				"doctype": "UAE Peppol Tax Category",
				"company": BUYING_COMPANY,
				"account_head": vat,
				"category": "S",
				"rate": 5,
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("UAE Peppol Seller Profile", {"label": "Peppol Buying Demo"}):
		profile = frappe.get_doc({"doctype": "UAE Peppol Seller Profile", "label": "Peppol Buying Demo"})
		profile.append(
			"companies",
			{
				"company": BUYING_COMPANY,
				"mode": "Preparation",
				"inbound_item": item,
				"inbound_expense_account": expense,
			},
		)
		profile.insert(ignore_permissions=True)

	frappe.db.commit()
	print(f"buying set up on {BUYING_COMPANY}")
	return BUYING_COMPANY
