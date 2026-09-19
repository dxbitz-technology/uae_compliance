"""What somebody who should not see it cannot see.

Case A19 in spec 13. A person restricted to one company must not be able to
read or change another company's statuses, counts, attempt records,
evidence or the errors derived from its invoices.

The interesting part is not whether opening a document is refused. It is
whether listing them is, because a list that leaks row counts and document
numbers has leaked most of what matters. One of these tests exists because
that leak was real.
"""

import frappe
from frappe.tests import IntegrationTestCase

from uae_compliance.development.fixtures import a_company, a_seller, an_invoice

RESTRICTED = "restricted.acceptance@example.com"
OTHER_COMPANY = "Someone Elses Company"


def a_restricted_user() -> str:
	"""Somebody with the app's ordinary role, allowed one company only."""
	if not frappe.db.exists("User", RESTRICTED):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": RESTRICTED,
				"first_name": "Restricted",
				"send_welcome_email": 0,
			}
		)
		user.append("roles", {"role": "UAE Peppol User"})
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)

	if not frappe.db.exists("Company", OTHER_COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": OTHER_COMPANY,
				"abbr": "SEC",
				"default_currency": "AED",
				"country": "United Arab Emirates",
			}
		).insert(ignore_permissions=True)

	# Allowed the other company, and so not the one the invoices belong to.
	if not frappe.db.exists(
		"User Permission", {"user": RESTRICTED, "allow": "Company", "for_value": OTHER_COMPANY}
	):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": RESTRICTED,
				"allow": "Company",
				"for_value": OTHER_COMPANY,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
	frappe.db.commit()
	return RESTRICTED


class A19AnotherCompanysWork(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		a_seller("Preparation")
		self.invoice = an_invoice()
		self.user = a_restricted_user()
		frappe.db.commit()
		self.addCleanup(frappe.set_user, "Administrator")

	def as_restricted(self):
		frappe.set_user(self.user)

	def test_they_cannot_list_another_companys_working_records(self):
		# The leak that was real. Opening one was refused and listing them
		# was not, which gives away the count and every document number.
		self.as_restricted()
		rows = frappe.get_list("UAE Peppol Invoice", ignore_permissions=False)
		self.assertEqual(rows, [], f"they could see {len(rows)} working records")

	def test_they_cannot_list_another_companys_submissions(self):
		self.as_restricted()
		self.assertEqual(frappe.get_list("UAE Peppol Submission"), [])

	def test_they_cannot_list_another_companys_attempts(self):
		self.as_restricted()
		self.assertEqual(frappe.get_list("UAE Peppol Transmission Log"), [])

	def test_the_readiness_report_shows_them_nothing(self):
		from uae_compliance.uae_e_invoicing.report.uae_e_invoicing_readiness import (
			uae_e_invoicing_readiness as readiness,
		)

		self.as_restricted()
		_columns, rows = readiness.execute({})
		self.assertEqual(rows, [], f"the report showed them {len(rows)} invoices")

	def test_they_cannot_read_another_companys_working_record(self):
		self.as_restricted()
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("UAE Peppol Invoice", self.invoice.name).check_permission("read")

	def test_they_cannot_check_another_companys_invoice(self):
		from uae_compliance.services import api

		self.as_restricted()
		with self.assertRaises(frappe.PermissionError):
			api.preview_invoice(self.invoice.name)

	def test_a_readiness_batch_filters_out_what_they_cannot_read(self):
		from uae_compliance.services import api

		self.as_restricted()
		found = api.get_readiness_batch(frappe.as_json([self.invoice.name]))
		self.assertEqual(found, {})

	def test_they_cannot_save_details_on_another_companys_invoice(self):
		from uae_compliance.services import api

		self.as_restricted()
		with self.assertRaises(frappe.PermissionError):
			api.save_invoice_inputs(self.invoice.name, 0, frappe.as_json({"export": 1}))
