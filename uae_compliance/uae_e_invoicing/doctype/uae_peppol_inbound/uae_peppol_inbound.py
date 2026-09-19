"""A document somebody sent us, kept as it arrived.

Nothing here becomes a purchase on its own. A supplier's invoice landing in
the inbox is a claim about what we owe, and claims get looked at. The record
holds what the document says, matched where it can be matched, and waits.

What arrived never changes. Only the note of what we decided about it does.
"""

import frappe
from frappe import _
from frappe.model.document import Document

# Everything the document itself said. If any of it could be edited, the
# record would stop being a copy of what was sent and become an opinion
# about it.
FIXED_FIELDS = (
	"connection",
	"environment",
	"provider_key",
	"supplier_name",
	"supplier_tax_id",
	"supplier_endpoint",
	"document_number",
	"document_uuid",
	"type_code",
	"issue_date",
	"order_reference",
	"currency",
	"tax_exclusive",
	"tax_total",
	"payable",
	"line_count",
	"payload_digest",
	"payload_file",
	"received_at",
)


class UAEPeppolInbound(Document):
	def validate(self):
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if not before:
			return
		for field in FIXED_FIELDS:
			if self.get(field) != before.get(field):
				frappe.throw(_("What arrived cannot be changed."))
		if before.purchase_invoice and self.purchase_invoice != before.purchase_invoice:
			frappe.throw(_("This has already been entered as {0}.").format(before.purchase_invoice))

	def on_trash(self):
		frappe.throw(_("Received documents are kept."))


# A document that has not been matched to a company yet belongs to nobody,
# and a company restriction cannot restrict a blank. Until a manager matches
# it, only a manager sees it. Both halves below are needed: the query
# condition covers lists and reports, the permission check covers opening
# one record, and the framework does not derive either from the other.

MANAGES_UNMATCHED = ("UAE Peppol Manager", "System Manager")


def _sees_unmatched(user: str | None) -> bool:
	roles = frappe.get_roles(user or frappe.session.user)
	return any(role in roles for role in MANAGES_UNMATCHED)


def get_permission_query_conditions(user=None, doctype=None) -> str:
	if _sees_unmatched(user):
		return ""
	return "`tabUAE Peppol Inbound`.`company` is not null and `tabUAE Peppol Inbound`.`company` != ''"


def has_permission(doc, ptype=None, user=None, debug=False) -> bool:
	if doc.get("company"):
		return True
	return _sees_unmatched(user)
