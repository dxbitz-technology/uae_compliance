"""Taking approved work and actually sending it.

The order here is the whole point and it is not negotiable.

Claim the work, write down that an attempt is starting, and commit. Only
then make the request, holding no database lock while it is in flight.
Then, in a new transaction, write down what came back, checking first that
a newer worker has not been and gone in the meantime.

What the provider said is never interpreted here. The adapter turns it into
the contract's own words and this file reads those. A provider status code
must not reach this far, or every new provider would mean new branches
scattered through the app.
"""

from __future__ import annotations

import random

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime
from frappe.utils.password import get_decrypted_password

from uae_compliance.connectors import registry as connectors
from uae_compliance.connectors.transport import Policy, Transport, policy_for, safe_traceback
from uae_compliance.domain.connector import Advice, AspReceipt, Effect, Environment, Operation, Route, advise
from uae_compliance.services import outbox
from uae_compliance.services.freeze import SUBMISSION_DOCTYPE
from uae_compliance.services.recorder import FrappeRecorder

ASP_DOCTYPE = "UAE Peppol ASP"
CREDENTIAL_DOCTYPE = "UAE Peppol ASP Credential"
SETTINGS = "UAE Peppol Settings"


class MissingBytes(Exception):
	"""What was approved cannot be found, so nothing may be sent."""


def send_due(limit: int = 20) -> int:
	"""Scheduler entry. Take what is due and try each one."""
	sent = 0
	for name in outbox.due(limit):
		if send_one(name):
			sent += 1
	return sent


def send_one(submission: str) -> bool:
	"""One submission, all the way out and back.

	Returns whether an attempt was actually made. Not getting the claim is a
	normal answer, not a failure.
	"""
	claim = outbox.claim(submission)
	if not claim:
		return False

	token = claim["token"]
	try:
		connection, adapter = _connection_and_adapter(submission)
	except Exception as error:
		outbox.release(submission, "Attention required", _plainly(error, _("reach the provider")))
		frappe.db.commit()
		return False

	from uae_compliance.services.deployment import may_send

	allowed, why = may_send(connection.environment.value)
	if not allowed:
		outbox.release(submission, "Stopped", why)
		frappe.db.commit()
		return False

	try:
		request = _business_request(submission)
	except (MissingBytes, ValueError) as error:
		# Nothing has gone out and nothing will. Approving something whose
		# bytes are gone is not the same as sending it, so this stops rather
		# than trying.
		outbox.release(submission, "Attention required", str(error))
		frappe.db.commit()
		return False

	attempt = outbox.start_attempt(submission, Operation.SUBMIT.value, token, request.digest)

	# Committed before the request. If this process dies in the next line,
	# the attempt record is still there saying something may have gone out.
	frappe.db.commit()

	details = frappe.db.get_value(
		SUBMISSION_DOCTYPE, submission, ["company", "idempotency_key"], as_dict=True
	)
	recorder = FrappeRecorder(submission, details.company, connection.connection_id, token)
	transport = Transport(_policy_for(connection), recorder)

	call = connectors.Call(
		operation=Operation.SUBMIT,
		connection=connection,
		request=request,
		document=_canonical_of(submission),
		idempotency_key=details.idempotency_key,
		correlation=submission,
	)

	try:
		outcome = adapter.perform(call, transport)
	except Exception as error:
		# The request may or may not have arrived. Nothing here assumes it
		# did not, because assuming that is how the same invoice goes twice.
		_record_unknown(submission, attempt, token, _plainly(error, _("send this document")))
		frappe.db.commit()
		return True

	_apply(submission, attempt, token, outcome, adapter)
	frappe.db.commit()
	return True


def _connection_and_adapter_for(asp, operation: Operation):
	"""Build the connection for one provider record and pick its adapter.

	Shared, because receiving needs exactly the same thing as sending and
	two copies of credential handling is one too many.
	"""
	if not asp.enabled:
		raise ValueError(f"The connection {asp.label} is switched off.")

	credentials = {
		row.credential_key: get_decrypted_password(
			CREDENTIAL_DOCTYPE, row.name, "secret", raise_exception=False
		)
		for row in asp.credentials or []
	}
	connection = connectors.Connection(
		provider_key=asp.provider_key,
		connection_id=asp.name,
		environment=Environment(asp.environment),
		base_url=asp.base_url,
		credentials={key: value for key, value in credentials.items() if value},
	)
	adapter = connectors.installed().for_connection(connection, operation)
	return connection, adapter


def _connection_and_adapter(submission: str):
	name = frappe.db.get_value(SUBMISSION_DOCTYPE, submission, "connection")
	if not name:
		raise ValueError("This submission is not bound to a provider connection.")

	asp = frappe.get_doc(ASP_DOCTYPE, name)
	# The shared builder checks the operation and the environment together.
	# An adapter that only serves a simulator must not reach a production
	# connection even where it can technically do the operation.
	connection, adapter = _connection_and_adapter_for(asp, Operation.SUBMIT)

	# A connection that has carried work is settled, and this marks it so.
	if not asp.has_been_used:
		frappe.db.set_value(ASP_DOCTYPE, asp.name, "has_been_used", 1, update_modified=False)
	return connection, adapter


def _policy_for(connection) -> Policy:
	"""The transport policy this connection runs under.

	The rule itself lives with the transport, because that is what enforces
	it and a second copy here would be a second thing to keep right.
	"""
	return policy_for(connection.environment, connection.base_url)


def _business_request(submission: str) -> connectors.BusinessRequest:
	"""The frozen bytes, read back and checked against what was approved.

	A worker may wrap these in an authentication envelope. It may not build
	them again, so the digest is checked rather than trusted.
	"""
	import json

	row = frappe.db.get_value(
		SUBMISSION_DOCTYPE, submission, ["evidence_manifest", "payload_hash"], as_dict=True
	)
	manifest = json.loads(row.evidence_manifest or "[]")
	entry = next((item for item in manifest if item["kind"] == "reference-xml"), None)
	if not entry:
		raise MissingBytes("The document to send was never stored.")

	# A record of a file is not a file. Checking rather than assuming,
	# because the alternative is a worker falling over on a missing path and
	# the invoice quietly never going anywhere.
	try:
		content = frappe.get_doc("File", entry["file"]).get_content()
	except FileNotFoundError as error:
		raise MissingBytes("The stored document is recorded but its file is gone.") from error

	if isinstance(content, str):
		content = content.encode("utf-8")
	return connectors.BusinessRequest(media_type="application/xml", body=content, digest=row.payload_hash)


def _canonical_of(submission: str) -> dict | None:
	"""The canonical document, for an adapter whose provider takes its own format."""
	import json

	manifest = json.loads(frappe.db.get_value(SUBMISSION_DOCTYPE, submission, "evidence_manifest") or "[]")
	entry = next((item for item in manifest if item["kind"] == "canonical"), None)
	if not entry:
		return None
	content = frappe.get_doc("File", entry["file"]).get_content()
	return json.loads(content)


def _record_unknown(submission: str, attempt: str, token: int, reason: str):
	"""Something went out and we cannot say what became of it."""
	outbox.finish_attempt(
		attempt, token, effect="Unknown", advice=Advice.RECONCILE_FIRST.value, error_class=reason[:140]
	)
	frappe.db.set_value(
		SUBMISSION_DOCTYPE,
		submission,
		{
			"processing_state": "Unknown",
			"asp_receipt": AspReceipt.UNKNOWN.value,
			"lease_owner": None,
			"lease_expires_at": None,
			"next_attempt_at": None,
			"attention_reason": f"The request went out and nothing came back. {reason}",
		},
	)


def _apply(submission: str, attempt: str, token: int, outcome, adapter):
	"""Write down what came back, and decide what happens next.

	The decision comes from the adapter's own declaration, not from the
	provider's answer alone. A provider that cannot settle an ambiguous send
	means the work waits for a person, whatever it said.
	"""
	final = advise(outcome, adapter.descriptor)
	acks = outcome.acknowledgements

	written = outbox.finish_attempt(
		attempt,
		token,
		transport_status=outcome.disposition.value,
		effect=outcome.effect.value,
		advice=final.value,
		error_class=outcome.provider_code,
		provider_id=_provider_reference(outcome),
		retry_after_seconds=outcome.retry_after_seconds,
	)
	if not written:
		# A newer claim has already been and gone. Its answer is about the
		# world as it is now and ours is not.
		return

	values = {
		"asp_receipt": acks.asp_receipt.value,
		"exchange_state": acks.exchange.value,
		"reporting_state": acks.reporting.value,
		"evidence_state": acks.evidence.value,
		"lease_owner": None,
		"lease_expires_at": None,
	}
	reference = _provider_reference(outcome)
	if reference:
		values["provider_id"] = reference
	values.update(_next_step(submission, outcome, final, acks))
	frappe.db.set_value(SUBMISSION_DOCTYPE, submission, values)


def _provider_reference(outcome) -> str | None:
	"""The provider's own name for the document, whatever it calls it.

	Adapters put it under the key their provider uses, so this looks for the
	usual ones rather than assuming a single name across every provider.
	"""
	for key in ("document_id", "submission", "id", "number"):
		if outcome.provider_ids.get(key):
			return str(outcome.provider_ids[key])
	return None


def _next_step(submission: str, outcome, advice: Advice, acks) -> dict:
	"""Where the work goes from here."""
	if advice is Advice.RECONCILE_FIRST or outcome.effect is Effect.UNKNOWN:
		return {
			"processing_state": "Unknown",
			"next_attempt_at": None,
			"attention_reason": "The outcome is not known. It has to be reconciled before anything else.",
		}

	if advice is Advice.HOLD_FOR_PERSON:
		return {
			"processing_state": "Attention required",
			"next_attempt_at": None,
			"attention_reason": "This provider cannot settle an ambiguous send, so it waits for a person.",
		}

	if advice is Advice.RETRY_SAME_PAYLOAD:
		return _schedule_retry(submission, outcome.retry_after_seconds)

	if advice is Advice.REFRESH_AUTHENTICATION:
		# The credentials are stale rather than the document being wrong, so
		# the same bytes go again once. The wait is short because nothing is
		# overloaded, something has simply expired.
		return _schedule_retry(submission, 5)

	# Do not retry. Either it is finished or it was refused on its merits.
	if acks.complete(Route()):
		return {"processing_state": "Complete", "next_attempt_at": None}
	if acks.asp_receipt is AspReceipt.REJECTED:
		return {
			"processing_state": "Attention required",
			"next_attempt_at": None,
			"attention_reason": "The provider would not take this document. It needs correcting.",
		}
	return {
		"processing_state": "Awaiting outcome",
		"next_attempt_at": None,
		"attention_reason": None,
	}


def _schedule_retry(submission: str, retry_after: int | None) -> dict:
	"""When to try again, within what the settings allow.

	A provider asking for a particular wait is obeyed even where it is
	longer than our own cap. Our cap is a guess about load; theirs is what
	they actually want.
	"""
	settings = frappe.get_cached_doc(SETTINGS)
	attempts = frappe.db.get_value(SUBMISSION_DOCTYPE, submission, "attempts") or 0

	if attempts >= (settings.max_attempts or 5):
		return {
			"processing_state": "Attention required",
			"next_attempt_at": None,
			"attention_reason": f"Tried {attempts} times without getting through.",
		}

	first = settings.first_delay_seconds or 30
	cap = settings.max_delay_seconds or 900
	delay = min(first * (2 ** max(attempts - 1, 0)), cap)
	# A little scatter, so a hundred invoices that failed together do not all
	# come back at the same second.
	delay = int(delay * (0.8 + random.random() * 0.4))
	if retry_after:
		delay = max(delay, int(retry_after))

	return {
		"processing_state": "Retry scheduled",
		"next_attempt_at": add_to_date(now_datetime(), seconds=delay),
		"attention_reason": None,
	}


def _plainly(error: Exception, doing: str) -> str:
	"""A sentence somebody can read, with the technical detail kept elsewhere.

	Raw exception text in a field a person reads is how a report ends up
	showing somebody an error number and a file path. The detail still
	matters, so it goes to the error log where it belongs.

	The text is built here rather than left to the framework, which renders
	the local variables of every frame when it is given no message. On this
	path that would be the authorization header, the decrypted provider
	secret and the invoice itself.
	"""
	frappe.log_error(title=f"UAE e-invoicing: {doing}", message=safe_traceback(error))
	return _("Could not {0}. The connection or the provider is not answering.").format(doing)
