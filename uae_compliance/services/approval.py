"""Saying yes to a specific document, not to a record in general.

An approval names the exact content it agreed to. If anything about that
content changes afterwards the approval stops applying, because otherwise a
different document could go out under somebody's name.

Two ways a submission gets approved. A person looks at it and says yes, or
the company has been set up not to require review and the policy says yes on
the same immutable revision. The second is recorded as a policy approval so
nobody later reads an unreviewed document as a reviewed one.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from uae_compliance.services.freeze import SUBMISSION_DOCTYPE
from uae_compliance.services.working import SELLER_COMPANY_DOCTYPE, SELLER_DOCTYPE


@frappe.whitelist()
def approve(submission: str, expected_hash: str) -> dict:
	"""Approve one submission, naming the content being approved.

	The hash has to be the one the approver was looking at. If it has moved,
	they were looking at something else and the answer is no.
	"""
	doc = frappe.get_doc(SUBMISSION_DOCTYPE, submission)
	doc.check_permission("write")
	_approvable(doc)

	if expected_hash != doc.canonical_hash:
		frappe.throw(
			_("This changed since you looked at it. Read it again before approving."),
			title=_("Changed"),
		)

	return _record(doc, kind="Person", user=frappe.session.user)


def approve_by_policy(submission: str) -> dict | None:
	"""Approve because the company was set up not to require review.

	Only where a person has actually turned review off for that company.
	The default is that review is required, and a missing setting means the
	default.
	"""
	doc = frappe.get_doc(SUBMISSION_DOCTYPE, submission)
	if _review_required(doc.company):
		return None
	_approvable(doc)
	return _record(doc, kind="Policy", user="Administrator")


def _approvable(doc):
	"""Everything that has to be true before anybody can say yes."""
	if doc.approved:
		frappe.throw(_("This is already approved."))
	if doc.processing_state != "Awaiting review":
		frappe.throw(_("This is not waiting for review."))
	if not doc.payload_hash or doc.evidence_state != "Complete":
		# Approving something whose bytes are not down yet would approve an
		# intention rather than a document.
		frappe.throw(_("The document it would send is not fully stored yet."))
	if not doc.route_value:
		frappe.throw(_("There is nowhere to send this. The customer has no network address."))


def _record(doc, kind: str, user: str) -> dict:
	doc.approved = 1
	doc.approved_by = user
	doc.approved_at = now_datetime()
	doc.approved_canonical_hash = doc.canonical_hash
	doc.approval_kind = kind
	doc.processing_state = "Ready"
	doc.next_attempt_at = now_datetime()
	# This save is the guarded path the controller reserves these fields for.
	doc.flags.from_service = True
	doc.save(ignore_permissions=True)
	return {"approved": True, "kind": kind, "state": doc.processing_state}


def _review_required(company: str) -> bool:
	value = frappe.db.get_value(
		SELLER_COMPANY_DOCTYPE,
		{"company": company, "parenttype": SELLER_DOCTYPE},
		"review_required",
	)
	# Missing configuration means review is required. The safe answer is the
	# one that puts a person in the way.
	return True if value is None else bool(value)


@frappe.whitelist()
def hold(submission: str, reason: str) -> dict:
	"""Stop a submission that has not gone anywhere, and say why."""
	doc = frappe.get_doc(SUBMISSION_DOCTYPE, submission)
	doc.check_permission("write")
	if doc.asp_receipt != "Not sent" or doc.attempts:
		frappe.throw(_("This has already been sent. It cannot simply be stopped."))
	if not reason:
		frappe.throw(_("Stopping something has to say why."))
	doc.processing_state = "Stopped"
	doc.attention_reason = reason
	doc.next_attempt_at = None
	# This save is the guarded path the controller reserves these fields for.
	doc.flags.from_service = True
	doc.save(ignore_permissions=True)
	return {"state": doc.processing_state}
