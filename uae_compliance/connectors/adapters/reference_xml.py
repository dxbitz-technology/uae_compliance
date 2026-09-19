"""A test adapter for a provider that takes the reference XML.

It sends the bytes the serializer already produced and nothing else. It does
not build them, does not reformat them, and refuses anything that is not the
UBL this app writes. A worker may wrap approved content in an envelope. It may
not rebuild it, and an adapter that quietly re-serialized would be doing
exactly that.

The provider it pretends to be keeps its promises: an idempotency key means
something and a submission can be found again. That is what makes an ambiguous
send resolvable here, and it is the difference between this adapter and the
JSON one next to it.
"""

from __future__ import annotations

import json
from dataclasses import replace

from uae_compliance.connectors.adapters import simulation_api as api
from uae_compliance.connectors.registry import Call
from uae_compliance.connectors.transport import Request, Transport, TransportError
from uae_compliance.domain.connector import (
	Adapter,
	ContractError,
	Environment,
	Idempotency,
	Operation,
	Outcome,
)

MEDIA_TYPE = "application/xml"

# The two roots the serializer writes. Anything else is not our reference XML,
# whatever its content type claims.
ROOTS = (b"Invoice", b"CreditNote")

DECLARATION = Adapter(
	provider_key="reference_xml",
	label="Reference XML provider (simulation)",
	adapter_version="1.0.0",
	contract_version=1,
	# Simulation and nothing else. The registry refuses to use an adapter in an
	# environment it has not declared, so this one can never reach Production.
	environments=(Environment.SIMULATION,),
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
	request_format="UBL 2.1 XML as the serializer writes it",
	authentication="OAuth client credentials",
	idempotency=Idempotency(scope="client and key", expiry_seconds=86400),
	can_search_by_key=True,
	# The simulator posts callbacks unsigned. Declaring a scheme it does not
	# have would be claiming a capability, so this stays empty and events from
	# it count for nothing until something verifies them.
	event_authentication=None,
	events_carry_order=True,
	supports_artifacts=True,
	pagination="cursor",
	scenarios=("standard", "credit note", "export", "free zone"),
)


class ReferenceXmlAdapter:
	descriptor = DECLARATION

	def perform(self, call: Call, transport: Transport) -> Outcome:
		api.require_declared(self.descriptor, call.operation)
		if call.operation is Operation.AUTHENTICATE:
			return api.sign_in(call, transport, self.descriptor)
		missing = api.with_token(call, transport, self.descriptor)
		if missing is not None:
			return missing
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
			return api.failed(call, self.descriptor, error)

	def _submit(self, call: Call, transport: Transport) -> Outcome:
		body = _approved_xml(call)
		response = transport.fetch(
			Request(
				operation=Operation.SUBMIT,
				method="POST",
				url=call.connection.url(api.INVOICES_PATH),
				headers=api.headers_for(call, MEDIA_TYPE, len(body), call.idempotency_key),
				body=body,
				secrets=call.connection.secrets(),
				label="submit",
				correlation=call.correlation,
				connection=call.connection.connection_id,
			)
		)
		return api.submit_outcome(call, response, self.descriptor)

	def _status(self, call: Call, transport: Transport) -> Outcome:
		identifier = call.provider_ids.get("document_id")
		if not identifier:
			raise ContractError("a status needs the identifier the provider gave us")
		response = transport.fetch(self._read(call, f"{api.INVOICES_PATH}/{identifier}", "status"))
		return api.status_outcome(call, response, self.descriptor)

	def _find(self, call: Call, transport: Transport) -> Outcome:
		"""Settle an ambiguous send by asking about the key we sent it under."""
		if not call.idempotency_key:
			raise ContractError("there is nothing to search by without the key that was sent")
		response = transport.fetch(
			self._read(call, f"{api.INVOICES_PATH}?idempotency_key={call.idempotency_key}", "find")
		)
		found = api.body_of(response).get("results") or []
		if response.status == 200 and found:
			return api.status_outcome(call, response, self.descriptor, found[0])
		return api.status_outcome(call, response, self.descriptor)

	def _artifact(self, call: Call, transport: Transport) -> Outcome:
		if call.artifact is None:
			raise ContractError("fetching evidence needs the reference to it")
		body = json.dumps({"uri": call.artifact.identifier}).encode()
		response = transport.fetch(
			Request(
				operation=Operation.FETCH_ARTIFACT,
				method="POST",
				url=call.connection.url(api.DOWNLOAD_PATH),
				headers=api.headers_for(call, "application/json", len(body)),
				body=body,
				secrets=call.connection.secrets(),
				label="artifact",
				correlation=call.correlation,
				connection=call.connection.connection_id,
			)
		)
		return api.artifact_outcome(call, response)

	def _inbound(self, call: Call, transport: Transport) -> Outcome:
		path = f"{api.INVOICES_PATH}?direction=2"
		if call.cursor:
			path = f"{path}&cursor={call.cursor}"
		if call.page_size:
			path = f"{path}&limit={call.page_size}"
		response = transport.fetch(self._read(call, path, "inbound"))
		outcome = api.status_outcome(call, response, self.descriptor)
		body = api.body_of(response)

		# The documents come back with their contents. A list of references
		# somebody then fetches one at a time is not how these providers work,
		# and it would make a page of fifty invoices fifty more requests.
		received = tuple(api.inbound_documents(body))
		cursor = body.get("next")
		return replace(
			outcome,
			artifacts=outcome.artifacts + received,
			event_cursor=str(cursor) if cursor else outcome.event_cursor,
		)

	def _read(self, call: Call, path: str, label: str) -> Request:
		return Request(
			operation=call.operation,
			method="GET",
			url=call.connection.url(path),
			headers={"Authorization": f"Bearer {call.connection.session.token}"},
			secrets=call.connection.secrets(),
			label=label,
			correlation=call.correlation,
			connection=call.connection.connection_id,
		)


def _approved_xml(call: Call) -> bytes:
	"""The frozen bytes, checked to be the XML this app writes.

	A JSON body arriving here would mean something upstream decided every
	provider takes the same thing. It does not, and this says so rather than
	posting it and letting the provider work it out.
	"""
	if call.request is None:
		raise ContractError("this provider takes the reference XML and none was frozen for it")
	if "xml" not in call.request.media_type:
		raise ContractError(f"this provider takes XML, not {call.request.media_type}")
	head = call.request.body.lstrip()[:200]
	if not any(root in head for root in ROOTS):
		raise ContractError("the frozen payload is not the reference invoice XML")
	return call.request.body
