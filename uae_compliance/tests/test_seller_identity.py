"""The seller's identity, tested against a real site.

One thing matters here: the participant identity is how the outside world
names this seller, so exactly one profile may hold it. A VAT number is a
different fact and deliberately shareable, because the members of a VAT
group all carry the group's registration.
"""

import frappe
from frappe.tests import IntegrationTestCase


class TestUAEPeppolSellerProfile(IntegrationTestCase):
	def a_profile(self, label, **values):
		doc = frappe.get_doc(
			{
				"doctype": "UAE Peppol Seller Profile",
				"label": label,
				**values,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_one_identity_belongs_to_one_profile(self):
		self.a_profile("Identity Holder", participant_scheme="0235", participant_value="100000000000203")
		with self.assertRaises(frappe.ValidationError):
			self.a_profile("Identity Chaser", participant_scheme="0235", participant_value="100000000000203")

	def test_profiles_still_missing_their_identity_can_coexist(self):
		# Most of a profile's details arrive later than the profile. Two
		# blanks are two unknowns, not one identity claimed twice.
		self.a_profile("Waiting One", participant_scheme="0235")
		self.a_profile("Waiting Two", participant_scheme="0235")

	def test_a_blank_identity_is_stored_as_nothing(self):
		doc = self.a_profile("Blank Strings", participant_value="  ", vat_number="")
		self.assertIsNone(doc.participant_value)
		self.assertIsNone(doc.vat_number)

	def test_a_vat_group_number_is_shareable(self):
		# Group members invoice under their own identity and the group's one
		# registration. The registration cannot be unique.
		self.a_profile(
			"Group Member One",
			participant_scheme="0235",
			participant_value="100000000000303",
			vat_number="100000000000403",
		)
		self.a_profile(
			"Group Member Two",
			participant_scheme="0235",
			participant_value="100000000000503",
			vat_number="100000000000403",
		)

	def test_a_shared_group_number_attributes_no_arriving_document(self):
		from uae_compliance.services.receiving import _find_company

		self.a_profile(
			"Group Claim One",
			participant_scheme="0235",
			participant_value="100000000000603",
			vat_number="100000000000703",
		)
		self.a_profile(
			"Group Claim Two",
			participant_scheme="0235",
			participant_value="100000000000803",
			vat_number="100000000000703",
		)
		self.assertIsNone(
			_find_company("100000000000703"),
			"a document addressed to a shared group number was attributed by luck",
		)
