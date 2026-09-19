"""Finding out what actually happened.

Two jobs. Asking a provider where a document has got to, and dealing with
the attempts that went out and never came back.

The second is the one that matters. An attempt whose claim ran out is not
evidence that the worker stopped or that the provider did not take the
document. It is evidence that we stopped hearing. So nothing here ever
retries one. It asks, and where it cannot ask it holds the work for a person
and says why.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

from uae_compliance.domain.connector import AspReceipt, Effect, Operation
from uae_compliance.services import outbox
from uae_compliance.services.freeze import SUBMISSION_DOCTYPE
from uae_compliance.services.outbox import LOG_DOCTYPE

# States where the answer is still outstanding, so it is worth asking again.
OUTSTANDING = ("Awaiting outcome", "Unknown", "Sending")


def reconcile_due(limit: int = 20) -> int:
	"""Scheduler entry. Ask about what is still outstanding.

	Bounded and indexed. A site with years of history must not read all of
	it to find the handful still waiting.
	"""
	recovered = recover_abandoned()
	asked = 0
	for name in _outstanding(limit):
		if ask_about(name):
			asked += 1
	return recovered + asked


def _outstanding(limit: int) -> list[str]:
	cutoff = add_to_date(now_datetime(), seconds=-60)
	rows = frappe.get_all(
		SUBMISSION_DOCTYPE,
		filters={"processing_state": ["in", OUTSTANDING], "modified": ["<", cutoff]},
		fields=["name"],
		order_by="modified asc",
		limit=limit,
	)
	return [row.name for row in rows]


def recover_abandoned() -> int:
	"""Attempts that went out and never came back.

	The submission is moved to Unknown and the attempt is marked abandoned.
	Neither is treated as a failure. Something may be sitting at the provider
	with our document in it, and the only safe next step is to ask.
	"""
	count = 0
	for attempt_id in outbox.abandoned():
		submission = frappe.db.get_value(LOG_DOCTYPE, attempt_id, "submission")
		frappe.db.set_value(
			LOG_DOCTYPE,
			attempt_id,
			{"state": "Abandoned", "error_class": "No answer came back"},
		)
		if submission:
			frappe.db.set_value(
				SUBMISSION_DOCTYPE,
				submission,
				{
					"processing_state": "Unknown",
					"asp_receipt": AspReceipt.UNKNOWN.value,
					"lease_owner": None,
					"lease_expires_at": None,
					"next_attempt_at": None,
					"attention_reason": "A request went out and nothing came back. Asking the provider.",
				},
			)
		count += 1
	return count


def ask_about(submission: str) -> bool:
	"""Ask the provider where this document has got to.

	Returns whether an answer was recorded. Not being able to ask is a
	normal outcome for a provider that offers no way to, and it leaves the
	work held rather than guessed at.
	"""
	from uae_compliance.connectors import registry as connectors
	from uae_compliance.connectors.transport import Transport
	from uae_compliance.services.sending import (
		_connection_and_adapter,
		_policy_for,
		_provider_reference,
	)

	try:
		connection, adapter = _connection_and_adapter(submission)
	except Exception as error:
		frappe.db.set_value(SUBMISSION_DOCTYPE, submission, "attention_reason", str(error)[:500])
		return False

	details = frappe.db.get_value(
		SUBMISSION_DOCTYPE, submission, ["company", "provider_id", "idempotency_key"], as_dict=True
	)

	operation = _how_to_ask(adapter, details.provider_id)
	if operation is None:
		frappe.db.set_value(
			SUBMISSION_DOCTYPE,
			submission,
			{
				"processing_state": "Attention required",
				"attention_reason": "This provider offers no way to find out what happened, so a person has to.",
			},
		)
		return False

	from uae_compliance.services.recorder import FrappeRecorder

	recorder = FrappeRecorder(submission, details.company, connection.connection_id)
	transport = Transport(_policy_for(connection), recorder)
	call = connectors.Call(
		operation=operation,
		connection=connection,
		provider_ids={"document_id": details.provider_id} if details.provider_id else {},
		idempotency_key=details.idempotency_key,
		correlation=submission,
	)

	try:
		outcome = adapter.perform(call, transport)
	except Exception as error:
		frappe.db.set_value(SUBMISSION_DOCTYPE, submission, "attention_reason", str(error)[:500])
		return False

	_record_answer(submission, outcome, _provider_reference(outcome))
	_settle_if_done(submission)
	return True


def _settle_if_done(submission: str):
	"""Mark it complete only once everything the route needs has arrived."""
	from uae_compliance.domain.connector import Acknowledgements, Evidence, Exchange, Reporting, Route

	row = frappe.db.get_value(
		SUBMISSION_DOCTYPE,
		submission,
		["asp_receipt", "exchange_state", "reporting_state", "evidence_state"],
		as_dict=True,
	)
	acks = Acknowledgements(
		asp_receipt=AspReceipt(row.asp_receipt),
		exchange=Exchange(row.exchange_state),
		reporting=Reporting(row.reporting_state),
		evidence=Evidence(row.evidence_state),
	)
	if acks.complete(Route()):
		frappe.db.set_value(
			SUBMISSION_DOCTYPE, submission, {"processing_state": "Complete", "next_attempt_at": None}
		)


def _how_to_ask(adapter, provider_id: str | None) -> Operation | None:
	"""Which operation can settle this, given what the provider offers.

	Knowing the provider's own reference means we can simply ask about it.
	Without one, only a provider that supports searching can help, and a
	provider that supports neither cannot be asked at all.
	"""
	declaration = adapter.descriptor
	if provider_id and declaration.supports(Operation.GET_STATUS):
		return Operation.GET_STATUS
	if declaration.supports(Operation.FIND_SUBMISSION) and declaration.can_search_by_key:
		return Operation.FIND_SUBMISSION
	return None


def _record_answer(submission: str, outcome, reference: str | None):
	"""Write down what the provider said, without letting it go backwards.

	A late answer about an older state must not overwrite a newer confirmed
	one. Where the two disagree, both are kept and the work is marked for a
	person rather than quietly resolved one way.
	"""
	from uae_compliance.domain.connector import Route

	current = frappe.db.get_value(
		SUBMISSION_DOCTYPE, submission, ["asp_receipt", "exchange_state", "reporting_state"], as_dict=True
	)
	acks = outcome.acknowledgements

	if current.asp_receipt == AspReceipt.RECEIVED.value and acks.asp_receipt is AspReceipt.NOT_SENT:
		# The provider now says it never had it, having previously said it
		# did. Both facts are kept and somebody looks at it.
		frappe.db.set_value(
			SUBMISSION_DOCTYPE,
			submission,
			{
				"processing_state": "Attention required",
				"attention_reason": "The provider's answer contradicts what it said before.",
			},
		)
		return

	values = {
		"asp_receipt": acks.asp_receipt.value,
		"exchange_state": acks.exchange.value,
		"reporting_state": acks.reporting.value,
		"evidence_state": acks.evidence.value,
		"attention_reason": None,
	}
	if reference:
		values["provider_id"] = reference

	if acks.complete(Route()):
		values["processing_state"] = "Complete"
		values["next_attempt_at"] = None
	elif outcome.effect is Effect.UNKNOWN:
		values["processing_state"] = "Unknown"
	else:
		values["processing_state"] = "Awaiting outcome"

	frappe.db.set_value(SUBMISSION_DOCTYPE, submission, values)
