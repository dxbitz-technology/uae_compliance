"""How a company's tax accounts map to the official categories.

Company aware, because two companies on the same site can treat the same
account differently. A mapping that could match twice is refused when it is
saved rather than picked between later: choosing the first match would make
the tax on an invoice depend on the order rows happen to be in.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class UAEPeppolTaxCategory(Document):
	def validate(self):
		self.require_something_to_match_on()
		self.reject_an_ambiguous_mapping()
		self.require_reason_for_exempt()

	def require_something_to_match_on(self):
		if not self.account_head and not self.item_tax_template:
			frappe.throw(
				_("A mapping needs a tax account or an item tax template to match on."),
				title=_("Nothing to match"),
			)

	def reject_an_ambiguous_mapping(self):
		"""Two rows that could both match the same invoice line are refused."""
		# An unset link is null in the database, not an empty string, so each
		# side has to be matched for whichever it actually is.
		filters = {"company": self.company, "name": ("!=", self.name or "")}
		for field in ("account_head", "item_tax_template"):
			value = self.get(field)
			filters[field] = value if value else ("in", ["", None])
		twin = frappe.db.get_value("UAE Peppol Tax Category", filters, "name")
		if twin:
			frappe.throw(
				_("{0} already maps this combination for {1}.").format(twin, self.company),
				title=_("Two mappings would match"),
			)

	def require_reason_for_exempt(self):
		"""An exempt or out of scope line has to say why, because the rules ask."""
		if self.category in ("E", "O") and not (self.reason_code or self.reason):
			frappe.throw(
				_("An exempt or out of scope mapping needs a reason."),
				title=_("Reason needed"),
			)
