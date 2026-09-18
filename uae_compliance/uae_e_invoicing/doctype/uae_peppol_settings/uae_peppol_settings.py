"""One settings record per site.

It carries the operational switches and says which rules are installed. The
rule identifiers are set by the release and are read only here, because rules
are pinned in the repository and never fetched at runtime.

Nothing here decides whether a company is switched on. That is company by
company and lives with the seller binding, so a site wide setting can never
quietly switch on a company nobody configured.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class UAEPeppolSettings(Document):
	def validate(self):
		self.reject_unusable_retry_settings()

	def reject_unusable_retry_settings(self):
		"""Bounded means bounded. A setting that cannot work is refused."""
		if (self.max_attempts or 0) < 1:
			frappe.throw(_("There must be at least one attempt."))
		for field in ("first_delay_seconds", "max_delay_seconds", "poll_interval_seconds"):
			if (self.get(field) or 0) < 1:
				frappe.throw(_("{0} must be at least one second.").format(_(self.meta.get_label(field))))
		if (self.max_delay_seconds or 0) < (self.first_delay_seconds or 0):
			frappe.throw(_("The maximum delay cannot be shorter than the first delay."))
