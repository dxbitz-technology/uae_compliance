"""A test adapter for a provider that takes JSON of its own design.

This one exists to be different. It never sees the reference XML and could not
use it if it did. It reads the canonical document and builds the provider's own
shape: different field names, different nesting, decimals as strings. If
anything upstream ever starts assuming that every provider consumes the XML we
write, this is what fails.

It also promises nothing. No idempotency key, no way to search for a
submission. Against this provider a send whose answer never arrived can never
be settled, and the app has to hold it for a person rather than send the
document again. That is not a gap in the adapter. It is a real kind of provider
and the app has to be able to work with one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal

from uae_compliance.connectors.adapters import simulation_api as api
from uae_compliance.connectors.registry import Call
from uae_compliance.connectors.transport import Request, Transport, TransportError
from uae_compliance.domain.canonical import SCENARIO_FLAGS
from uae_compliance.domain.connector import (
	Adapter,
	ContractError,
	Environment,
	Operation,
	Outcome,
)
from uae_compliance.domain.encoding import NotApplicable, canonical_decimal, read_not_applicable

MEDIA_TYPE = "application/json"
MAPPING_VERSION = "simulated-json-v1"

DECLARATION = Adapter(
	provider_key="simulated_json",
	label="Simulated JSON provider (simulation)",
	adapter_version="1.0.0",
	contract_version=1,
	environments=(Environment.SIMULATION,),
	# Three operations and no more. Anything undeclared does not exist, and the
	# app must not invent a way around that.
	operations=frozenset({Operation.AUTHENTICATE, Operation.SUBMIT, Operation.GET_STATUS}),
	request_format="Provider JSON, mapped from the canonical document",
	authentication="OAuth client credentials",
	# No promise about sending the same thing twice, and nothing to search by.
	idempotency=None,
	can_search_by_key=False,
	event_authentication=None,
	events_carry_order=False,
	supports_artifacts=False,
	pagination=None,
	scenarios=("standard", "credit note"),
)


class SimulatedJsonAdapter:
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
			return self._status(call, transport)
		except TransportError as error:
			return api.failed(call, self.descriptor, error)

	def _submit(self, call: Call, transport: Transport) -> Outcome:
		if call.document is None:
			raise ContractError("this provider builds its own request and needs the canonical document")
		body = json.dumps(to_provider_json(call.document), sort_keys=True).encode()
		response = transport.fetch(
			Request(
				operation=Operation.SUBMIT,
				method="POST",
				url=call.connection.url(api.INVOICES_PATH),
				# No idempotency key. This provider makes no promise about one
				# and sending it would suggest otherwise.
				headers=api.headers_for(call, MEDIA_TYPE, len(body)),
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
		response = transport.fetch(
			Request(
				operation=Operation.GET_STATUS,
				method="GET",
				url=call.connection.url(f"{api.INVOICES_PATH}/{identifier}"),
				headers={"Authorization": f"Bearer {call.connection.session.token}"},
				secrets=call.connection.secrets(),
				label="status",
				correlation=call.correlation,
				connection=call.connection.connection_id,
			)
		)
		return api.status_outcome(call, response, self.descriptor)


def to_provider_json(document: Mapping) -> dict:
	"""The canonical invoice in this provider's shape.

	Nothing here matches the XML. The names are the provider's, the nesting is
	the provider's, and amounts are strings because a provider that took them
	as floats would be a different problem again.
	"""
	head = document.get("document") or {}
	parties = document.get("parties") or {}
	totals = document.get("totals") or {}
	scenario = document.get("scenario") or {}
	return _drop_empty(
		{
			"mapping_version": MAPPING_VERSION,
			"invoice_number": _plain(head.get("number")),
			"invoice_uuid": _plain(head.get("uuid")),
			"invoice_type_code": _plain(head.get("type_code")),
			"issued_on": _plain(head.get("issue_date")),
			"due_on": _plain(head.get("due_date")),
			"currency_code": _plain(head.get("currency")),
			"buyer_reference": _plain(head.get("buyer_reference")),
			"markers": [name for name in SCENARIO_FLAGS if scenario.get(name)],
			"supplier": _party(parties.get("seller")),
			"customer": _party(parties.get("buyer")),
			"items": [_line(line) for line in document.get("lines") or ()],
			"tax_lines": [_tax(row) for row in document.get("tax_breakdown") or ()],
			"amounts": {
				"net": _plain(totals.get("tax_exclusive")),
				"tax": _plain(totals.get("tax")),
				"gross": _plain(totals.get("tax_inclusive")),
				"due": _plain(totals.get("payable")),
			},
		}
	)


def _party(party: Mapping | None) -> dict | None:
	if not party:
		return None
	address = party.get("address") or {}
	return _drop_empty(
		{
			"name": _plain(party.get("legal_name")),
			"country_code": _plain(party.get("country")),
			"tax_number": _identifier(party.get("tax_registration")),
			"network_id": _identifier(party.get("participant")),
			"city": _plain(address.get("city")),
			"street": _plain(address.get("line1")),
		}
	)


def _identifier(value) -> str | None:
	value = read_not_applicable(value)
	if isinstance(value, NotApplicable) or not value:
		return None
	if isinstance(value, Mapping):
		return _plain(value.get("value"))
	return _plain(value)


def _line(line: Mapping) -> dict:
	return _drop_empty(
		{
			"row": _plain(line.get("id")),
			"description": _plain(line.get("name")),
			"item_code": _plain(line.get("item_code")),
			"quantity": _plain(line.get("quantity")),
			"unit": _plain(line.get("uom_code")),
			"unit_price": _plain(line.get("net_price")),
			"line_total": _plain(line.get("net_amount")),
			"tax_code": _plain(line.get("tax_category")),
			"tax_percent": _plain(line.get("tax_rate")),
		}
	)


def _tax(row: Mapping) -> dict:
	return _drop_empty(
		{
			"tax_code": _plain(row.get("category")),
			"tax_percent": _plain(row.get("rate")),
			"taxable": _plain(row.get("taxable_amount")),
			"tax": _plain(row.get("tax_amount")),
			"exemption_reason": _plain(row.get("reason")),
		}
	)


def _plain(value):
	"""One value in a form JSON can carry without losing anything.

	A decimal becomes the same string the canonical encoding writes, so a
	number never arrives at a provider as a float. A field marked as not
	applicable is left out rather than sent as null, because the two mean
	different things and only one of them is true here.
	"""
	value = read_not_applicable(value)
	if value is None or isinstance(value, NotApplicable):
		return None
	if isinstance(value, Decimal):
		return canonical_decimal(value)
	if isinstance(value, bool):
		return value
	if isinstance(value, Mapping):
		return _drop_empty({key: _plain(item) for key, item in value.items()})
	if isinstance(value, list | tuple):
		return [_plain(item) for item in value]
	return str(value)


def _drop_empty(value: dict) -> dict:
	return {key: item for key, item in value.items() if item not in (None, [], {})}
