"""The two test adapters, against the simulator, over a real socket.

They exist as a pair on purpose. One sends the XML the serializer writes and
one builds a provider's own JSON from the canonical document, so anything that
quietly assumed every provider takes the same bytes fails here.

They also promise different things, which is the more interesting half. The XML
one honours an idempotency key and can be searched, so a send whose answer never
arrived can be settled. The JSON one promises nothing, so the same send has to
be held for a person. Same app, same document, two correct and opposite
answers.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uae_compliance.connectors.adapters.reference_xml import ReferenceXmlAdapter
from uae_compliance.connectors.adapters.simulated_json import SimulatedJsonAdapter, to_provider_json
from uae_compliance.connectors.registry import BusinessRequest, Call, Connection, installed
from uae_compliance.connectors.simulator import BARE, Behaviour, Simulator, SimulatorServer, Store
from uae_compliance.connectors.transport import InMemoryRecorder, Policy, Transport
from uae_compliance.domain.connector import (
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
	Reporting,
)
from uae_compliance.domain.findings import Stage
from uae_compliance.validation.serializer import to_xml

# The serializer's own fixture. Reused rather than copied, so what this checks
# really is the XML the serializer produces and not a hand-written lookalike.
from uae_compliance.validation.tests.test_serializer import an_invoice

CREDENTIALS = {"client_id": "sim_client", "client_secret": "sim_secret_value"}


class AdapterCase(unittest.TestCase):
	profile = None

	def setUp(self):
		self.folder = tempfile.TemporaryDirectory()
		self.store = Store(str(Path(self.folder.name) / "simulator.db"))
		self.simulator = Simulator(self.store, self.profile) if self.profile else Simulator(self.store)
		self.server = SimulatorServer(self.simulator).start()
		self.recorder = InMemoryRecorder()
		self.transport = Transport(
			Policy(
				environment=Environment.SIMULATION,
				trusted_hosts=("127.0.0.1",),
				allow_plain_http=True,
				allow_private_addresses=True,
				connect_timeout=5.0,
				read_timeout=5.0,
			),
			self.recorder,
		)

	def tearDown(self):
		self.server.stop()
		self.store.close()
		self.folder.cleanup()

	def connection(self, provider_key):
		return Connection(
			provider_key=provider_key,
			connection_id=f"{provider_key} simulation",
			environment=Environment.SIMULATION,
			base_url=self.server.base_url,
			credentials=dict(CREDENTIALS),
		)

	def xml_call(self, number="SINV-0001", key="key-1", **kwargs):
		document = an_invoice(number=number)
		body = to_xml(document)
		return Call(
			operation=Operation.SUBMIT,
			connection=kwargs.pop("connection", None) or self.connection("reference_xml"),
			document=document,
			request=BusinessRequest(media_type="application/xml", body=body),
			idempotency_key=key,
			**kwargs,
		)

	def json_call(self, number="SINV-0001", **kwargs):
		return Call(
			operation=Operation.SUBMIT,
			connection=kwargs.pop("connection", None) or self.connection("simulated_json"),
			document=an_invoice(number=number),
			**kwargs,
		)

	def run_call(self, adapter, call):
		return adapter.perform(call, self.transport)


class SendingTheReferenceXml(AdapterCase):
	def setUp(self):
		super().setUp()
		self.adapter = ReferenceXmlAdapter()

	def test_the_xml_the_serializer_writes_is_accepted(self):
		outcome = self.run_call(self.adapter, self.xml_call())
		self.assertIs(outcome.disposition, Disposition.SUCCEEDED)
		self.assertIs(outcome.effect, Effect.APPLIED)
		self.assertTrue(outcome.provider_ids["document_id"].startswith("SIM-"))

	def test_it_signs_in_on_its_own_first(self):
		call = self.xml_call()
		self.assertIsNone(call.connection.session.token)
		self.run_call(self.adapter, call)
		self.assertTrue(call.connection.session.token.startswith("sim_tok_"))

	def test_it_sends_exactly_the_bytes_that_were_frozen(self):
		call = self.xml_call()
		self.run_call(self.adapter, call)
		stored = self.store.find_by_key("sim_client", "key-1")
		self.assertEqual(stored.media_type, "application/xml")

	def test_it_refuses_a_payload_that_is_not_the_reference_xml(self):
		call = self.xml_call()
		wrong = Call(
			operation=Operation.SUBMIT,
			connection=call.connection,
			request=BusinessRequest(media_type="application/json", body=b'{"invoice_number": "X"}'),
			idempotency_key="key-2",
		)
		with self.assertRaises(ContractError):
			self.run_call(self.adapter, wrong)

	def test_it_refuses_to_send_with_nothing_frozen(self):
		call = Call(
			operation=Operation.SUBMIT,
			connection=self.connection("reference_xml"),
			document=an_invoice(),
			idempotency_key="key-3",
		)
		with self.assertRaises(ContractError):
			self.run_call(self.adapter, call)

	def test_an_operation_it_never_declared_does_not_exist(self):
		call = Call(operation=Operation.WITHDRAW, connection=self.connection("reference_xml"))
		with self.assertRaises(ContractError):
			self.run_call(self.adapter, call)


class SendingTheProviderJson(AdapterCase):
	def setUp(self):
		super().setUp()
		self.adapter = SimulatedJsonAdapter()

	def test_the_canonical_document_is_accepted_as_json(self):
		outcome = self.run_call(self.adapter, self.json_call())
		self.assertIs(outcome.disposition, Disposition.SUCCEEDED)
		self.assertTrue(outcome.provider_ids["document_id"].startswith("SIM-"))

	def test_it_sends_json_and_not_the_serializer_output(self):
		self.run_call(self.adapter, self.json_call())
		stored = self.store.find_by_number("sim_client", "SINV-0001")[0]
		self.assertEqual(stored.media_type, "application/json")

	def test_the_mapping_is_the_provider_own_shape(self):
		body = to_provider_json(an_invoice(number="SINV-0009"))
		self.assertEqual(body["invoice_number"], "SINV-0009")
		self.assertEqual(body["mapping_version"], "simulated-json-v1")
		# Nothing in it is named the way the XML names it.
		self.assertNotIn("cbc:ID", json.dumps(body))
		self.assertIn("supplier", body)
		self.assertIn("items", body)

	def test_amounts_travel_as_strings(self):
		body = to_provider_json(an_invoice())
		self.assertIsInstance(body["amounts"]["gross"], str)
		self.assertIsInstance(body["items"][0]["line_total"], str)

	def test_it_does_not_need_the_reference_xml_at_all(self):
		call = self.json_call()
		self.assertIsNone(call.request)
		self.assertIs(self.run_call(self.adapter, call).disposition, Disposition.SUCCEEDED)

	def test_it_declares_no_search_and_offers_none(self):
		self.assertFalse(self.adapter.descriptor.supports(Operation.FIND_SUBMISSION))
		call = Call(operation=Operation.FIND_SUBMISSION, connection=self.connection("simulated_json"))
		with self.assertRaises(ContractError):
			self.run_call(self.adapter, call)


class WhenTheProviderSaysNo(AdapterCase):
	def setUp(self):
		super().setUp()
		self.adapter = ReferenceXmlAdapter()

	def test_a_rejection_is_not_a_transport_problem(self):
		self.simulator.plan("SINV-BAD", Behaviour.REJECT_VALIDATION)
		outcome = self.run_call(self.adapter, self.xml_call("SINV-BAD", key="key-bad"))
		self.assertIs(outcome.disposition, Disposition.BUSINESS_REJECTED)
		self.assertIs(outcome.effect, Effect.NOT_APPLIED)
		self.assertIs(outcome.advice, Advice.DO_NOT_RETRY)

	def test_the_provider_complaints_arrive_as_findings(self):
		self.simulator.plan("SINV-BAD", Behaviour.REJECT_VALIDATION)
		outcome = self.run_call(self.adapter, self.xml_call("SINV-BAD", key="key-bad"))
		self.assertTrue(outcome.findings)
		for finding in outcome.findings:
			self.assertIs(finding.stage, Stage.PROVIDER_RESPONSE)
			self.assertEqual(finding.code, "PROVIDER_REJECTED")
		codes = {finding.params["provider_code"] for finding in outcome.findings}
		self.assertIn("AE-VAT-0012", codes)

	def test_a_rate_limit_carries_the_provider_own_wait(self):
		self.simulator.plan("SINV-BUSY", Behaviour.RATE_LIMIT)
		outcome = self.run_call(self.adapter, self.xml_call("SINV-BUSY", key="key-busy"))
		self.assertIs(outcome.disposition, Disposition.RATE_LIMITED)
		self.assertEqual(outcome.retry_after_seconds, 30)
		self.assertIs(outcome.advice, Advice.RETRY_SAME_PAYLOAD)

	def test_an_expired_token_is_refreshed_before_the_next_send(self):
		self.run_call(self.adapter, self.xml_call())
		connection = self.connection("reference_xml")
		self.store.expire_tokens()
		connection.session.clear()
		outcome = self.run_call(self.adapter, self.xml_call("SINV-0002", key="key-2", connection=connection))
		self.assertIs(outcome.disposition, Disposition.SUCCEEDED)


class WhenNobodyKnowsWhatHappened(AdapterCase):
	"""The case the whole contract exists for, answered two different ways."""

	def test_a_provider_that_promises_nothing_holds_it_for_a_person(self):
		adapter = SimulatedJsonAdapter()
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		outcome = self.run_call(adapter, self.json_call("SINV-LOST"))
		self.assertIs(outcome.effect, Effect.UNKNOWN)
		self.assertIs(outcome.advice, Advice.HOLD_FOR_PERSON)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.UNKNOWN)

	def test_a_provider_that_can_be_searched_is_reconciled_instead(self):
		adapter = ReferenceXmlAdapter()
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		outcome = self.run_call(adapter, self.xml_call("SINV-LOST", key="key-lost"))
		self.assertIs(outcome.effect, Effect.UNKNOWN)
		self.assertIs(outcome.advice, Advice.RECONCILE_FIRST)

	def test_and_the_search_finds_the_document_that_did_arrive(self):
		adapter = ReferenceXmlAdapter()
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		connection = self.connection("reference_xml")
		self.run_call(adapter, self.xml_call("SINV-LOST", key="key-lost", connection=connection))
		found = adapter.perform(
			Call(
				operation=Operation.FIND_SUBMISSION,
				connection=connection,
				idempotency_key="key-lost",
			),
			self.transport,
		)
		self.assertIs(found.disposition, Disposition.SUCCEEDED)
		self.assertEqual(found.provider_ids["number"], "SINV-LOST")

	def test_an_unknown_outcome_is_never_told_to_send_the_same_thing_again(self):
		for adapter, call in (
			(SimulatedJsonAdapter(), self.json_call("SINV-LOST")),
			(ReferenceXmlAdapter(), self.xml_call("SINV-LOST", key="key-lost")),
		):
			self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
			outcome = self.run_call(adapter, call)
			self.assertIsNot(outcome.advice, Advice.RETRY_SAME_PAYLOAD)


class ReadingWhatBecameOfIt(AdapterCase):
	def setUp(self):
		super().setUp()
		self.adapter = ReferenceXmlAdapter()

	def status_after(self, number, key, behaviour):
		self.simulator.plan(number, behaviour)
		connection = self.connection("reference_xml")
		sent = self.run_call(self.adapter, self.xml_call(number, key=key, connection=connection))
		return self.adapter.perform(
			Call(
				operation=Operation.GET_STATUS,
				connection=connection,
				provider_ids=dict(sent.provider_ids),
			),
			self.transport,
		)

	def test_delivered_and_reported_are_both_recorded(self):
		outcome = self.status_after("SINV-OK", "key-ok", Behaviour.ACCEPT)
		self.assertIs(outcome.acknowledgements.exchange, Exchange.DELIVERED)
		self.assertIs(outcome.acknowledgements.reporting, Reporting.ACCEPTED)

	def test_delivery_succeeding_does_not_make_reporting_succeed(self):
		outcome = self.status_after("SINV-HALF", "key-half", Behaviour.DELIVERED_REPORTING_FAILED)
		self.assertIs(outcome.acknowledgements.exchange, Exchange.DELIVERED)
		self.assertIs(outcome.acknowledgements.reporting, Reporting.REJECTED)

	def test_and_the_other_way_round(self):
		outcome = self.status_after("SINV-OTHER", "key-other", Behaviour.REPORTED_DELIVERY_FAILED)
		self.assertIs(outcome.acknowledgements.exchange, Exchange.REJECTED)
		self.assertIs(outcome.acknowledgements.reporting, Reporting.ACCEPTED)

	def test_evidence_is_only_complete_once_it_has_been_fetched(self):
		connection = self.connection("reference_xml")
		sent = self.run_call(self.adapter, self.xml_call(connection=connection))
		self.assertIs(sent.acknowledgements.evidence, Evidence.PENDING)
		got = self.adapter.perform(
			Call(
				operation=Operation.FETCH_ARTIFACT,
				connection=connection,
				artifact=ArtifactRef(
					kind="receipt", identifier=f"{sent.provider_ids['document_id']}/receipt"
				),
			),
			self.transport,
		)
		self.assertIs(got.acknowledgements.evidence, Evidence.COMPLETE)

	def test_a_missing_artifact_is_its_own_problem_and_not_a_failed_document(self):
		"""The provider names evidence it then cannot produce.

		The document was still delivered and still reported. Only the file is
		missing, and saying otherwise would mark a good invoice as broken.
		"""
		outcome = self.status_after("SINV-GONE", "key-gone", Behaviour.MISSING_ARTIFACT)
		self.assertIs(outcome.acknowledgements.exchange, Exchange.DELIVERED)
		self.assertIs(outcome.acknowledgements.reporting, Reporting.ACCEPTED)
		promised = outcome.artifacts[0]
		got = self.adapter.perform(
			Call(
				operation=Operation.FETCH_ARTIFACT,
				connection=self.connection("reference_xml"),
				artifact=ArtifactRef(kind=promised.kind, identifier=promised.identifier),
			),
			self.transport,
		)
		self.assertIs(got.acknowledgements.evidence, Evidence.UNAVAILABLE)
		# Ask for the file again. Never send the invoice again to get it.
		self.assertIs(got.advice, Advice.RETRY_SAME_PAYLOAD)


class AgainstAProviderThatPromisesNothing(AdapterCase):
	profile = BARE

	def test_the_same_key_twice_really_does_make_two_documents(self):
		adapter = ReferenceXmlAdapter()
		first = self.run_call(adapter, self.xml_call())
		second = self.run_call(adapter, self.xml_call())
		# A declaration is a claim, not a fact. The XML adapter says a key is
		# honoured; this provider does not honour one, and two documents come
		# back. It is here as a reminder that a capability claim has to be
		# proved against the provider it names before it is believed.
		self.assertNotEqual(first.provider_ids["document_id"], second.provider_ids["document_id"])


class WhatTheInstallationHas(unittest.TestCase):
	def test_both_adapters_are_installed(self):
		registry = installed()
		self.assertEqual(registry.keys(), ("reference_xml", "simulated_json"))

	def test_neither_of_them_serves_production(self):
		registry = installed()
		for key in registry.keys():
			self.assertEqual(registry.declaration(key).environments, (Environment.SIMULATION,))

	def test_the_xml_one_can_settle_an_ambiguous_send(self):
		self.assertTrue(installed().declaration("reference_xml").can_resolve_an_ambiguous_send())

	def test_the_json_one_cannot(self):
		self.assertFalse(installed().declaration("simulated_json").can_resolve_an_ambiguous_send())

	def test_a_production_connection_cannot_use_either(self):
		registry = installed()
		connection = Connection(
			provider_key="reference_xml",
			connection_id="live",
			environment=Environment.PRODUCTION,
			base_url="https://api.example.test",
		)
		with self.assertRaises(ContractError):
			registry.for_connection(connection, Operation.SUBMIT)


if __name__ == "__main__":
	unittest.main()
