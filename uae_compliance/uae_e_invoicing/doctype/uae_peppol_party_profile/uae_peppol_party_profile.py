"""What we know about a customer or a supplier.

It saves while incomplete, because the details often arrive later than the
first invoice and there has to be somewhere to put what is known.

The rule worth stating: what somebody tells us and what a lookup found are
two different fields and never touch. Somebody saying they are on the network
is a claim. Only a lookup records the party as verified.
"""

import frappe
from frappe import _
from frappe.model.document import Document

ALLOWED_PARTIES = ("Customer", "Supplier")


class UAEPeppolPartyProfile(Document):
	def autoname(self):
		self.name = f"{self.party_doctype}-{self.party}"

	def validate(self):
		self.reject_other_party_types()
		self.reject_duplicate_profile()
		self.reject_manual_verification()

	def reject_other_party_types(self):
		if self.party_doctype not in ALLOWED_PARTIES:
			frappe.throw(
				_("Only a customer or a supplier has a party profile."),
				title=_("Not a party"),
			)

	def reject_duplicate_profile(self):
		"""One profile per party, so nothing has two answers about the same party.

		The name is derived from the party, so the primary key stops this
		anyway. This runs first only to say which party is already taken,
		rather than leaving somebody with a database error to interpret. A new
		record must not exclude its own name here, because it shares that name
		with the record it is about to collide with.
		"""
		filters = {"party_doctype": self.party_doctype, "party": self.party}
		if not self.is_new():
			filters["name"] = ("!=", self.name)
		existing = frappe.db.get_value("UAE Peppol Party Profile", filters, "name")
		if existing:
			frappe.throw(
				_("{0} already has a profile.").format(self.party),
				title=_("Already has a profile"),
			)

	def reject_manual_verification(self):
		before = self.get_doc_before_save()
		was = (before.lookup_state if before else None) or "Not checked"
		if self.lookup_state == "Verified" and was != "Verified":
			if not self.flags.get("from_lookup"):
				frappe.throw(
					_("Only a lookup can record a party as verified."),
					title=_("Not evidence"),
				)
