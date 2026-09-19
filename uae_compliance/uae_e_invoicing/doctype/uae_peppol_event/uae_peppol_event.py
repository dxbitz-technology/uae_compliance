"""Something a provider told us, kept exactly as it arrived.

Nothing writes one of these yet. Status comes back by asking the provider
and arrived documents come back by reading its inbox, so there is no
receiver for a pushed event anywhere in the app. The record and its rules
are reserved for the real provider phase, where webhooks arrive; acceptance
case A16 stays Not run until then. If that phase never wires one, this
record goes with it.

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
