"""One working record per invoice.

It holds two different kinds of thing and keeps them apart. The details a
person supplies, which are the scenario flags and the credit note reason,
and the result of the last check, which the app writes and nobody edits.

The record is deliberately not submittable. Its states belong to the app and
have nothing to do with the invoice's own docstatus, and mirroring one onto
the other would give two answers to the same question.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from uae_compliance.domain.canonical import SCENARIO_FLAGS

# Written by a check, never by a person. A generic write through the API has
# to be stopped here as well as in the form, because the form is not the only
# way in.
RESULT_FIELDS = (
	"mode",
	"in_scope",
	"scope_reason",
	"readiness",
	"checked_at",
	"checked_level",
	"errors",
	"warnings",
	"source_fingerprint",
	"master_fingerprint",
	"findings",
	"latest_submission",
)

PARTY_FIELDS = (
	"beneficiary_name",
	"beneficiary_scheme",
	"beneficiary_value",
	"principal_name",
	"principal_scheme",
	"principal_value",
)

INPUT_FIELDS = ("credit_reason_code", "credit_reason", *SCENARIO_FLAGS, *PARTY_FIELDS)


class UAEPeppolInvoice(Document):
	def validate(self):
		self.keep_the_source_fixed()
		self.guard_result_fields()
		self.count_the_input_revision()

	def keep_the_source_fixed(self):
		"""The invoice this belongs to is settled when the record is made."""
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if before and before.sales_invoice != self.sales_invoice:
			frappe.throw(
				_("This record belongs to {0} and cannot be moved to another invoice.").format(
					before.sales_invoice
				)
			)

	def guard_result_fields(self):
		"""Nobody sets a check result by hand.

		Readiness is the one that matters. An invoice that says Ready locally
		without a check having passed would send on the strength of somebody
		typing it.
		"""
		if self.flags.from_check or self.is_new():
			return
		before = self.get_doc_before_save()
		if not before:
			return
		for field in RESULT_FIELDS:
			if self.get(field) != before.get(field):
				self.set(field, before.get(field))

	def count_the_input_revision(self):
		"""Count up when the supplied details change, and only then.

		A check writing its result must not move the revision, or every save
		would look to the browser like somebody else's edit.
		"""
		if self.is_new():
			self.input_revision = 0
			return
		before = self.get_doc_before_save()
		if not before:
			return
		if any(self.get(field) != before.get(field) for field in INPUT_FIELDS):
			self.input_revision = (before.input_revision or 0) + 1

	def scenario(self) -> dict:
		"""The flags as the canonical model wants them, every one stated."""
		return {flag: bool(self.get(flag)) for flag in SCENARIO_FLAGS}
