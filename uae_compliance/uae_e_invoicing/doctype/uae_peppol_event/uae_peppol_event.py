"""Something a provider told us, kept exactly as it arrived.

The body is evidence and never changes. What may change is our note of
whether we have managed to do anything with it yet.

An event is not permitted to move a document until its signature has been
checked. A web address nobody has published is not authentication, and an
event that moves a status is worth forging.
"""

import frappe
from frappe import _
from frappe.model.document import Document

FIXED_FIELDS = (
	"connection",
	"environment",
	"event_key",
	"payload_digest",
	"payload_file",
	"received_at",
	"provider_time",
	"sequence",
	"signature_method",
	"signature_verified",
)


class UAEPeppolEvent(Document):
	def validate(self):
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if not before:
			return
		for field in FIXED_FIELDS:
			if self.get(field) != before.get(field):
				frappe.throw(_("What arrived cannot be changed afterwards."))

	def on_trash(self):
		frappe.throw(_("Events are kept."))
