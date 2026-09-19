"""The services nothing was covering. Cases A07, A10, A11 and A22.

Four pieces of the app had no tests at all: creating a party, fixing items
in bulk, the freeze rolling back with its invoice, and the safeguard that
stops a restored copy of a site from sending. Each one either writes to
somebody's books or decides whether real invoices go out.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from uae_compliance.development.fixtures import a_company, a_seller, an_invoice


class A07CreatingAParty(IntegrationTestCase):
	"""The party, its address and contact, and its profile, or none of them."""

	def values(self, name, **extra):
		return frappe.as_json(
			{
				"customer_name": name,
				"customer_type": "Company",
				"country": "United Arab Emirates",
				"address_line1": "Unit 1, Test Tower",
				"city": "Dubai",
				**extra,
			}
		)

	def test_one_call_makes_the_party_its_address_and_its_profile(self):
		from uae_compliance.services import party_entry

		name = "A07 Complete LLC"
		self.addCleanup(self.clear, name)
		made = party_entry.create_party(
			"Customer",
			self.values(name, vat_state="Registered", vat_number="100000000000003"),
		)
		self.assertTrue(frappe.db.exists("Customer", made["name"]))
		self.assertTrue(made["profile"])
		linked = frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Customer", "link_name": made["name"], "parenttype": "Address"},
			pluck="parent",
		)
		self.assertEqual(len(linked), 1, "one address, not none and not two")

	def test_what_somebody_told_us_never_becomes_evidence(self):
		from uae_compliance.services import party_entry

		name = "A07 Claims LLC"
		self.addCleanup(self.clear, name)
		made = party_entry.create_party(
			"Customer",
			self.values(name, peppol_state="Registered", endpoint_scheme="0235", endpoint_value="1"),
		)
		profile = frappe.get_doc("UAE Peppol Party Profile", made["profile"])
		self.assertEqual(profile.peppol_state, "Registered")
		self.assertEqual(profile.lookup_state, "Not checked")

	def test_a_caller_cannot_mark_a_party_verified_on_the_way_in(self):
		# The worst thing this door could be used for. A caller crafting a
		# payload that says the party was checked would turn a claim into
		# evidence, and everything downstream trusts evidence.
		from uae_compliance.services import party_entry

		name = "A07 Wants To Be Verified LLC"
		self.addCleanup(self.clear, name)
		# Two things stop it and only one of them is this door. The field
		# list here drops what it does not allow, and the profile itself
		# refuses to be marked verified by anything but a lookup. Checked
		# with the door held open, so what is being proved is the second
		# guard and not the first.
		held_open = (*party_entry.PROFILE_FIELDS, "lookup_state")
		with patch.object(party_entry, "PROFILE_FIELDS", held_open):
			with self.assertRaises(frappe.ValidationError) as refused:
				party_entry.create_party("Customer", self.values(name, lookup_state="Verified"))
		self.assertIn("lookup", str(refused.exception).lower())

		# And with the door shut, the claim is simply dropped.
		made = party_entry.create_party("Customer", self.values(name, lookup_state="Verified"))
		profile = frappe.get_doc("UAE Peppol Party Profile", made["profile"])
		self.assertEqual(profile.lookup_state, "Not checked")

	def test_the_country_fills_in_both_meanings_and_they_stay_apart(self):
		from uae_compliance.services import party_entry

		name = "A07 Country LLC"
		self.addCleanup(self.clear, name)
		made = party_entry.create_party("Customer", self.values(name, vat_state="Registered"))
		profile = frappe.get_doc("UAE Peppol Party Profile", made["profile"])
		self.assertEqual(profile.establishment_country, "United Arab Emirates")

	def test_a_party_nobody_said_anything_about_still_claims_nothing(self):
		# It does get a profile, because the country is a real fact and
		# extraction needs a profile anyway, so recording it here saves an
		# error later. What it must not do is look answered.
		from uae_compliance.services import party_entry

		name = "A07 Nothing Known LLC"
		self.addCleanup(self.clear, name)
		made = party_entry.create_party("Customer", self.values(name))
		profile = frappe.get_doc("UAE Peppol Party Profile", made["profile"])
		self.assertEqual(profile.establishment_country, "United Arab Emirates")
		self.assertEqual(profile.vat_state, "Not sure")
		self.assertEqual(profile.peppol_state, "Not sure")
		self.assertEqual(profile.lookup_state, "Not checked")
		self.assertFalse(profile.vat_number)

	def test_a_party_with_no_country_either_gets_no_profile(self):
		# Nothing at all is nothing to record.
		from uae_compliance.services import party_entry

		name = "A07 Truly Nothing LLC"
		self.addCleanup(self.clear, name)
		made = party_entry.create_party(
			"Customer", frappe.as_json({"customer_name": name, "customer_type": "Company"})
		)
		self.assertIsNone(made["profile"])

	def test_only_a_customer_or_a_supplier(self):
		from uae_compliance.services import party_entry

		with self.assertRaises(frappe.ValidationError):
			party_entry.create_party("Item", self.values("A07 Not A Party"))

	def clear(self, name):
		for address in frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Customer", "link_name": name, "parenttype": "Address"},
			pluck="parent",
		):
			frappe.delete_doc("Address", address, force=True)
		profile = frappe.db.exists("UAE Peppol Party Profile", {"party": name})
		if profile:
			frappe.delete_doc("UAE Peppol Party Profile", profile, force=True)
		if frappe.db.exists("Customer", name):
			frappe.delete_doc("Customer", name, force=True)


class A07SettingUpACompany(IntegrationTestCase):
	def test_it_goes_into_preparation_and_nowhere_further(self):
		# Preparation collects and checks and sends nothing, so a company
		# can be set up long before there is a provider.
		from uae_compliance.services import party_entry

		company = a_company()
		existing = frappe.db.get_value(
			"UAE Peppol Seller Company",
			{"company": company, "parenttype": "UAE Peppol Seller Profile"},
			"parent",
		)
		if existing:
			self.assertFalse(party_entry.set_up_company(company)["created"])
			return
		found = party_entry.set_up_company(company)
		self.assertEqual(found["mode"], "Preparation")
		self.assertTrue(found["created"])

	def test_running_it_twice_changes_nothing(self):
		from uae_compliance.services import party_entry

		company = a_company()
		party_entry.set_up_company(company)
		again = party_entry.set_up_company(company)
		self.assertFalse(again["created"])


class A10FixingItemsInBulk(IntegrationTestCase):
	def an_item(self, code):
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": frappe.get_all("Item Group", filters={"is_group": 0}, pluck="name")[0],
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)
		self.addCleanup(frappe.db.set_value, "Item", code, "uae_peppol_item_type", None)
		return code

	def test_several_items_are_set_at_once(self):
		from uae_compliance.services import party_entry

		codes = [self.an_item("A10-ITEM-1"), self.an_item("A10-ITEM-2")]
		changed = party_entry.set_item_type(frappe.as_json(codes), "Goods")
		self.assertEqual(changed, 2)
		for code in codes:
			self.assertEqual(frappe.db.get_value("Item", code, "uae_peppol_item_type"), "Goods")

	def test_it_is_goods_services_or_both_and_nothing_else(self):
		from uae_compliance.services import party_entry

		code = self.an_item("A10-ITEM-3")
		with self.assertRaises(frappe.ValidationError):
			party_entry.set_item_type(frappe.as_json([code]), "Whatever")

	def test_a_bulk_fix_is_bounded(self):
		from uae_compliance.services import party_entry

		code = self.an_item("A10-ITEM-4")
		changed = party_entry.set_item_type(frappe.as_json([code] * 500), "Services")
		self.assertLessEqual(changed, 100, "an unbounded bulk write is a way to hold the site up")


class A11RollingBack(IntegrationTestCase):
	"""A rollback leaves no work that could transmit."""

	def setUp(self):
		super().setUp()
		a_seller("Live")
		self.addCleanup(a_seller, "Preparation")

	def test_a_rollback_after_the_freeze_leaves_nothing_sendable(self):
		before = frappe.db.count("UAE Peppol Submission")
		invoice = an_invoice()
		try:
			invoice.submit()
		except frappe.ValidationError:
			# Live refuses an incomplete invoice, which is its own test.
			# What matters here is that nothing was left behind.
			pass
		frappe.db.rollback()
		self.assertEqual(frappe.db.count("UAE Peppol Submission"), before)
		self.assertEqual(
			frappe.db.count(
				"UAE Peppol Submission", {"processing_state": ["in", ["Ready", "Retry scheduled"]]}
			),
			0,
			"a rollback left work a worker could pick up",
		)


class A22StoppingARestoredCopy(IntegrationTestCase):
	"""A copy of this site cannot send real invoices."""

	def setUp(self):
		super().setUp()
		from uae_compliance.services import deployment

		self.deployment = deployment
		self.known = frappe.db.get_global(deployment.HOST_KEY)
		self.addCleanup(self.restore)

	def restore(self):
		frappe.db.set_global(self.deployment.HOST_KEY, self.known)
		settings = frappe.get_single("UAE Peppol Settings")
		settings.pause_outbound = 0
		settings.pause_reason = None
		settings.flags.ignore_permissions = True
		settings.save()

	def test_production_sending_is_off_unless_the_deployment_granted_it(self):
		# The permission lives in the site's configuration file, which a
		# database restore does not bring with it.
		allowed, reason = self.deployment.production_sending_allowed()
		self.assertFalse(allowed)
		self.assertTrue(reason)

	def test_a_key_granted_for_another_site_does_not_work_here(self):
		frappe.conf[self.deployment.CONFIG_KEY] = "somebody-elses-site.com"
		self.addCleanup(frappe.conf.pop, self.deployment.CONFIG_KEY, None)
		allowed, reason = self.deployment.production_sending_allowed()
		self.assertFalse(allowed)
		self.assertIn("another site", reason)

	def test_the_right_key_does(self):
		frappe.conf[self.deployment.CONFIG_KEY] = frappe.local.site
		self.addCleanup(frappe.conf.pop, self.deployment.CONFIG_KEY, None)
		allowed, _reason = self.deployment.production_sending_allowed()
		self.assertTrue(allowed)

	def test_the_database_turning_up_elsewhere_pauses_everything(self):
		from uae_compliance.services import outbox

		frappe.db.set_global(self.deployment.HOST_KEY, "a-different-machine")
		allowed, reason = self.deployment.check_environment()
		self.assertFalse(allowed)
		self.assertTrue(reason)
		self.assertTrue(frappe.db.get_single_value("UAE Peppol Settings", "pause_outbound"))
		self.assertEqual(outbox.due(), [], "a restored copy was handed work to send")

	def test_a_manager_can_confirm_a_genuine_move(self):
		frappe.db.set_global(self.deployment.HOST_KEY, "a-different-machine")
		self.deployment.check_environment()
		self.deployment.confirm_this_machine()
		self.assertFalse(frappe.db.get_single_value("UAE Peppol Settings", "pause_outbound"))
		allowed, _reason = self.deployment.check_environment()
		self.assertTrue(allowed)
