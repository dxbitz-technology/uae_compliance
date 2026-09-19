"""The part of the simulator's service both test adapters use.

A real provider adapter would not import this. It exists because both test
adapters happen to talk to the same simulated service, and the one thing they
must not share is what they send. Signing in, reading a status code, and
turning a provider's words into ours are the same work either way. Building the
document is not, and each adapter does that itself.

Nothing in here decides anything from a provider code. The codes are carried so
an attempt can be explained later, and every decision comes from the normalized
fields above them.
"""

from __future__ import annotations

import json
from dataclasses import replace

from uae_compliance.connectors.registry import Call
from uae_compliance.connectors.transport import (
	BlockedAddress,
	PolicyError,
	Request,
	RequestTimedOut,
	Transport,
	TransportError,
	UntrustedHost,
)
from uae_compliance.domain.connector import (
	Acknowledgements,
	Adapter,
	Advice,
	ArtifactRef,
	AspReceipt,
	ContractError,
	Disposition,
	Effect,
	Evidence,
	Exchange,
	Operation,
	Outcome,
	Reporting,
	advise,
)
from uae_compliance.domain.findings import Finding, Severity, Stage

TOKEN_PATH = "/oauth/token"
INVOICES_PATH = "/invoices"
DOWNLOAD_PATH = "/documents/download"

# Our own code for a document the provider refused. The provider's code goes in
# the parameters, where it can be read and never branched on.
REJECTED_CODE = "PROVIDER_REJECTED"
REJECTED_REPAIR = "Correct the invoice and send a new revision."

# An operation that changes something at the provider. A failure part way
# through one of these leaves a question. The rest can simply be asked again.
CHANGING = frozenset({Operation.SUBMIT, Operation.WITHDRAW})

# The provider's own words for where a document has got to. Mapped, never used.
EXCHANGE_STATES = {
	"pending": Exchange.PENDING,
	"delivered": Exchange.DELIVERED,
	"rejected": Exchange.REJECTED,
}
REPORTING_STATES = {
	"pending": Reporting.PENDING,
	"accepted": Reporting.ACCEPTED,
	"rejected": Reporting.REJECTED,
}


def body_of(response) -> dict:
	try:
		value = json.loads(response.body.decode("utf-8"))
	except UnicodeDecodeError, ValueError:
		return {}
	return value if isinstance(value, dict) else {}


def sign_in(call: Call, transport: Transport, adapter: Adapter) -> Outcome:
	"""Get a token and keep it on the connection.

	This is the one operation that does not check for a token first, which is
	what stops the check from calling itself.
	"""
	connection = call.connection
	payload = json.dumps(
		{
			"client_id": connection.credentials.get("client_id", ""),
			"client_secret": connection.credentials.get("client_secret", ""),
		}
	).encode()
	response = transport.fetch(
		Request(
			operation=Operation.AUTHENTICATE,
			method="POST",
			url=connection.url(TOKEN_PATH),
			headers={"Content-Type": "application/json", "Content-Length": str(len(payload))},
			body=payload,
			secrets=connection.secrets(),
			label="token",
			correlation=call.correlation,
			connection=connection.connection_id,
		)
	)
	if response.status != 200:
		connection.session.clear()
		return Outcome(
			operation=Operation.AUTHENTICATE,
			disposition=Disposition.AUTHENTICATION_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.HOLD_FOR_PERSON,
			provider_code=str(response.status),
			diagnostic_ref=response.diagnostic_ref,
		)
	answer = body_of(response)
	connection.session.hold(answer.get("access_token", ""), answer.get("expires_in"))
	return Outcome(
		operation=Operation.AUTHENTICATE,
		disposition=Disposition.SUCCEEDED,
		effect=Effect.APPLIED,
		advice=Advice.DO_NOT_RETRY,
		diagnostic_ref=response.diagnostic_ref,
	)


def with_token(call: Call, transport: Transport, adapter: Adapter) -> Outcome | None:
	"""Make sure there is a usable token. Returns an outcome only when there is not."""
	if call.connection.session.valid():
		return None
	got = sign_in(call, transport, adapter)
	if got.disposition is not Disposition.SUCCEEDED:
		return replace(got, operation=call.operation, advice=Advice.REFRESH_AUTHENTICATION)
	return None


def headers_for(call: Call, media_type: str, length: int, key: str | None = None) -> dict:
	headers = {
		"Authorization": f"Bearer {call.connection.session.token}",
		"Content-Type": media_type,
		"Content-Length": str(length),
	}
	if key:
		headers["Idempotency-Key"] = key
	return headers


def failed(call: Call, adapter: Adapter, error: Exception) -> Outcome:
	"""What an exchange that never produced an answer means.

	The division that matters: a request refused before it left applied
	nothing, and a request that failed after the bytes went may have applied
	everything. Only the adapter knows which operation it was making, so only
	it can say.
	"""
	if isinstance(error, UntrustedHost | BlockedAddress | PolicyError):
		# Nothing left this machine. Somebody has to fix the connection.
		return Outcome(
			operation=call.operation,
			disposition=Disposition.TRANSPORT_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.HOLD_FOR_PERSON,
			provider_code=getattr(error, "code", None),
		)
	if isinstance(error, RequestTimedOut):
		return _unknown(call, adapter, Disposition.TIMED_OUT, getattr(error, "code", None))
	if call.operation in CHANGING:
		return _unknown(call, adapter, Disposition.TRANSPORT_FAILED, getattr(error, "code", None))
	# Reading something again costs nothing and changes nothing.
	return Outcome(
		operation=call.operation,
		disposition=Disposition.TRANSPORT_FAILED,
		effect=Effect.NOT_APPLIED,
		advice=Advice.RETRY_SAME_PAYLOAD,
		provider_code=getattr(error, "code", None),
	)


def _unknown(call: Call, adapter: Adapter, disposition: Disposition, code: str | None) -> Outcome:
	"""An outcome nobody can read off the wire, with the advice this provider earns.

	Held for a person unless the adapter has promised something that can settle
	it. The contract decides that, not this module.
	"""
	outcome = Outcome(
		operation=call.operation,
		disposition=disposition,
		effect=Effect.UNKNOWN,
		advice=Advice.HOLD_FOR_PERSON,
		acknowledgements=Acknowledgements(asp_receipt=AspReceipt.UNKNOWN),
		provider_code=code,
	)
	return replace(outcome, advice=advise(outcome, adapter))


def findings_from(payload: dict) -> tuple[Finding, ...]:
	"""Turn the provider's complaints into ours.

	Our code is the same for all of them, because what the app does about a
	refused document does not change with the provider's numbering. The
	provider's own code travels in the parameters so a person can look it up.
	"""
	found = []
	for row in payload.get("errors") or ():
		found.append(
			Finding(
				code=REJECTED_CODE,
				severity=Severity.ERROR,
				stage=Stage.PROVIDER_RESPONSE,
				message=str(row.get("message") or "The provider refused the document"),
				path=str(row.get("path") or "/"),
				repair=REJECTED_REPAIR,
				params={
					"provider_code": str(row.get("code") or ""),
					"provider_message": str(row.get("message") or ""),
				},
			)
		)
	return tuple(found)


def acknowledgements_from(payload: dict, *, received: bool, evidence: Evidence) -> Acknowledgements:
	"""The four dimensions, each read from its own field.

	Delivery and reporting come from separate fields and stay separate. One of
	them succeeding says nothing about the other, and collapsing them is how a
	document gets called complete having never been reported.
	"""
	return Acknowledgements(
		asp_receipt=AspReceipt.RECEIVED if received else AspReceipt.NOT_SENT,
		exchange=EXCHANGE_STATES.get(str(payload.get("c3_mls_status") or ""), Exchange.UNKNOWN),
		reporting=REPORTING_STATES.get(str(payload.get("c5_mls_status") or ""), Reporting.UNKNOWN),
		evidence=evidence,
	)


def artifacts_from(payload: dict) -> tuple[ArtifactRef, ...]:
	found = []
	for row in payload.get("artifacts") or ():
		found.append(
			ArtifactRef(
				kind=str(row.get("kind") or "receipt"),
				identifier=str(row.get("identifier") or ""),
				media_type=row.get("media_type"),
			)
		)
	return tuple(found)


def submit_outcome(call: Call, response, adapter: Adapter) -> Outcome:
	"""What the provider's answer to a send means."""
	payload = body_of(response)
	if response.status in (200, 201):
		return Outcome(
			operation=Operation.SUBMIT,
			disposition=Disposition.SUCCEEDED,
			effect=Effect.APPLIED,
			advice=Advice.DO_NOT_RETRY,
			acknowledgements=acknowledgements_from(payload, received=True, evidence=Evidence.PENDING),
			provider_ids=_ids(payload),
			artifacts=artifacts_from(payload),
			provider_code=str(response.status),
			diagnostic_ref=response.diagnostic_ref,
		)
	if response.status == 401:
		return Outcome(
			operation=Operation.SUBMIT,
			disposition=Disposition.AUTHENTICATION_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.REFRESH_AUTHENTICATION,
			provider_code=str(response.status),
			diagnostic_ref=response.diagnostic_ref,
		)
	if response.status == 429:
		return Outcome(
			operation=Operation.SUBMIT,
			disposition=Disposition.RATE_LIMITED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.RETRY_SAME_PAYLOAD,
			# The provider's own wait, not a local backoff. A shorter local cap
			# is not a reason to knock on the door again sooner.
			retry_after_seconds=response.retry_after_seconds() or 60,
			provider_code=str(response.status),
			diagnostic_ref=response.diagnostic_ref,
		)
	if response.status in (400, 422):
		return Outcome(
			operation=Operation.SUBMIT,
			disposition=Disposition.BUSINESS_REJECTED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.DO_NOT_RETRY,
			acknowledgements=Acknowledgements(asp_receipt=AspReceipt.REJECTED, evidence=Evidence.UNAVAILABLE),
			findings=findings_from(payload),
			provider_code=str(response.status),
			diagnostic_ref=response.diagnostic_ref,
		)
	# Anything else may or may not have landed. A 5xx after the bytes left is
	# exactly the case that must never be sent again on a guess.
	outcome = Outcome(
		operation=Operation.SUBMIT,
		disposition=Disposition.TRANSPORT_FAILED,
		effect=Effect.UNKNOWN,
		advice=Advice.HOLD_FOR_PERSON,
		acknowledgements=Acknowledgements(asp_receipt=AspReceipt.UNKNOWN),
		provider_code=str(response.status),
		diagnostic_ref=response.diagnostic_ref,
	)
	return replace(outcome, advice=advise(outcome, adapter))


def status_outcome(call: Call, response, adapter: Adapter, payload: dict | None = None) -> Outcome:
	"""What the provider said about a document.

	`payload` is there for a search, which answers with a list and hands in the
	one row it picked. The status code still comes from the response, because
	that is what says whether the answer can be believed at all.
	"""
	payload = body_of(response) if payload is None else payload
	if response.status == 401:
		return Outcome(
			operation=call.operation,
			disposition=Disposition.AUTHENTICATION_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.REFRESH_AUTHENTICATION,
			provider_code=str(response.status),
			diagnostic_ref=response.diagnostic_ref,
		)
	if response.status != 200:
		return Outcome(
			operation=call.operation,
			disposition=Disposition.TRANSPORT_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.RETRY_SAME_PAYLOAD,
			provider_code=str(response.status),
			diagnostic_ref=response.diagnostic_ref,
		)
	return Outcome(
		operation=call.operation,
		disposition=Disposition.SUCCEEDED,
		effect=Effect.APPLIED,
		advice=Advice.DO_NOT_RETRY,
		acknowledgements=acknowledgements_from(payload, received=True, evidence=Evidence.PENDING),
		provider_ids=_ids(payload),
		artifacts=artifacts_from(payload),
		findings=findings_from(payload),
		provider_code=str(response.status),
		diagnostic_ref=response.diagnostic_ref,
	)


def artifact_outcome(call: Call, response) -> Outcome:
	"""Fetching evidence. A missing artifact is its own problem and not a failed document."""
	if response.status == 200:
		# The bytes travel with the reference. Retrieval that works but hands
		# back nothing to keep is the same as retrieval that does not work.
		fetched = ()
		if call.artifact:
			fetched = (
				replace(
					call.artifact,
					media_type=response.headers.get("content-type") or call.artifact.media_type,
					sha256=None,
					body=response.body,
				),
			)
		return Outcome(
			operation=Operation.FETCH_ARTIFACT,
			disposition=Disposition.SUCCEEDED,
			effect=Effect.APPLIED,
			advice=Advice.DO_NOT_RETRY,
			acknowledgements=Acknowledgements(asp_receipt=AspReceipt.RECEIVED, evidence=Evidence.COMPLETE),
			artifacts=fetched,
			provider_code=str(response.status),
			diagnostic_ref=response.diagnostic_ref,
		)
	return Outcome(
		operation=Operation.FETCH_ARTIFACT,
		disposition=Disposition.TRANSPORT_FAILED,
		effect=Effect.NOT_APPLIED,
		# Ask for the file again. Never send the invoice again to get it.
		advice=Advice.RETRY_SAME_PAYLOAD,
		acknowledgements=Acknowledgements(asp_receipt=AspReceipt.RECEIVED, evidence=Evidence.UNAVAILABLE),
		provider_code=str(response.status),
		diagnostic_ref=response.diagnostic_ref,
	)


def require_declared(adapter: Adapter, operation: Operation) -> None:
	if not adapter.supports(operation):
		raise ContractError(f"{adapter.provider_key} does not support {operation.value}")


def _ids(payload: dict) -> dict:
	ids = {}
	if payload.get("id"):
		ids["document_id"] = str(payload["id"])
	if payload.get("number"):
		ids["number"] = str(payload["number"])
	return ids
