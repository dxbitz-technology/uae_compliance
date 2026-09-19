"""The Suntech Tax Compliance Agent, spoken through the contract.

The first real Access Point this app sends through. Three facts from its
published sandbox reference shape everything here, recorded with their
sources in docs/evidence/p10.

Submission is three requests, not one: reserve a slot in the organisation's
document library, put the XML bytes on the presigned storage URL the
reservation returns, then submit referencing the stored file. The storage
URL lives on a different host than the API, which this adapter declares so
the transport can allow that host without widening anything else.

There are no idempotency keys. What the platform promises instead is that
an invoice number is unique per organisation per issue year, and its own
guidance for a lost answer is to search for the number before ever posting
again. That is this app's reconcile-first rule word for word, so
find_submission is that search.

Statuses come back as four integers. They are translated here, once, into
the contract's independent dimensions, and the raw values ride along in
the provider code for the record. Nothing downstream branches on them.

A 201 on submission means accepted and queued, not validated: the platform
checks an uploaded XML asynchronously and a rule failure arrives later as a
status flip with the rule id in its message. The submit outcome therefore
reports receipt by the platform, and everything further comes from status.
"""

from __future__ import annotations

import json
from dataclasses import replace
from urllib.parse import urlencode

# These helpers are provider-neutral outcome grammar that happens to live
# beside the simulator: how an exchange that produced no answer is
# classified, and the shared finding code for a refused document. Reusing
# them keeps the recovery rules in one place.
from uae_compliance.connectors.adapters.simulation_api import (
	REJECTED_CODE,
	REJECTED_REPAIR,
	failed,
	require_declared,
)
from uae_compliance.connectors.registry import Call
from uae_compliance.connectors.transport import Request, Transport, TransportError
from uae_compliance.domain.connector import (
	Acknowledgements,
	Adapter,
	Advice,
	ArtifactRef,
	AspReceipt,
	ContractError,
	Disposition,
	Effect,
	Environment,
	Evidence,
	Exchange,
	Operation,
	Outcome,
	Reporting,
	advise,
)
from uae_compliance.domain.findings import Finding, Severity, Stage

TOKEN_PATH = "oauth/token/"
INVOICES_PATH = "invoices/"
DOCUMENTS_PATH = "documents/"
DOWNLOAD_PATH = "documents/download/"

XML_MEDIA_TYPE = "application/xml"

# Received documents, supplier side only. The self-billed types are
# receivables and belong to a later scope.
INBOUND_TYPES = "380,381,480,81"

# How far one inbound collection will walk. Each page is the caller's page
# size, so this bounds one run at a few hundred documents. A backlog past it
# is reported for a person rather than half-walked, because advancing the
# cursor past unread rows would lose them.
MAX_INBOUND_PAGES = 50

# The platform's own enumerations, kept only to translate (§14 of its
# reference). c3 is the receiving Access Point, c5 is the FTA.
_EXCHANGE = {
	0: Exchange.NOT_STARTED,
	1: Exchange.PENDING,
	2: Exchange.PENDING,
	3: Exchange.PENDING,
	4: Exchange.DELIVERED,
	5: Exchange.REJECTED,
	6: Exchange.REJECTED,
}
# 5, 6 and 7 are the withdraw states. A withdrawal is portal-driven and
# outside this app's flow, so it is not translated into an answer it is not.
_REPORTING = {
	0: Reporting.NOT_STARTED,
	1: Reporting.PENDING,
	2: Reporting.PENDING,
	3: Reporting.PENDING,
	4: Reporting.ACCEPTED,
	5: Reporting.UNKNOWN,
	6: Reporting.UNKNOWN,
	7: Reporting.UNKNOWN,
}

DECLARATION = Adapter(
	provider_key="suntech",
	label="Suntech Tax Compliance Agent",
	adapter_version="0.1.0",
	contract_version=1,
	environments=(Environment.SANDBOX, Environment.PRODUCTION),
	operations=frozenset(
		{
			Operation.AUTHENTICATE,
			Operation.SUBMIT,
			Operation.GET_STATUS,
			Operation.FIND_SUBMISSION,
			Operation.FETCH_ARTIFACT,
			Operation.FETCH_INBOUND,
		}
	),
	request_format="PINT AE XML, uploaded to the document library and submitted by path",
	authentication="OAuth2 client credentials",
	# No client-supplied idempotency keys in its v1. The uniqueness of the
	# invoice number per organisation per issue year is the platform's net,
	# and the search below is how an ambiguous send is settled.
	idempotency=None,
	can_search_by_key=True,
	event_authentication=None,
	events_carry_order=False,
	supports_artifacts=True,
	pagination="Cursor for lists; the after anchor with a 60 second settle window for polling",
	scenarios=(),
	# The document library hands back presigned storage URLs on this host.
	extra_trusted_hosts=(".amazonaws.com",),
)


class SuntechAdapter:
	descriptor = DECLARATION

	def perform(self, call: Call, transport: Transport) -> Outcome:
		require_declared(self.descriptor, call.operation)
		if call.operation is Operation.AUTHENTICATE:
			return _sign_in(call, transport)
		blocked = _with_token(call, transport)
		if blocked is not None:
			return blocked
		try:
			if call.operation is Operation.SUBMIT:
				return self._submit(call, transport)
			if call.operation is Operation.GET_STATUS:
				return self._status(call, transport)
			if call.operation is Operation.FIND_SUBMISSION:
				return self._find(call, transport)
			if call.operation is Operation.FETCH_ARTIFACT:
				return self._artifact(call, transport)
			return self._inbound(call, transport)
		except TransportError as error:
			return failed(call, self.descriptor, error)

	def _submit(self, call: Call, transport: Transport) -> Outcome:
		"""Reserve, upload, submit. Only the third call changes anything.

		A failure on the first two applied nothing: an orphan library slot is
		the worst they leave behind. Only the final POST can have created an
		invoice, so only its ambiguous answers are treated as unknown.
		"""
		if call.request is None:
			raise ContractError("this provider takes the reference XML and none was given")
		head = _head_of(call)

		reserved = transport.fetch(
			_request(
				call,
				Operation.SUBMIT,
				"POST",
				call.connection.url(DOCUMENTS_PATH),
				_json_body({"name": _slot_name(head, call), "extension": "xml"}),
				label="reserve document",
			)
		)
		if reserved.status != 201:
			return _refused(call, reserved, may_have_applied=False)
		slot = _body_of(reserved)
		upload_url = slot.get("upload_url") or ""
		path = slot.get("path") or ""
		if not upload_url or not path:
			return _refused(call, reserved, may_have_applied=False, code="reservation-incomplete")

		stored = transport.fetch(
			Request(
				operation=Operation.SUBMIT,
				method="PUT",
				url=upload_url,
				headers={
					"Content-Type": XML_MEDIA_TYPE,
					"Content-Length": str(len(call.request.body)),
				},
				body=call.request.body,
				secrets=call.connection.secrets(),
				label="upload document",
				correlation=call.correlation,
				connection=call.connection.connection_id,
			)
		)
		if stored.status not in (200, 201, 204):
			return _refused(call, stored, may_have_applied=False, code="upload-refused")

		submitted = transport.fetch(
			_request(
				call,
				Operation.SUBMIT,
				"POST",
				call.connection.url(INVOICES_PATH),
				_json_body(
					{
						"name": f"Invoice {head.get('number')}",
						"invoice_number": head.get("number"),
						"issue_date": head.get("issue_date"),
						"invoice_type_code": head.get("type_code"),
						"source_file_path": path,
					}
				),
				label="submit",
			)
		)
		if submitted.status == 201:
			answer = _body_of(submitted)
			return Outcome(
				operation=Operation.SUBMIT,
				disposition=Disposition.SUCCEEDED,
				effect=Effect.APPLIED,
				advice=Advice.DO_NOT_RETRY,
				acknowledgements=Acknowledgements(
					asp_receipt=AspReceipt.RECEIVED,
					exchange=Exchange.PENDING,
					reporting=Reporting.PENDING,
					evidence=Evidence.PENDING,
				),
				provider_ids={"document_id": str(answer.get("id") or "")},
				provider_code="201",
				diagnostic_ref=submitted.diagnostic_ref,
			)
		if submitted.status == 400 and "invoice_number" in _body_of(submitted):
			# The number is already taken for this issue year, which means an
			# earlier attempt reached them. Nothing to correct: settle it by
			# the documented search before anything else happens.
			outcome = Outcome(
				operation=Operation.SUBMIT,
				disposition=Disposition.UNKNOWN,
				effect=Effect.UNKNOWN,
				advice=Advice.HOLD_FOR_PERSON,
				acknowledgements=Acknowledgements(asp_receipt=AspReceipt.UNKNOWN),
				provider_code="duplicate-invoice-number",
				diagnostic_ref=submitted.diagnostic_ref,
			)
			return replace(outcome, advice=advise(outcome, self.descriptor))
		return _refused(call, submitted, may_have_applied=submitted.status >= 500)

	def _status(self, call: Call, transport: Transport) -> Outcome:
		identifier = call.provider_ids.get("document_id")
		if not identifier:
			raise ContractError("a status needs the identifier the provider gave us")
		response = transport.fetch(
			_request(
				call,
				Operation.GET_STATUS,
				"GET",
				call.connection.url(INVOICES_PATH) + f"{identifier}/",
				None,
				label="status",
			)
		)
		if response.status == 404:
			# The provider answered, and it has no such document for this
			# organisation. Saying so is the whole point of asking.
			return _nothing_there(call, response)
		if response.status != 200:
			return _refused(call, response, may_have_applied=False)
		return _status_outcome(call, _body_of(response), response)

	def _find(self, call: Call, transport: Transport) -> Outcome:
		"""The documented settle for a lost answer: search our own number."""
		number = call.provider_ids.get("invoice_number")
		if not number:
			raise ContractError("finding a submission here needs our invoice number to search for")
		listing = transport.fetch(
			_request(
				call,
				Operation.FIND_SUBMISSION,
				"GET",
				call.connection.url(INVOICES_PATH)
				+ "?"
				+ urlencode({"search": number, "direction": "1", "page_size": "50"}),
				None,
				label="find by number",
			)
		)
		if listing.status != 200:
			return _refused(call, listing, may_have_applied=False)
		rows = [
			row
			for row in _body_of(listing).get("results") or ()
			if str(row.get("invoice_number") or "") == str(number)
		]
		if not rows:
			return _nothing_there(call, listing)

		# Search matches loosely and rows are thin, so the newest exact match
		# is read back in full through its own endpoint.
		detail = transport.fetch(
			_request(
				call,
				Operation.FIND_SUBMISSION,
				"GET",
				call.connection.url(INVOICES_PATH) + f"{rows[0].get('id')}/",
				None,
				label="found, reading it back",
			)
		)
		if detail.status != 200:
			return _refused(call, detail, may_have_applied=False)
		return _status_outcome(call, _body_of(detail), detail)

	def _artifact(self, call: Call, transport: Transport) -> Outcome:
		"""Two calls: ask for a download URL, then fetch the bytes from it."""
		if call.artifact is None:
			raise ContractError("fetching an artifact needs the reference to fetch")
		issued = transport.fetch(
			_request(
				call,
				Operation.FETCH_ARTIFACT,
				"POST",
				call.connection.url(DOWNLOAD_PATH),
				_json_body({"s3_uri": call.artifact.identifier}),
				label="issue download",
			)
		)
		if issued.status != 201:
			return _refused(call, issued, may_have_applied=False)
		fetched = transport.fetch(
			Request(
				operation=Operation.FETCH_ARTIFACT,
				method="GET",
				url=_body_of(issued).get("download_url") or "",
				secrets=call.connection.secrets(),
				label="download",
				correlation=call.correlation,
				connection=call.connection.connection_id,
			)
		)
		if fetched.status != 200:
			return _refused(call, fetched, may_have_applied=False)
		return Outcome(
			operation=Operation.FETCH_ARTIFACT,
			disposition=Disposition.SUCCEEDED,
			effect=Effect.APPLIED,
			advice=Advice.DO_NOT_RETRY,
			artifacts=(replace(call.artifact, body=fetched.body, sha256=None),),
			diagnostic_ref=fetched.diagnostic_ref,
		)

	def _inbound(self, call: Call, transport: Transport) -> Outcome:
		"""Everything suppliers sent since the anchor, oldest first.

		The platform's anchor returns only rows created after the given id
		and at least a minute old, so a row being written can never be
		skipped past. The pages walk from newest back towards the anchor;
		they are all collected before anything is processed, so the anchor
		only ever moves past rows that are actually in hand.
		"""
		params = {
			"direction": "2",
			"invoice_type_code__in": INBOUND_TYPES,
			"page_size": str(call.page_size or 50),
		}
		if call.cursor:
			params["after"] = call.cursor
		url = call.connection.url(INVOICES_PATH) + "?" + urlencode(params)

		rows: list[dict] = []
		for _page in range(MAX_INBOUND_PAGES):
			listing = transport.fetch(
				_request(call, Operation.FETCH_INBOUND, "GET", url, None, label="inbox page")
			)
			if listing.status != 200:
				return _refused(call, listing, may_have_applied=False)
			body = _body_of(listing)
			rows.extend(body.get("results") or ())
			url = body.get("next")
			if not url:
				break
		else:
			# More pages than one run may walk. Advancing the anchor now
			# would step over rows nobody has read, so it stays where it is
			# and a person decides how to drain the backlog.
			return Outcome(
				operation=Operation.FETCH_INBOUND,
				disposition=Disposition.TRANSPORT_FAILED,
				effect=Effect.NOT_APPLIED,
				advice=Advice.HOLD_FOR_PERSON,
				event_cursor=call.cursor,
				provider_code="inbound-backlog-too-large",
			)

		documents: list[ArtifactRef] = []
		newest_processed = None
		for row in reversed(rows):
			path = row.get("invoice_xml_location_path")
			if not path:
				# Not settled yet. Stop before it: the anchor may only move
				# past rows whose bytes are in hand, and everything newer
				# comes back on the next poll.
				break
			body = self._download(call, transport, str(path))
			if body is None:
				break
			documents.append(
				ArtifactRef(
					kind="inbound",
					identifier=str(row.get("id") or ""),
					media_type=XML_MEDIA_TYPE,
					body=body,
				)
			)
			newest_processed = str(row.get("id") or "")

		return Outcome(
			operation=Operation.FETCH_INBOUND,
			disposition=Disposition.SUCCEEDED,
			effect=Effect.APPLIED,
			advice=Advice.DO_NOT_RETRY,
			artifacts=tuple(documents),
			# Unmoved when nothing landed, so an empty inbox never erases
			# the place marker.
			event_cursor=newest_processed or call.cursor,
		)

	def _download(self, call: Call, transport: Transport, s3_uri: str) -> bytes | None:
		issued = transport.fetch(
			_request(
				call,
				Operation.FETCH_INBOUND,
				"POST",
				call.connection.url(DOWNLOAD_PATH),
				_json_body({"s3_uri": s3_uri}),
				label="issue inbound download",
			)
		)
		if issued.status != 201:
			return None
		fetched = transport.fetch(
			Request(
				operation=Operation.FETCH_INBOUND,
				method="GET",
				url=_body_of(issued).get("download_url") or "",
				secrets=call.connection.secrets(),
				label="download inbound",
				correlation=call.correlation,
				connection=call.connection.connection_id,
			)
		)
		if fetched.status != 200:
			return None
		return fetched.body


def _sign_in(call: Call, transport: Transport) -> Outcome:
	"""Client credentials for a short-lived token, held on the connection.

	Form-encoded, because that is the shape the token endpoint takes. The
	refresh endpoint exists but is not used: a worker builds its connection
	fresh for each operation, and one grant per operation is simpler than
	persisting a rotating refresh token safely.
	"""
	connection = call.connection
	payload = urlencode(
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
			headers={
				"Content-Type": "application/x-www-form-urlencoded",
				"Content-Length": str(len(payload)),
			},
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
	answer = _body_of(response)
	connection.session.hold(answer.get("access_token", ""), answer.get("expires_in"))
	return Outcome(
		operation=Operation.AUTHENTICATE,
		disposition=Disposition.SUCCEEDED,
		effect=Effect.APPLIED,
		advice=Advice.DO_NOT_RETRY,
		diagnostic_ref=response.diagnostic_ref,
	)


def _with_token(call: Call, transport: Transport) -> Outcome | None:
	if call.connection.session.valid():
		return None
	got = _sign_in(call, transport)
	if got.disposition is not Disposition.SUCCEEDED:
		return replace(got, operation=call.operation, advice=Advice.REFRESH_AUTHENTICATION)
	return None


def _request(call: Call, operation: Operation, method: str, url: str, body: bytes | None, label: str):
	headers = {"Authorization": f"Bearer {call.connection.session.token}"}
	if body is not None:
		headers["Content-Type"] = "application/json"
		headers["Content-Length"] = str(len(body))
	return Request(
		operation=operation,
		method=method,
		url=url,
		headers=headers,
		body=body,
		secrets=call.connection.secrets(),
		label=label,
		correlation=call.correlation,
		connection=call.connection.connection_id,
	)


def _json_body(payload: dict) -> bytes:
	return json.dumps({k: v for k, v in payload.items() if v is not None}, sort_keys=True).encode()


def _body_of(response) -> dict:
	try:
		found = json.loads(response.body.decode("utf-8", "replace"))
	except ValueError:
		return {}
	return found if isinstance(found, dict) else {}


def _head_of(call: Call) -> dict:
	document = call.document or {}
	head = document.get("document") or {}
	if not head.get("number"):
		raise ContractError("the canonical document is needed for the submission envelope")
	return head


def _slot_name(head: dict, call: Call) -> str:
	"""A library filename the platform accepts, from our own identifiers.

	Letters, digits and a small set of punctuation, starting alphanumeric.
	The revision-bearing correlation makes a corrected revision its own
	file rather than a quiet overwrite of the first one's slot.
	"""
	raw = f"{head.get('number')}-{call.correlation or 'r0'}"
	safe = "".join(ch if ch.isalnum() or ch in "._()-" else "-" for ch in raw)
	return safe.lstrip("._()-")[:200] or "invoice"


def _num(value) -> int:
	try:
		return int(value)
	except TypeError, ValueError:
		return -1


def _status_outcome(call: Call, payload: dict, response) -> Outcome:
	"""The platform's four integers, translated once.

	Receipt is the platform's own hold on the document: it has it unless its
	validation refused it. Delivery and reporting come from their own fields
	and stay separate. The withdraw states mean somebody acted in the portal
	outside this app's flow, and that is held for a person, not guessed.
	"""
	internal = _num(payload.get("internal_validation_status"))
	c3 = _num(payload.get("c3_mls_status"))
	c5 = _num(payload.get("c5_mls_status"))

	acknowledgements = Acknowledgements(
		asp_receipt=AspReceipt.REJECTED if internal == 2 else AspReceipt.RECEIVED,
		exchange=_EXCHANGE.get(c3, Exchange.UNKNOWN),
		reporting=_REPORTING.get(c5, Reporting.UNKNOWN),
		evidence=Evidence.PENDING,
	)
	advice = Advice.HOLD_FOR_PERSON if c5 in (5, 6, 7) else Advice.DO_NOT_RETRY

	return Outcome(
		operation=call.operation,
		disposition=Disposition.SUCCEEDED,
		effect=Effect.APPLIED,
		advice=advice,
		acknowledgements=acknowledgements,
		provider_ids={"document_id": str(payload.get("id") or "")},
		findings=_findings(payload),
		artifacts=_artifact_refs(payload),
		provider_code=f"status={payload.get('status')} ivs={internal} c3={c3} c5={c5}",
		diagnostic_ref=response.diagnostic_ref,
	)


def _nothing_there(call: Call, response) -> Outcome:
	"""The provider answered and holds nothing under what we asked by."""
	return Outcome(
		operation=call.operation,
		disposition=Disposition.SUCCEEDED,
		effect=Effect.APPLIED,
		advice=Advice.DO_NOT_RETRY,
		acknowledgements=Acknowledgements(asp_receipt=AspReceipt.NOT_SENT),
		provider_code="not-found",
		diagnostic_ref=response.diagnostic_ref,
	)


def _refused(call: Call, response, *, may_have_applied: bool, code: str | None = None) -> Outcome:
	"""An HTTP answer that is not the one the operation wanted.

	The division that matters: an answer that provably applied nothing can
	be retried or fixed, and an ambiguous one on the call that creates the
	invoice is unknown until it is reconciled.
	"""
	provider_code = code or str(response.status)
	if response.status == 429:
		return Outcome(
			operation=call.operation,
			disposition=Disposition.RATE_LIMITED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.RETRY_SAME_PAYLOAD,
			retry_after_seconds=response.retry_after_seconds() or 60,
			provider_code=provider_code,
			diagnostic_ref=response.diagnostic_ref,
		)
	if response.status == 401:
		return Outcome(
			operation=call.operation,
			disposition=Disposition.AUTHENTICATION_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.REFRESH_AUTHENTICATION,
			provider_code=provider_code,
			diagnostic_ref=response.diagnostic_ref,
		)
	if may_have_applied:
		outcome = Outcome(
			operation=call.operation,
			disposition=Disposition.UNKNOWN,
			effect=Effect.UNKNOWN,
			advice=Advice.HOLD_FOR_PERSON,
			acknowledgements=Acknowledgements(asp_receipt=AspReceipt.UNKNOWN),
			provider_code=provider_code,
			diagnostic_ref=response.diagnostic_ref,
		)
		return replace(outcome, advice=advise(outcome, DECLARATION))
	if response.status >= 500:
		return Outcome(
			operation=call.operation,
			disposition=Disposition.TRANSPORT_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.RETRY_SAME_PAYLOAD,
			provider_code=provider_code,
			diagnostic_ref=response.diagnostic_ref,
		)
	return Outcome(
		operation=call.operation,
		disposition=Disposition.BUSINESS_REJECTED,
		effect=Effect.NOT_APPLIED,
		advice=Advice.HOLD_FOR_PERSON,
		provider_code=provider_code,
		diagnostic_ref=response.diagnostic_ref,
	)


def _findings(payload: dict) -> tuple[Finding, ...]:
	"""The platform's complaints, in the app's own words.

	The rule id and message arrive as one string, kept whole: the reader
	looks the rule up in the official text either way.
	"""
	found = []
	for field, note in (
		("internal_validation_error_message", "validation"),
		("c3_mls_error_message", "delivery"),
	):
		message = payload.get(field)
		if message:
			found.append(
				Finding(
					code=REJECTED_CODE,
					severity=Severity.ERROR,
					stage=Stage.PROVIDER_RESPONSE,
					message=str(message),
					path="/",
					repair=REJECTED_REPAIR,
					params={"provider_stage": note},
				)
			)
	return tuple(found)


def _artifact_refs(payload: dict) -> tuple[ArtifactRef, ...]:
	"""What the platform holds for this invoice, as references to fetch."""
	found = []
	for field, kind, media in (
		("invoice_xml_location_path", "provider-xml", XML_MEDIA_TYPE),
		("tdd_location_path", "tdd", XML_MEDIA_TYPE),
		("pdf_location_path", "pdf", "application/pdf"),
	):
		path = payload.get(field)
		if path:
			found.append(ArtifactRef(kind=kind, identifier=str(path), media_type=media))
	return tuple(found)
