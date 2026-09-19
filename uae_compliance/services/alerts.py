"""Telling somebody, once, when something needs attention.

One message a day carrying everything, rather than one per problem. A system
that sends an alert per polling attempt teaches people to ignore its alerts,
and then the one that mattered is ignored too.

Nothing is sent when there is nothing to say.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

MANAGER_ROLE = "UAE Peppol Manager"

# Long enough that ordinary work in progress is not reported as a problem.
QUIET_HOURS = 4


def daily_summary() -> dict:
	"""Scheduler entry. Count what needs a person and tell the managers."""
	counts = what_needs_attention()
	if not any(counts.values()):
		return counts
	_notify(counts)
	return counts


def what_needs_attention() -> dict:
	"""The counts worth waking somebody for.

	Deliberately short. Each one means a person has to do something, and
	anything the app will sort out by itself is left off.
	"""
	quiet = add_to_date(now_datetime(), hours=-QUIET_HOURS)
	return {
		"unknown": frappe.db.count("UAE Peppol Submission", {"processing_state": "Unknown"}),
		"needs_a_person": frappe.db.count(
			"UAE Peppol Submission", {"processing_state": "Attention required"}
		),
		"waiting_for_review": frappe.db.count(
			"UAE Peppol Submission", {"processing_state": "Awaiting review", "modified": ["<", quiet]}
		),
		"no_answer": frappe.db.count(
			"UAE Peppol Transmission Log", {"state": "Pending", "started_at": ["<", quiet]}
		),
		"evidence_missing": frappe.db.count(
			"UAE Peppol Submission", {"asp_receipt": "Received", "evidence_state": ["!=", "Complete"]}
		),
		"credentials_expiring": _credentials_expiring(),
		"paused": 1 if frappe.db.get_single_value("UAE Peppol Settings", "pause_outbound") else 0,
	}


def _credentials_expiring() -> int:
	"""Credentials that will stop working within the week.

	Worth knowing in advance, because finding out at the moment of sending
	means a queue of invoices waiting on somebody's password manager.
	"""
	soon = add_to_date(now_datetime(), days=7)
	return frappe.db.count("UAE Peppol ASP Credential", {"expires_on": ["between", [now_datetime(), soon]]})


LINES = {
	"unknown": "{0} sent with no clear outcome. They have to be reconciled before anything else.",
	"needs_a_person": "{0} cannot go further on their own.",
	"waiting_for_review": "{0} are frozen and waiting for somebody to approve them.",
	"no_answer": "{0} requests went out and never came back.",
	"evidence_missing": "{0} reached the provider without their evidence being kept.",
	"credentials_expiring": "{0} credentials expire within the week.",
	"paused": "Outbound work is paused.",
}


def _notify(counts: dict):
	message = _("UAE e-invoicing needs attention.")
	parts = []
	for key, count in counts.items():
		if not count:
			continue
		line = LINES[key]
		parts.append(_(line).format(count) if "{0}" in line else _(line))

	for user in _managers():
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"subject": message,
				"email_content": "<br>".join(parts),
				"document_type": "UAE Peppol Submission",
			}
		).insert(ignore_permissions=True)


def _managers() -> list[str]:
	return [
		row.parent
		for row in frappe.get_all(
			"Has Role",
			filters={"role": MANAGER_ROLE, "parenttype": "User"},
			fields=["parent"],
		)
		if frappe.db.get_value("User", row.parent, "enabled")
	]
