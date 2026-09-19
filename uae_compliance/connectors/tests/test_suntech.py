"""The Suntech adapter against scripted answers.

No socket and no site. Every response below is shaped exactly as the
published sandbox reference shows it, so these tests pin the translation:
the three-call submission, the four status integers, the settle-by-search
rule, and the inbox anchor. What they cannot pin is the sandbox itself;
that evidence comes from the live runs in P10.
"""

from __future__ import annotations

import json
import unittest

from uae_compliance.connectors.adapters.suntech import DECLARATION, SuntechAdapter
from uae_compliance.connectors.registry import BusinessRequest, Call, Connection
from uae_compliance.connectors.transport import Response, policy_for
from uae_compliance.domain.connector import (
	Advice,
	AspReceipt,
	ContractError,
	Disposition,
	Effect,
	Environment,
	Exchange,
	Operation,
	Reporting,
)

BASE = "https://portal-sandbox.taxcomplianceagent.com/api/v1"


def a_connection() -> Connection:
	return Connection(
		provider_key="suntech",
		connection_id="Sandbox Seller",
		environment=Environment.SANDBOX,
		base_url=BASE,
		credentials={"client_id": "an-id", "client_secret": "a-secret-value"},
	)


def a_document() -> dict:
	return {
		"document": {
			"number": "SINV-0007",
			"issue_date": "2026-09-19",
			"type_code": "380",
			"uuid": "0198f3a2-0000-7000-8000-000000000001",
		}
	}


def a_request() -> BusinessRequest:
	return BusinessRequest(media_type="application/xml", body=b"<Invoice/>")


def answer(status: int, payload=None, headers=None, raw: bytes | None = None) -> Response:
	body = raw if raw is not None else json.dumps(payload or {}).encode()
	return Response(
		status=status,
		headers=headers or {},
		body=body,
		url=BASE,
		diagnostic_ref="attempt-1",
		elapsed_ms=1,
	)


def token_answer() -> Response:
	return answer(200, {"access_token": "eyJ-token", "expires_in": 600})


class ScriptedTransport:
	"""Hands back the scripted answers in order and keeps every request."""

	def __init__(self, answers):
		self.answers = list(answers)
		self.requests = []

	def fetch(self, request):
		self.requests.append(request)
		if not self.answers:
			raise AssertionError(f"nothing scripted for {request.label}")
		scripted = self.answers.pop(0)
		if isinstance(scripted, Exception):
			raise scripted
		return scripted


def perform(operation, answers, **call_fields):
	adapter = SuntechAdapter()
	transport = ScriptedTransport(answers)
	call = Call(operation=operation, connection=a_connection(), **call_fields)
	return adapter.perform(call, transport), transport


class Submitting(unittest.TestCase):
	def three_call_answers(self):
		return [
			token_answer(),
			answer(
				201,
				{
					"id": "01HXDOC",
					"path": "s3://bucket/organization/org-1/documents/SINV-0007.xml",
					"upload_url": "https://bucket.s3.amazonaws.com/key?X-Amz-Signature=abc",
					"expires_in": 3600,
				},
			),
			answer(200, {}),
			answer(201, {"id": "01HXINV", "source": "xml_upload"}),
		]

	def test_a_submission_is_three_calls_after_the_token(self):
		outcome, transport = perform(
			Operation.SUBMIT, self.three_call_answers(), request=a_request(), document=a_document()
		)
		self.assertIs(outcome.disposition, Disposition.SUCCEEDED)
		self.assertIs(outcome.effect, Effect.APPLIED)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.RECEIVED)
		self.assertEqual(outcome.provider_ids["document_id"], "01HXINV")

		labels = [request.label for request in transport.requests]
		self.assertEqual(labels, ["token", "reserve document", "upload document", "submit"])

	def test_the_upload_goes_to_the_presigned_url_without_the_token(self):
		_outcome, transport = perform(
			Operation.SUBMIT, self.three_call_answers(), request=a_request(), document=a_document()
		)
		upload = transport.requests[2]
		self.assertTrue(upload.url.startswith("https://bucket.s3.amazonaws.com/"))
		self.assertEqual(upload.body, b"<Invoice/>")
		self.assertNotIn("Authorization", upload.headers)

	def test_the_submission_references_the_stored_file_and_never_a_detail(self):
		_outcome, transport = perform(
			Operation.SUBMIT, self.three_call_answers(), request=a_request(), document=a_document()
		)
		body = json.loads(transport.requests[3].body)
		self.assertEqual(body["invoice_number"], "SINV-0007")
		self.assertEqual(body["invoice_type_code"], "380")
		self.assertEqual(body["source_file_path"], "s3://bucket/organization/org-1/documents/SINV-0007.xml")
		self.assertNotIn("detail", body)

	def test_a_taken_number_is_settled_before_anything_else(self):
		answers = self.three_call_answers()
		answers[3] = answer(400, {"invoice_number": ["already used for this issue year"]})
		outcome, _transport = perform(Operation.SUBMIT, answers, request=a_request(), document=a_document())
		self.assertIs(outcome.effect, Effect.UNKNOWN)
		self.assertIs(outcome.advice, Advice.RECONCILE_FIRST)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.UNKNOWN)

	def test_a_rate_limit_carries_the_providers_own_wait(self):
		answers = [token_answer(), answer(429, {}, headers={"Retry-After": "120"})]
		outcome, _transport = perform(Operation.SUBMIT, answers, request=a_request(), document=a_document())
		self.assertIs(outcome.disposition, Disposition.RATE_LIMITED)
		self.assertEqual(outcome.retry_after_seconds, 120)

	def test_a_server_error_on_the_final_call_is_unknown(self):
		answers = self.three_call_answers()
		answers[3] = answer(502, {"detail": "upstream failed"})
		outcome, _transport = perform(Operation.SUBMIT, answers, request=a_request(), document=a_document())
		self.assertIs(outcome.effect, Effect.UNKNOWN)
		self.assertIs(outcome.advice, Advice.RECONCILE_FIRST)

	def test_a_server_error_before_the_final_call_applied_nothing(self):
		answers = [token_answer(), answer(500, {"detail": "boom"})]
		outcome, _transport = perform(Operation.SUBMIT, answers, request=a_request(), document=a_document())
		self.assertIs(outcome.effect, Effect.NOT_APPLIED)
		self.assertIs(outcome.advice, Advice.RETRY_SAME_PAYLOAD)


class ReadingStatus(unittest.TestCase):
	def detail(self, **overrides):
		payload = {
			"id": "01HXINV",
			"status": 2,
			"internal_validation_status": 3,
			"internal_validation_error_message": None,
			"c3_mls_status": 4,
			"c5_mls_status": 4,
			"invoice_xml_location_path": "s3://bucket/org/wire.xml",
			"tdd_location_path": "s3://bucket/org/tdd.xml",
			"pdf_location_path": None,
		}
		payload.update(overrides)
		return payload

	def test_the_four_integers_translate_to_the_four_dimensions(self):
		answers = [token_answer(), answer(200, self.detail())]
		outcome, _transport = perform(Operation.GET_STATUS, answers, provider_ids={"document_id": "01HXINV"})
		acks = outcome.acknowledgements
		self.assertIs(acks.asp_receipt, AspReceipt.RECEIVED)
		self.assertIs(acks.exchange, Exchange.DELIVERED)
		self.assertIs(acks.reporting, Reporting.ACCEPTED)
		self.assertEqual([a.kind for a in outcome.artifacts], ["provider-xml", "tdd"])

	def test_a_validation_refusal_reads_as_rejected_with_the_rule(self):
		payload = self.detail(
			status=3,
			internal_validation_status=2,
			internal_validation_error_message="ibr-055-ae: a credit note names what it corrects",
			c3_mls_status=0,
			c5_mls_status=0,
		)
		answers = [token_answer(), answer(200, payload)]
		outcome, _transport = perform(Operation.GET_STATUS, answers, provider_ids={"document_id": "01HXINV"})
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.REJECTED)
		self.assertIn("ibr-055-ae", outcome.findings[0].message)

	def test_a_withdraw_state_is_held_for_a_person(self):
		answers = [token_answer(), answer(200, self.detail(c5_mls_status=7))]
		outcome, _transport = perform(Operation.GET_STATUS, answers, provider_ids={"document_id": "01HXINV"})
		self.assertIs(outcome.acknowledgements.reporting, Reporting.UNKNOWN)
		self.assertIs(outcome.advice, Advice.HOLD_FOR_PERSON)

	def test_a_document_the_provider_never_saw_says_so(self):
		answers = [token_answer(), answer(404, {"detail": "Not found."})]
		outcome, _transport = perform(
			Operation.GET_STATUS, answers, provider_ids={"document_id": "01HXMISSING"}
		)
		self.assertIs(outcome.disposition, Disposition.SUCCEEDED)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.NOT_SENT)


class SettlingByNumber(unittest.TestCase):
	def test_a_found_number_is_read_back_in_full(self):
		answers = [
			token_answer(),
			answer(200, {"results": [{"id": "01HXINV", "invoice_number": "SINV-0007"}]}),
			answer(
				200,
				{
					"id": "01HXINV",
					"status": 2,
					"internal_validation_status": 3,
					"c3_mls_status": 4,
					"c5_mls_status": 4,
				},
			),
		]
		outcome, transport = perform(
			Operation.FIND_SUBMISSION, answers, provider_ids={"invoice_number": "SINV-0007"}
		)
		self.assertIs(outcome.acknowledgements.exchange, Exchange.DELIVERED)
		self.assertEqual(outcome.provider_ids["document_id"], "01HXINV")
		self.assertIn("search=SINV-0007", transport.requests[1].url)

	def test_nothing_found_is_an_answer_not_a_shrug(self):
		answers = [token_answer(), answer(200, {"results": []})]
		outcome, _transport = perform(
			Operation.FIND_SUBMISSION, answers, provider_ids={"invoice_number": "SINV-0007"}
		)
		self.assertIs(outcome.disposition, Disposition.SUCCEEDED)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.NOT_SENT)

	def test_a_loose_match_is_not_a_match(self):
		answers = [
			token_answer(),
			answer(200, {"results": [{"id": "01HXOTHER", "invoice_number": "SINV-00070"}]}),
		]
		outcome, _transport = perform(
			Operation.FIND_SUBMISSION, answers, provider_ids={"invoice_number": "SINV-0007"}
		)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.NOT_SENT)


class CollectingTheInbox(unittest.TestCase):
	def download_answers(self, body: bytes):
		return [
			answer(201, {"download_url": "https://bucket.s3.amazonaws.com/d?X-Amz-Signature=x"}),
			answer(200, raw=body),
		]

	def test_the_walk_lands_oldest_first_and_anchors_on_the_newest(self):
		answers = [
			token_answer(),
			answer(
				200,
				{
					"next": None,
					"results": [
						{"id": "01HXB2", "invoice_xml_location_path": "s3://bucket/org/b2.xml"},
						{"id": "01HXB1", "invoice_xml_location_path": "s3://bucket/org/b1.xml"},
					],
				},
			),
			*self.download_answers(b"<Invoice>b1</Invoice>"),
			*self.download_answers(b"<Invoice>b2</Invoice>"),
		]
		outcome, transport = perform(Operation.FETCH_INBOUND, answers, cursor="01HXA0", page_size=50)
		self.assertEqual([a.identifier for a in outcome.artifacts], ["01HXB1", "01HXB2"])
		self.assertEqual(outcome.artifacts[0].body, b"<Invoice>b1</Invoice>")
		self.assertEqual(outcome.event_cursor, "01HXB2")
		self.assertIn("after=01HXA0", transport.requests[1].url)
		self.assertIn("direction=2", transport.requests[1].url)

	def test_an_empty_inbox_never_erases_the_anchor(self):
		answers = [token_answer(), answer(200, {"next": None, "results": []})]
		outcome, _transport = perform(Operation.FETCH_INBOUND, answers, cursor="01HXA0", page_size=50)
		self.assertEqual(outcome.artifacts, ())
		self.assertEqual(outcome.event_cursor, "01HXA0")

	def test_a_row_still_settling_stops_the_anchor_before_it(self):
		answers = [
			token_answer(),
			answer(
				200,
				{
					"next": None,
					"results": [
						{"id": "01HXB2", "invoice_xml_location_path": None},
						{"id": "01HXB1", "invoice_xml_location_path": "s3://bucket/org/b1.xml"},
					],
				},
			),
			*self.download_answers(b"<Invoice>b1</Invoice>"),
		]
		outcome, _transport = perform(Operation.FETCH_INBOUND, answers, cursor="01HXA0", page_size=50)
		self.assertEqual([a.identifier for a in outcome.artifacts], ["01HXB1"])
		self.assertEqual(outcome.event_cursor, "01HXB1")


class TheDeclaration(unittest.TestCase):
	def test_it_never_serves_the_simulator(self):
		self.assertNotIn(Environment.SIMULATION, DECLARATION.environments)

	def test_what_the_api_does_not_offer_stays_undeclared(self):
		self.assertNotIn(Operation.LOOKUP_PARTICIPANT, DECLARATION.operations)
		self.assertNotIn(Operation.WITHDRAW, DECLARATION.operations)

	def test_an_undeclared_operation_is_refused_outright(self):
		adapter = SuntechAdapter()
		call = Call(operation=Operation.WITHDRAW, connection=a_connection())
		with self.assertRaises(ContractError):
			adapter.perform(call, ScriptedTransport([]))

	def test_the_storage_host_is_declared_and_trusted(self):
		self.assertIn(".amazonaws.com", DECLARATION.extra_trusted_hosts)
		policy = policy_for(Environment.SANDBOX, BASE, DECLARATION.extra_trusted_hosts)
		self.assertTrue(policy.trusts("bucket.s3.amazonaws.com"))
		self.assertFalse(policy.trusts("amazonaws.com.attacker.test"))
