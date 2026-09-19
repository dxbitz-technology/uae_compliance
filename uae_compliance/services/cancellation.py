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

from uae_compliance.domain.recovery import (
	CORRECTABLE,
	IN_FLIGHT,
	STOPPABLE,
	WITH_THE_PROVIDER,
	why_it_may_be_out_there,
)
from uae_compliance.services import outbox
from uae_compliance.services.freeze import SUBMISSION_DOCTYPE
from uae_compliance.services.outbox import LOG_DOCTYPE
from uae_compliance.services.working import WORKING_DOCTYPE


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
	if row.processing_state == "Complete":
		frappe.throw(
			_("This invoice has already been sent and settled. Issue a credit note instead."),
			title=_("Already sent"),
		)

	if row.processing_state == "Superseded":
		# Superseded says a revision was replaced. It says nothing about
		# whether that revision ever left, and treating it as settled made
		# correcting an invoice the thing that stopped it ever being
		# cancelled. It is judged below on the same evidence as any other:
		# what the provider received, what was delivered, what was
		# reported, and whether a request is still out.
		_check_it_never_left(row)
		return

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
		row.asp_receipt in WITH_THE_PROVIDER
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


def _check_it_never_left(row):
	"""Whether a replaced revision is still in the way.

	One that went nowhere is not. One the provider took, or that is still
	out, is, and a credit note is then the way to change it.
	"""
	if _pending_attempt(row.name):
		frappe.throw(
			_(
				"A request went out for an earlier version of this invoice and has not come back. It has to be reconciled before anything else."
			),
			title=_("Outcome unknown"),
		)

	if (
		row.asp_receipt in WITH_THE_PROVIDER
		or row.exchange_state == "Delivered"
		or row.reporting_state == "Accepted"
	):
		frappe.throw(
			_(
				"An earlier version of this invoice reached the other side. Issue a credit note instead of cancelling it."
			),
			title=_("Already delivered"),
		)


def _pending_attempt(submission: str) -> bool:
	"""Whether a request went out for this and never came back."""
	return bool(frappe.db.exists(LOG_DOCTYPE, {"submission": submission, "state": "Pending"}))


def _stop(submission: str):
	"""Take away the intent, keep everything else.

	The snapshot, the artifacts and the history stay exactly as they are.
	What is removed is only the app's intention to send, which is the one
	thing that has to go before the invoice underneath it does.

	One update, and it has to bite. Reading the state and then writing it
	leaves a gap, and a worker that claims the submission inside that gap
	sends an invoice whose local record then says it was stopped.
	"""
	_take_out_of_reach(
		submission,
		"Stopped",
		"The invoice was cancelled before anything was sent.",
		STOPPABLE,
		_("A worker picked this up while it was being cancelled. Find out what happened to it first."),
	)


def _take_out_of_reach(submission: str, state: str, reason: str, permitted, refusal: str):
	"""Move a submission somewhere no worker can claim it, or refuse.

	The where clause carries the whole test, so nobody can claim the row
	between the check and the write. The fencing token goes up as well, which
	does two jobs: the update always changes something, so the row count is a
	real answer, and any worker still holding the old token is stopped from
	writing a result over the top of this.
	"""
	if frappe.db.get_value(SUBMISSION_DOCTYPE, submission, "processing_state") == state:
		# Already where we are trying to put it. Nothing to take away, and
		# nothing can claim it from there, so there is nothing to race for.
		return

	states = ", ".join(f"'{name}'" for name in permitted if name != state)
	frappe.db.sql(
		f"""
		update `tab{SUBMISSION_DOCTYPE}`
		set processing_state = %(state)s,
			attention_reason = %(reason)s,
			next_attempt_at = null,
			lease_owner = null,
			lease_expires_at = null,
			fencing_token = fencing_token + 1,
			modified = %(now)s
		where name = %(name)s
			and processing_state in ({states})
			and (lease_expires_at is null or lease_expires_at < %(now)s)
		""",
		{"state": state, "reason": reason, "now": now_datetime(), "name": submission},
	)
	took = outbox.changed_rows()
	frappe.clear_document_cache(SUBMISSION_DOCTYPE, submission)
	if not took:
		frappe.throw(refusal, title=_("Somebody else has this"))


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

	out_there = why_it_may_be_out_there(
		old.processing_state,
		old.asp_receipt,
		old.exchange_state,
		old.reporting_state,
		pending_attempt=_pending_attempt(submission),
		lease_live=outbox.lease_held(submission),
	)
	if out_there:
		frappe.throw(
			_("This cannot be corrected because {0}. A credit note is the way to change it.").format(
				out_there
			),
			title=_("Already gone"),
		)

	# Lock the control row the way freezing does, and in the same order. The
	# revision number is read from it, and two corrections reading the same
	# highest revision would build two documents claiming to be the same one.
	frappe.db.sql(f"select name from `tab{WORKING_DOCTYPE}` where name = %s for update", (old.control,))

	# Out of reach before anything is built. If a worker has claimed it since
	# the read above, this refuses and no second revision exists to be sent.
	# Everything below can still throw, and that rolls this back with it, so
	# a correction that fails leaves the old one exactly as it was.
	_take_out_of_reach(
		submission,
		"Superseded",
		reason,
		CORRECTABLE,
		_("A worker picked this up while it was being corrected. Find out what happened to it first."),
	)

	invoice_name = frappe.db.get_value(WORKING_DOCTYPE, old.control, "sales_invoice")
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
