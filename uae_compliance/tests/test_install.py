# Site tests. They need a site with a database, so they run in the site-tests
# workflow, not in the pure Python ci job.
#
# This directory deliberately has no __init__.py. Frappe's runner imports test
# modules by path and reaches this one as a namespace package, while the ci
# job's `unittest discover` skips any directory without __init__.py. That is
# what keeps a frappe import out of the pure Python run.

import frappe
from frappe.tests import IntegrationTestCase


class TestInstall(IntegrationTestCase):
	def test_app_is_installed(self):
		self.assertIn("uae_compliance", frappe.get_installed_apps())

	def test_module_exists(self):
		self.assertTrue(frappe.db.exists("Module Def", "UAE e-Invoicing"))


class A21InstallingAgainChangesNothing(IntegrationTestCase):
	"""Running the install steps twice leaves one of everything.

	Case A21. A migration runs these on every deployment, so anything that
	doubled would double every time somebody deployed.
	"""

	def test_the_roles_are_not_duplicated(self):
		from uae_compliance.install import after_migrate

		before = frappe.db.count("Role", {"role_name": ["like", "UAE Peppol%"]})
		after_migrate()
		after_migrate()
		self.assertEqual(frappe.db.count("Role", {"role_name": ["like", "UAE Peppol%"]}), before)

	def test_the_field_we_add_to_items_lands_once(self):
		from uae_compliance.install import add_item_type_field

		add_item_type_field()
		add_item_type_field()
		for doctype in ("Item", "Item Group"):
			self.assertEqual(
				frappe.db.count("Custom Field", {"dt": doctype, "fieldname": "uae_peppol_item_type"}),
				1,
				f"the field landed more than once on {doctype}",
			)

	def test_the_installed_rules_are_recorded_and_read_only(self):
		from uae_compliance.install import record_installed_rules

		record_installed_rules()
		settings = frappe.get_single("UAE Peppol Settings")
		self.assertTrue(settings.ruleset_version)
		self.assertTrue(settings.canonical_version)
		# Release owned. A site cannot point itself at rules it does not hold.
		self.assertTrue(settings.meta.get_field("ruleset_version").read_only)

	def test_we_add_nothing_to_the_invoice_itself(self):
		# Zero custom fields on Sales Invoice is a fixed decision, and the
		# whole design of the working record follows from it.
		for doctype in ("Sales Invoice", "Sales Invoice Item"):
			self.assertEqual(
				frappe.db.count("Custom Field", {"dt": doctype, "fieldname": ["like", "uae_peppol%"]}),
				0,
				f"this app has put a field on {doctype}",
			)

	def test_we_touch_no_other_apps_fields(self):
		# Installing must never overwrite another app's work. The only
		# fields this app owns anywhere are its own, on Item and Item Group.
		ours = frappe.get_all(
			"Custom Field", filters={"fieldname": ["like", "uae_peppol%"]}, fields=["dt", "fieldname"]
		)
		self.assertEqual({row.dt for row in ours}, {"Item", "Item Group"})
