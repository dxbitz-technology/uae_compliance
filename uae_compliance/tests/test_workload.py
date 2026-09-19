"""How checking behaves as an invoice gets bigger.

The timings here are not a capacity claim. This is a developer's laptop and
not the reference host in spec 11.2, so what is measured is the shape rather
than the number: does the work grow with the invoice, and how.

The query count is the part that matters and it is host independent. Spec
11.2 requires that master queries do not grow by one per row, and when this
was first measured they grew by four. A five hundred line invoice asked two
thousand and fifty questions of the database, most of them the same question
about the same item.
"""

import frappe
from frappe.tests import IntegrationTestCase

from uae_compliance.development.fixtures import (
	DUE_DATE,
	POSTING_DATE,
	a_company,
	a_customer,
	a_price_list,
	a_seller,
	an_address,
	an_item,
)


def counting_queries():
	"""Count what reaches the database, whatever route it takes."""
	real = frappe.db.sql
	counter = {"n": 0}

	def counted(*args, **kwargs):
		counter["n"] += 1
		return real(*args, **kwargs)

	return real, counted, counter


class QueriesDoNotGrowWithTheInvoice(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		a_seller("Preparation")

	def an_invoice_of(self, rows: int):
		company = a_company()
		income = frappe.db.get_value(
			"Account", {"company": company, "account_type": "Income Account", "is_group": 0}, "name"
		)
		centre = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
		line = {
			"item_code": an_item(),
			"qty": 1,
			"uom": "Nos",
			"rate": 100,
			"income_account": income,
			"cost_center": centre,
		}
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": company,
				"customer": a_customer(),
				"customer_address": an_address(a_customer(), "Customer", a_customer()),
				"company_address": an_address("ATC Office", "Company", company),
				"currency": "AED",
				"conversion_rate": 1,
				"selling_price_list": a_price_list(),
				"price_list_currency": "AED",
				"plc_conversion_rate": 1,
				"posting_date": POSTING_DATE,
				"due_date": DUE_DATE,
				"items": [dict(line) for _ in range(rows)],
			}
		)
		invoice.set_missing_values()
		invoice.calculate_taxes_and_totals()
		invoice.insert(ignore_permissions=True)
		return invoice

	def queries_for(self, invoice, level) -> int:
		from uae_compliance.services import validation

		# Warm first. The framework caches metadata on first touch and that
		# is not what is being measured.
		validation.check(invoice, level)
		real, counted, counter = counting_queries()
		frappe.db.sql = counted
		try:
			validation.check(invoice, level)
		finally:
			frappe.db.sql = real
		return counter["n"]

	def test_a_long_invoice_asks_no_more_than_a_short_one(self):
		from uae_compliance.domain.findings import Level

		short = self.queries_for(self.an_invoice_of(1), Level.FAST)
		long = self.queries_for(self.an_invoice_of(100), Level.FAST)
		# Some slack for anything the framework does differently with a
		# bigger document, but nothing like one per row.
		self.assertLessEqual(
			long,
			short + 10,
			f"a hundred rows cost {long} queries against {short} for one row",
		)

	def test_the_same_item_a_hundred_times_is_asked_about_once(self):
		from uae_compliance.domain.findings import Level

		# The case that was wrong. Every line is the same item, the same
		# unit and the same tax account, and each was looked up again.
		invoice = self.an_invoice_of(100)
		count = self.queries_for(invoice, Level.FULL)
		self.assertLess(count, 100, f"a hundred identical lines still cost {count} queries")

	def test_asking_once_still_notices_when_the_answer_changes(self):
		# Asking once must not mean missing a change. If remembering an
		# answer stopped the fingerprint moving, a draft would look current
		# forever after somebody edited the item it sits on.
		from uae_compliance.erpnext.extract import extract

		invoice = self.an_invoice_of(3)
		before, _findings = extract(invoice)
		self.assertIn(
			f"Item:{an_item()}",
			_masters_read(invoice),
			"the item is not in the fingerprint, so editing it would go unnoticed",
		)

		frappe.db.set_value("Item", an_item(), "description", "Edited during the test")
		frappe.db.commit()

		after, _findings = extract(invoice)
		self.assertNotEqual(
			before["provenance"]["master_fingerprint"],
			after["provenance"]["master_fingerprint"],
			"the fingerprint did not move when the item did",
		)


def _masters_read(invoice) -> dict:
	"""Every master one extraction touched, with when it last changed."""
	from uae_compliance.erpnext import lines as line_reader
	from uae_compliance.erpnext.masters import resolve

	resolution = resolve(invoice)
	line_reader.extract(invoice, resolution, credit_note=False)
	return resolution.revisions
