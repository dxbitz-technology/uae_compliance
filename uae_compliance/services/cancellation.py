"""Stopping something, and correcting something that has gone.

The distinction that runs through this file: cancelling in ERPNext and
cancelling at the other end are not the same act. ERPNext cancelling
succeeded tells us nothing about a document that has already left, so
nothing here ever marks a remote document cancelled because a local one was.

And no attempts having been made is not proof that nothing was issued. It is
proof that we made no attempts. Where that distinction has teeth is the
unknown outcome, where something may have arrived and we cannot say, and
that case is held rather than guessed either way.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from uae_compliance.services.freeze import SUBMISSION_DOCTYPE
from uae_compliance.services.outbox import LOG_DOCTYPE

# Nothing has gone out and nobody is holding it, so the intent can be
# stopped and the invoice cancelled underneath it.
STOPPABLE = ("Awaiting review", "Ready", "Retry scheduled", "Stopped")

# Something is in flight or we do not know. Cancelling now would leave the
# local record saying one thing and the provider holding another.
IN_FLIGHT = ("Sending", "Awaiting outcome", "Unknown")


def before_invoice_cancel(invoice, method=None):
	"""Hook. Decides whether this invoice may be cancelled at all.

	Runs before the cancellation commits, so refusing here leaves the
	invoice exactly as it was.
	"""
	for row in _submissions_of(invoice.name):
		_check(row)


def _submissions_of(invoice_name: str):
	return frappe.get_all(
		SUBMISSION_DOCTYPE,
		filters={"control": invoice_name},
		fields=["name", "processing_state", "asp_receipt", "exchange_state", "reporting_state", "attempts"],
	)


def _check(row):
	if row.processing_state in ("Complete", "Superseded"):
		frappe.throw(
			_("This invoice has already been sent and settled. Issue a credit note instead."),
			title=_("Already sent"),
		)

	if row.processing_state in IN_FLIGHT:
		frappe.throw(
			_(
				"This invoice is with the provider and we are waiting to hear. It cannot be cancelled until we know what happened."
			),
			title=_("Still in flight"),
		)

	if _pending_attempt(row.name):
		frappe.throw(
			_(
				"A request went out for this invoice and has not come back. It has to be reconciled before anything else."
			),
			title=_("Outcome unknown"),
		)

	if (
		row.asp_receipt in ("Received",)
		or row.exchange_state == "Delivered"
		or row.reporting_state == "Accepted"
	):
		frappe.throw(
			_("This invoice has reached the other side. Issue a credit note instead of cancelling it."),
			title=_("Already delivered"),
		)

	if row.processing_state not in STOPPABLE:
		frappe.throw(
			_("This invoice cannot be cancelled while its submission is {0}.").format(row.processing_state)
		)

	_stop(row.name)


def _pending_attempt(submission: str) -> bool:
	"""Whether a request went out for this and never came back."""
	return bool(frappe.db.exists(LOG_DOCTYPE, {"submission": submission, "state": "Pending"}))


def _stop(submission: str):
	"""Take away the intent, keep everything else.

	The snapshot, the artifacts and the history stay exactly as they are.
	What is removed is only the app's intention to send, which is the one
	thing that has to go before the invoice underneath it does.
	"""
	frappe.db.set_value(
		SUBMISSION_DOCTYPE,
		submission,
		{
			"processing_state": "Stopped",
			"next_attempt_at": None,
			"lease_owner": None,
			"lease_expires_at": None,
			"attention_reason": "The invoice was cancelled before anything was sent.",
		},
	)


@frappe.whitelist()
def correct(submission: str, reason: str) -> str:
	"""Make a new revision to replace one the provider would not take.

	A correction is not a retry. A retry sends the same bytes again because
	nothing about the document was wrong. A correction says the document was
	wrong, so it gets a new revision, points back at the one it replaces,
	and needs approving on its own.
	"""
	old = frappe.get_doc(SUBMISSION_DOCTYPE, submission)
	old.check_permission("write")
	if not reason:
		frappe.throw(_("A correction has to say what was wrong."))
	if old.processing_state in IN_FLIGHT:
		frappe.throw(_("We are still waiting to hear about this one. Correcting it now could send two."))
	if _pending_attempt(submission):
		frappe.throw(_("A request for this has not come back yet. It has to be reconciled first."))
	if old.exchange_state == "Delivered" or old.reporting_state == "Accepted":
		frappe.throw(_("This has already reached the other side. A credit note is the way to change it."))

	invoice_name = frappe.db.get_value("UAE Peppol Invoice", old.control, "sales_invoice")
	invoice = frappe.get_doc("Sales Invoice", invoice_name)

	from uae_compliance.domain.findings import Level
	from uae_compliance.services import validation
	from uae_compliance.services.freeze import create_submission

	result = validation.check(invoice, Level.FULL)
	if result.errors:
		frappe.throw(_("{0} details still need attention.").format(len(result.errors)))

	from uae_compliance.erpnext.extract import extract

	document, _findings = extract(invoice)
	new_name = create_submission(invoice, old.control, document, result)

	frappe.db.set_value(SUBMISSION_DOCTYPE, new_name, "predecessor", submission, update_modified=False)
	frappe.db.set_value(
		SUBMISSION_DOCTYPE,
		submission,
		{"processing_state": "Superseded", "attention_reason": reason, "next_attempt_at": None},
	)
	return new_name


def on_invoice_cancel(invoice, method=None):
	"""Hook. Says the invoice was cancelled, and claims nothing more.

	Whether a document that already left is cancelled at the other end is
	the provider's answer, not ours, and it never comes from an ERP
	cancellation succeeding.
	"""
	frappe.db.set_value(
		"UAE Peppol Invoice",
		{"sales_invoice": invoice.name},
		{"readiness": "Out of scope", "scope_reason": "The invoice was cancelled."},
	)
