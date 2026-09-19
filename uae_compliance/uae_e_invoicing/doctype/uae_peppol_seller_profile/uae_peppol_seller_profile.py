"""Who the seller is, and which companies are bound to it.

A profile saves while its details are still missing. That is deliberate: a
company cannot be asked for its participant identifier before it has one, and
refusing the save would leave nowhere to record what is known so far.

Two things it will not allow. A company cannot be bound to two sellers, since
that would make it ambiguous which identity its invoices carry. And a claim
about the seller's own identity cannot be marked as verified by answering a
question; only a lookup does that.
"""

import frappe
from frappe import _
from frappe.model.document import Document

LOOKUP_ONLY_FIELDS = ("identity_state", "identity_checked_at", "identity_valid_until")


class UAEPeppolSellerProfile(Document):
	def validate(self):
		self.normalize_identity()
		self.reject_manual_verification()
		self.reject_identity_used_elsewhere()
		self.reject_company_bound_elsewhere()
		self.require_reason_for_live()

	def normalize_identity(self):
		"""Blanks stored as nothing, so two profiles with no identity yet
		never collide on an empty string."""
		for field in ("participant_scheme", "participant_value", "vat_number"):
			value = (self.get(field) or "").strip()
			self.set(field, value or None)

	def reject_identity_used_elsewhere(self):
		"""One participant identity, one profile.

		The network address is how the outside world names this seller, so
		two profiles answering to one identity would make every match a coin
		toss. The database enforces it too; this says which profile has it.
		A VAT number is deliberately not unique: group members share one.
		"""
		if not self.participant_value:
			return
		filters = {
			"participant_scheme": self.participant_scheme,
			"participant_value": self.participant_value,
		}
		if not self.is_new():
			filters["name"] = ("!=", self.name)
		holder = frappe.db.get_value("UAE Peppol Seller Profile", filters, "name")
		if holder:
			frappe.throw(
				_("The identity {0} {1} already belongs to the seller {2}.").format(
					self.participant_scheme or "", self.participant_value, holder
				),
				title=_("Identity already taken"),
			)

	def reject_manual_verification(self):
		"""Answering a question about yourself is not evidence."""
		before = self.get_doc_before_save()
		was = (before.identity_state if before else None) or "Not checked"
		if self.identity_state == "Verified" and was != "Verified":
			if not self.flags.get("from_lookup"):
				frappe.throw(
					_("Only a lookup can record an identity as verified."),
					title=_("Not evidence"),
				)

	def reject_company_bound_elsewhere(self):
		"""One company, one seller.

		The child table has a unique company, which the database enforces, but
		that gives an error nobody can act on. This says which profile has it.
		"""
		for row in self.companies or []:
			filters = {"company": row.company}
			if not self.is_new():
				filters["parent"] = ("!=", self.name)
			holder = frappe.db.get_value("UAE Peppol Seller Company", filters, "parent")
			if holder:
				frappe.throw(
					_("{0} already belongs to the seller {1}.").format(row.company, holder),
					title=_("Company already bound"),
				)

	def require_reason_for_live(self):
		"""Going live is a decision, so it needs a date to be effective from."""
		for row in self.companies or []:
			if row.mode == "Live" and not row.effective_from:
				frappe.throw(
					_("{0} is set to Live and needs a date it takes effect from.").format(row.company)
				)

	def mode_for(self, company: str) -> str:
		"""What this seller has switched on for one company. Unknown means off."""
		for row in self.companies or []:
			if row.company == company:
				return row.mode or "Off"
		return "Off"
