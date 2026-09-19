"""One durable record of one attempt to reach a provider.

Written before the request goes out and never rewritten afterwards except to
record what came back. That order matters: if the process dies between the
write and the answer, the record is still there saying a request may have
reached them, which is the only thing that stops a blind resend later.

Append only. A history somebody can tidy up is not a history.
"""

import frappe
from frappe import _
from frappe.model.document import Document

# Everything about the attempt itself. Only the result fields may be filled
# in afterwards, and only once.
FIXED_FIELDS = (
	"attempt_id",
	"submission",
	"company",
	"connection",
	"operation",
	"started_at",
	"request_digest",
	"fencing_token",
	"worker",
)


class UAEPeppolTransmissionLog(Document):
	def validate(self):
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if not before:
			return
		for field in FIXED_FIELDS:
			if self.get(field) != before.get(field):
				frappe.throw(_("An attempt record cannot be changed after it is written."))
		if before.state == "Finished" and self.state != "Finished":
			frappe.throw(_("An attempt that finished cannot be reopened."))

	def on_trash(self):
		frappe.throw(_("Attempt records are kept."))
