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
