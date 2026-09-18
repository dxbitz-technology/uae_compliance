"""What happens when somebody submits an invoice.

Company policy decides, and only company policy. In Preparation the findings
are advice and the invoice still submits, because the point of Preparation is
to see what would be wrong without being stopped. In Live an invoice with a
blocking finding does not submit.

A compliance gap never stops a draft being saved. That is invariant I03 and
it is the reason this runs on submit and nowhere earlier.
"""

from __future__ import annotations

import frappe
from frappe import _

from uae_compliance.domain.findings import Level
from uae_compliance.domain.scope import Enforcement, Mode, enforcement_for
from uae_compliance.services import validation
from uae_compliance.services.working import mode_for


def before_invoice_submit(invoice, method=None):
	"""Hook. Runs a fresh full check on the values being submitted.

	Fresh on purpose. A result the browser is holding was taken against
	whatever was on screen at the time, and this is the last point where the
	authoritative values can be read.
	"""
	mode = mode_for(invoice.company)
	if mode is Mode.OFF:
		return

	result = validation.check(invoice, Level.FULL)
	errors = result.errors
	if not errors:
		return

	if enforcement_for(mode) is Enforcement.BLOCKING:
		frappe.throw(_summary(errors), title=_("Cannot submit yet"))
	else:
		frappe.msgprint(_summary(errors), title=_("Would not pass in Live"), indicator="orange")


def after_invoice_submit(invoice, method=None):
	"""Hook. Records what the submitted invoice was checked against."""
	mode = mode_for(invoice.company)
	if mode is Mode.OFF:
		return
	result = validation.check(invoice, Level.FULL)
	validation.record_result(invoice.name, result)


def _summary(errors) -> str:
	"""One message, not one per rule.

	A single missing value fails several rules, and listing each one buries
	the thing somebody has to go and fix.
	"""
	lines = [_("{0} details need attention before this invoice can be sent.").format(len(errors))]
	for finding in errors[:10]:
		where = f" ({finding.path})" if finding.path else ""
		lines.append(f"<br>{frappe.utils.escape_html(finding.message)}{frappe.utils.escape_html(where)}")
		if finding.repair:
			lines.append(f" {frappe.utils.escape_html(finding.repair)}")
	if len(errors) > 10:
		lines.append(_("<br>and {0} more.").format(len(errors) - 10))
	return "".join(lines)
