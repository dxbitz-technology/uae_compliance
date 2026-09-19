"""One frozen attempt at sending a document.

Everything business about it is settled when it is made and never changes
again. What the invoice said, what the masters said, the hash of both, the
connection it is bound to and the route it goes by. A later edit to the
invoice or to a master does not reach back into this record, which is the
whole point of it existing.

What does change is operational: where the work has got to, who has claimed
it, what the provider said. Those move through the services, not by anybody
editing the form.
"""

import frappe
from frappe import _
from frappe.model.document import Document

# Settled at freeze. If any of these could move, a submission would stop
# being evidence of what was actually sent.
FROZEN_FIELDS = (
	"control",
	"company",
	"revision",
	"document_number",
	"document_uuid",
	"type_code",
	"idempotency_key",
	"canonical_version",
	"canonical_hash",
	"payload_hash",
	"source_fingerprint",
	"master_fingerprint",
	"frozen_at",
	"ruleset_version",
	"serializer_version",
	"extraction_version",
	"connection",
	"environment",
	"config_revision",
	"route_scheme",
	"route_value",
)

# A state nothing may leave, because the work is finished or was replaced.
SETTLED_STATES = ("Complete", "Superseded")


class UAEPeppolSubmission(Document):
	def validate(self):
		self.keep_frozen_content_frozen()
		self.guard_approval()

	def keep_frozen_content_frozen(self):
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if not before:
			return
		for field in FROZEN_FIELDS:
			if self.get(field) != before.get(field):
				frappe.throw(
					_("{0} was settled when this submission was frozen and cannot change.").format(
						_(self.meta.get_label(field))
					)
				)

	def guard_approval(self):
		"""Approval belongs to what was approved, not to the record generally.

		An approval that stayed put while the content changed underneath it
		would let a different document go out under somebody's name.
		"""
		if not self.approved:
			return
		if self.approved_canonical_hash != self.canonical_hash:
			frappe.throw(_("The content changed after it was approved. It needs approving again."))
		if not self.approved_by or not self.approved_at:
			frappe.throw(_("An approval has to say who gave it and when."))

	def sendable(self) -> bool:
		"""Whether a worker may pick this up.

		Approved, with its bytes present, in a state that expects to move,
		and not already claimed by somebody whose claim has not run out.
		"""
		return bool(
			self.approved and self.payload_hash and self.processing_state in ("Ready", "Retry scheduled")
		)

	def on_trash(self):
		"""Evidence of something sent is not deleted.

		Not even by a manager through the desk. A document that went to a
		provider has a life outside this system and the record of it is the
		only thing tying the two together.
		"""
		if self.asp_receipt != "Not sent" or self.attempts:
			frappe.throw(_("This submission has been sent and its record is kept."))
