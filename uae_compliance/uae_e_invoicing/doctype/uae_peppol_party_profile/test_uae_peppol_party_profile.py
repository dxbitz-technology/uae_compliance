"""Profiles and mappings, against a real site.

The theme running through these: a profile has to be saveable while it is
still incomplete, because the details usually arrive after the first invoice
does, and there has to be somewhere to record what is known so far. What it
must never do is turn somebody's answer into evidence.
"""

import frappe
from frappe.tests import IntegrationTestCase

TEST_COMPANY = "UAE Peppol Test Company"


def a_company():
	"""A company these tests own.

	They used to take whichever company the site happened to have, which
	works on a development site and fails on a fresh one where there is no
	company at all. A test that depends on data somebody else created is not
	a test of anything.
	"""
	if not frappe.db.exists("Company", TEST_COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": TEST_COMPANY,
				"abbr": "UPTC",
				"default_currency": "AED",
				"country": "United Arab Emirates",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	return TEST_COMPANY


def a_tax_account():
	"""Any account belonging to our own company."""
	return frappe.get_all("Account", filters={"company": a_company(), "is_group": 0}, pluck="name", limit=1)[
		0
	]


def a_customer(name="Test Buyer LLC"):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert(
			ignore_permissions=True
		)
	return name


class TestUAEPeppolPartyProfile(IntegrationTestCase):
	def a_profile(self, party=None, **values):
		doc = frappe.get_doc(
			{
				"doctype": "UAE Peppol Party Profile",
				"party_doctype": "Customer",
				"party": party or a_customer(),
				**values,
			}
		)
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "UAE Peppol Party Profile", doc.name, force=True)
		return doc

	def test_a_profile_saves_while_everything_is_still_unknown(self):
		# The details arrive later than the first invoice does.
		doc = self.a_profile()
		self.assertEqual(doc.vat_state, "Not sure")
		self.assertEqual(doc.peppol_state, "Not sure")
		self.assertEqual(doc.lookup_state, "Not checked")
		self.assertFalse(doc.endpoint_value)

	def test_a_party_gets_only_one_profile(self):
		customer = a_customer("Only Once LLC")
		self.a_profile(customer)
		with self.assertRaises(frappe.ValidationError):
			self.a_profile(customer)

	def test_saying_a_party_is_on_the_network_is_not_evidence(self):
		# Somebody telling us is a claim. The lookup result is separate and
		# stays untouched.
		doc = self.a_profile(a_customer("Claims To Be On It LLC"), peppol_state="Registered")
		self.assertEqual(doc.peppol_state, "Registered")
		self.assertEqual(doc.lookup_state, "Not checked")

	def test_nobody_can_mark_a_party_verified_by_hand(self):
		doc = self.a_profile(a_customer("Wants To Be Verified LLC"))
		doc.lookup_state = "Verified"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_a_lookup_may_record_a_party_as_verified(self):
		doc = self.a_profile(a_customer("Properly Checked LLC"))
		doc.lookup_state = "Verified"
		doc.lookup_method = "Directory lookup"
		doc.flags.from_lookup = True
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.lookup_state, "Verified")

	def test_a_foreign_party_keeps_both_registrations(self):
		doc = self.a_profile(
			a_customer("Foreign Buyer Ltd"),
			establishment_country="United Kingdom",
			vat_number="GB123456789",
			extra_vat_number="100000000000003",
		)
		self.assertEqual(doc.vat_number, "GB123456789")
		self.assertEqual(doc.extra_vat_number, "100000000000003")

	def test_being_an_individual_does_not_make_it_a_consumer_sale(self):
		doc = self.a_profile(a_customer("A Person"))
		self.assertEqual(doc.party_context, "Not sure")


class TestUAEPeppolSellerProfile(IntegrationTestCase):
	def a_seller(self, label, company=None, **values):
		doc = frappe.get_doc({"doctype": "UAE Peppol Seller Profile", "label": label, **values})
		if company:
			doc.append("companies", {"company": company, "mode": "Off"})
		doc.insert(ignore_permissions=True)
		# The base class rolls back once per class, not per test, so each test
		# clears up after itself or the company binding leaks into the next one.
		self.addCleanup(frappe.delete_doc, "UAE Peppol Seller Profile", doc.name, force=True)
		return doc

	def any_company(self):
		return a_company()

	def test_a_seller_saves_with_no_tax_number_yet(self):
		# Its name does not depend on having an identifier it may not have.
		doc = self.a_seller("Nothing Known Yet")
		self.assertEqual(doc.vat_state, "Not sure")
		self.assertFalse(doc.participant_value)
		self.assertEqual(doc.identity_state, "Not checked")

	def test_a_company_starts_switched_off(self):
		doc = self.a_seller("Fresh Binding", self.any_company())
		self.assertEqual(doc.companies[0].mode, "Off")
		self.assertEqual(doc.mode_for(self.any_company()), "Off")

	def test_a_company_nobody_bound_reads_as_off(self):
		doc = self.a_seller("No Companies")
		self.assertEqual(doc.mode_for("Some Company That Is Not Bound"), "Off")

	def test_a_company_cannot_belong_to_two_sellers(self):
		company = self.any_company()
		self.a_seller("First Holder", company)
		with self.assertRaises(frappe.ValidationError):
			self.a_seller("Second Holder", company)

	def test_going_live_needs_a_date_it_takes_effect_from(self):
		doc = self.a_seller("Going Live Soon")
		doc.append("companies", {"company": self.any_company(), "mode": "Live"})
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_nobody_can_mark_their_own_identity_verified(self):
		doc = self.a_seller("Self Certified")
		doc.identity_state = "Verified"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_a_vat_group_does_not_merge_two_sellers(self):
		# Sharing a group registration does not make two companies one
		# participant on the network.
		one = self.a_seller(
			"Group Member One", vat_state="Registered", vat_number="100000000000003", in_vat_group=1
		)
		two = self.a_seller(
			"Group Member Two", vat_state="Registered", vat_number="100000000000003", in_vat_group=1
		)
		self.assertNotEqual(one.name, two.name)


class TestUAEPeppolTaxCategory(IntegrationTestCase):
	def any_company(self):
		return a_company()

	def any_account(self):
		return a_tax_account()

	def a_mapping(self, **values):
		doc = frappe.get_doc(
			{
				"doctype": "UAE Peppol Tax Category",
				"company": self.any_company(),
				"account_head": self.any_account(),
				"category": "S",
				"rate": 5,
				**values,
			}
		)
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "UAE Peppol Tax Category", doc.name, force=True)
		return doc

	def test_a_mapping_needs_something_to_match_on(self):
		with self.assertRaises(frappe.ValidationError):
			self.a_mapping(account_head=None, item_tax_template=None)

	def test_two_mappings_that_would_both_match_are_refused(self):
		# Picking the first match would make the tax on an invoice depend on
		# the order the rows happen to be in.
		self.a_mapping()
		with self.assertRaises(frappe.ValidationError):
			self.a_mapping()

	def test_an_exempt_mapping_has_to_say_why(self):
		with self.assertRaises(frappe.ValidationError):
			self.a_mapping(category="E", rate=0)

	def test_an_exempt_mapping_with_a_reason_is_fine(self):
		doc = self.a_mapping(category="E", rate=0, reason_code="DL8.46.2", reason="Residential lease")
		self.assertEqual(doc.category, "E")

	def test_margin_is_the_letter_n(self):
		options = frappe.get_meta("UAE Peppol Tax Category").get_field("category").options.split("\n")
		self.assertIn("N", options)
		self.assertNotIn("M", options)
