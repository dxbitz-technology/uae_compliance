"""Checks that the simulator can actually produce the awkward endings.

Every one of these goes over a real socket through the audited transport, so
what is being checked is the whole boundary and not a mock. The point is not
that the simulator works. It is that the endings the app has to survive can be
produced on demand, because none of them can be arranged against a real
provider.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uae_compliance.connectors.simulator import (
	ACCEPTED_LABEL,
	BARE,
	ENVIRONMENT,
	Behaviour,
	CallbackSink,
	Simulator,
	SimulatorServer,
	Store,
)
from uae_compliance.connectors.transport import InMemoryRecorder, Policy, Request, Transport, TransportError
from uae_compliance.domain.connector import Environment, Operation

CLIENT = {"client_id": "sim_client", "client_secret": "sim_secret_value"}


def a_policy():
	return Policy(
		environment=Environment.SIMULATION,
		trusted_hosts=("127.0.0.1",),
		allow_plain_http=True,
		allow_private_addresses=True,
		connect_timeout=5.0,
		read_timeout=5.0,
	)


def an_invoice(number="SINV-0001"):
	return json.dumps({"invoice_number": number, "total": "189.00"}).encode()


class SimulatorCase(unittest.TestCase):
	"""One simulator on a real port, with a store that is a file on disk."""

	profile = None
	callback = False

	def setUp(self):
		self.folder = tempfile.TemporaryDirectory()
		self.path = str(Path(self.folder.name) / "simulator.db")
		self.sink = None
		callback_url = None
		if self.callback:
			self.sink = CallbackSink().start()
			callback_url = self.sink.url
		self.store = Store(self.path)
		arguments = [self.store]
		if self.profile:
			arguments.append(self.profile)
		self.simulator = Simulator(*arguments, callback_url=callback_url)
		self.server = SimulatorServer(self.simulator).start()
		self.recorder = InMemoryRecorder()
		self.transport = Transport(a_policy(), self.recorder)
		self.token = None

	def tearDown(self):
		self.server.stop()
		if self.sink:
			self.sink.stop()
		self.store.close()
		self.folder.cleanup()

	def url(self, path):
		return f"{self.server.base_url}{path}"

	def send(self, method, path, body=None, headers=None, operation=Operation.SUBMIT):
		payload = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
		sending = {"Content-Type": "application/json"}
		if payload is not None:
			sending["Content-Length"] = str(len(payload))
		if self.token:
			sending["Authorization"] = f"Bearer {self.token}"
		sending.update(headers or {})
		return self.transport.fetch(
			Request(
				operation=operation,
				method=method,
				url=self.url(path),
				headers=sending,
				body=payload,
				secrets=(CLIENT["client_secret"], self.token or ""),
				label=path,
			)
		)

	def sign_in(self, **extra):
		response = self.send("POST", "/oauth/token", {**CLIENT, **extra}, operation=Operation.AUTHENTICATE)
		self.assertEqual(response.status, 200)
		body = json.loads(response.body)
		self.token = body["access_token"]
		return body

	def submit(self, number="SINV-0001", key="key-1", **headers):
		return self.send("POST", "/invoices", an_invoice(number), {"Idempotency-Key": key, **headers})


class SigningIn(SimulatorCase):
	def test_a_token_says_it_is_a_simulation_one(self):
		body = self.sign_in()
		self.assertTrue(body["access_token"].startswith("sim_tok_"))
		self.assertEqual(body["environment"], ENVIRONMENT)

	def test_a_credential_that_is_not_a_simulation_one_is_refused(self):
		response = self.send(
			"POST",
			"/oauth/token",
			{"client_id": "real_client", "client_secret": "real_secret"},
			operation=Operation.AUTHENTICATE,
		)
		self.assertEqual(response.status, 401)

	def test_sending_without_a_token_is_refused(self):
		self.assertEqual(self.submit().status, 401)

	def test_an_expired_token_is_refused_and_says_so(self):
		self.sign_in()
		self.store.expire_tokens()
		response = self.submit()
		self.assertEqual(response.status, 401)
		self.assertEqual(json.loads(response.body)["error"], "token_expired")

	def test_signing_in_again_produces_a_usable_token(self):
		self.sign_in()
		self.store.expire_tokens()
		self.sign_in()
		self.assertEqual(self.submit().status, 201)


class TakingADocument(SimulatorCase):
	def setUp(self):
		super().setUp()
		self.sign_in()

	def test_a_document_is_accepted_and_identified_as_a_simulation(self):
		response = self.submit()
		body = json.loads(response.body)
		self.assertEqual(response.status, 201)
		self.assertTrue(body["id"].startswith("SIM-"))
		self.assertEqual(body["environment"], ENVIRONMENT)
		self.assertEqual(body["status_label"], ACCEPTED_LABEL)

	def test_it_is_accepted_before_it_is_finished_with(self):
		body = json.loads(self.submit().body)
		self.assertEqual(body["status"], "Processing")

	def test_the_same_key_twice_returns_the_first_document(self):
		first = json.loads(self.submit().body)
		again = self.submit()
		self.assertEqual(again.status, 200)
		body = json.loads(again.body)
		self.assertEqual(body["id"], first["id"])
		self.assertTrue(body["duplicate"])

	def test_a_rejected_document_comes_back_with_the_provider_own_codes(self):
		self.simulator.plan("SINV-BAD", Behaviour.REJECT_VALIDATION)
		response = self.submit("SINV-BAD", key="key-bad")
		self.assertEqual(response.status, 422)
		codes = [error["code"] for error in json.loads(response.body)["errors"]]
		self.assertIn("AE-VAT-0012", codes)

	def test_a_rate_limit_says_how_long_to_wait(self):
		self.simulator.plan("SINV-BUSY", Behaviour.RATE_LIMIT)
		response = self.submit("SINV-BUSY", key="key-busy")
		self.assertEqual(response.status, 429)
		self.assertEqual(response.retry_after_seconds(), 30)


class WhenTheAnswerNeverArrives(SimulatorCase):
	def setUp(self):
		super().setUp()
		self.sign_in()

	def test_the_connection_drops_and_the_caller_learns_nothing(self):
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		with self.assertRaises(TransportError):
			self.submit("SINV-LOST", key="key-lost")

	def test_the_document_is_there_all_the_same(self):
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		with self.assertRaises(TransportError):
			self.submit("SINV-LOST", key="key-lost")
		found = self.store.find_by_key("sim_client", "key-lost")
		self.assertIsNotNone(found)

	def test_it_survives_the_worker_that_sent_it(self):
		"""A crash mid-flight is a worker that never came back, not a lost document.

		The store is a file, so a second reader opening the same file sees what
		the first one never found out.
		"""
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		with self.assertRaises(TransportError):
			self.submit("SINV-LOST", key="key-lost")
		after_the_crash = Store(self.path)
		try:
			found = after_the_crash.find_by_key("sim_client", "key-lost")
			self.assertIsNotNone(found)
			self.assertEqual(found.number, "SINV-LOST")
		finally:
			after_the_crash.close()

	def test_the_ambiguity_is_settled_by_looking_the_key_up(self):
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		with self.assertRaises(TransportError):
			self.submit("SINV-LOST", key="key-lost")
		response = self.send("GET", "/invoices?idempotency_key=key-lost", operation=Operation.FIND_SUBMISSION)
		results = json.loads(response.body)["results"]
		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]["number"], "SINV-LOST")


class HowItEnds(SimulatorCase):
	def setUp(self):
		super().setUp()
		self.sign_in()

	def status_of(self, number, key, behaviour):
		self.simulator.plan(number, behaviour)
		identifier = json.loads(self.submit(number, key=key).body)["id"]
		response = self.send("GET", f"/invoices/{identifier}", operation=Operation.GET_STATUS)
		return json.loads(response.body)

	def test_delivered_and_accepted(self):
		body = self.status_of("SINV-OK", "key-ok", Behaviour.ACCEPT)
		self.assertEqual(body["status"], "Completed")
		self.assertEqual(body["c3_mls_status"], "delivered")
		self.assertEqual(body["c5_mls_status"], "accepted")

	def test_delivered_but_not_reported(self):
		body = self.status_of("SINV-HALF", "key-half", Behaviour.DELIVERED_REPORTING_FAILED)
		self.assertEqual(body["c3_mls_status"], "delivered")
		self.assertEqual(body["c5_mls_status"], "rejected")

	def test_reported_but_not_delivered(self):
		body = self.status_of("SINV-OTHER", "key-other", Behaviour.REPORTED_DELIVERY_FAILED)
		self.assertEqual(body["c3_mls_status"], "rejected")
		self.assertEqual(body["c5_mls_status"], "accepted")

	def test_an_artifact_can_be_fetched(self):
		self.status_of("SINV-ART", "key-art", Behaviour.ACCEPT)
		found = self.store.find_by_number("sim_client", "SINV-ART")[0]
		response = self.send(
			"POST",
			"/documents/download",
			{"uri": f"{found.id}/receipt"},
			operation=Operation.FETCH_ARTIFACT,
		)
		self.assertEqual(response.status, 200)
		self.assertIn(ACCEPTED_LABEL, response.body.decode())

	def test_an_artifact_the_provider_promised_can_be_missing(self):
		body = self.status_of("SINV-GONE", "key-gone", Behaviour.MISSING_ARTIFACT)
		self.assertEqual(body["status"], "Completed")
		reference = body["artifacts"][0]["identifier"]
		response = self.send(
			"POST", "/documents/download", {"uri": reference}, operation=Operation.FETCH_ARTIFACT
		)
		self.assertEqual(response.status, 404)


class WalkingThePages(SimulatorCase):
	def setUp(self):
		super().setUp()
		self.sign_in()

	def test_a_cursor_walks_every_document_once(self):
		for index in range(5):
			self.submit(f"SINV-{index}", key=f"key-{index}")
		seen = []
		cursor = None
		for _ in range(10):
			path = "/invoices?direction=2" + (f"&cursor={cursor}" if cursor else "")
			body = json.loads(self.send("GET", path, operation=Operation.FETCH_INBOUND).body)
			seen.extend(item["id"] for item in body["results"])
			cursor = body["next"]
			if not cursor:
				break
		self.assertEqual(len(seen), 5)
		self.assertEqual(len(set(seen)), 5)


class WhenCallbacksArrive(SimulatorCase):
	callback = True

	def setUp(self):
		super().setUp()
		self.sign_in()

	def test_one_can_arrive_before_the_answer_to_the_send(self):
		self.simulator.plan("SINV-EARLY", Behaviour.CALLBACK_BEFORE_RESPONSE)
		response = self.submit("SINV-EARLY", key="key-early")
		identifier = json.loads(response.body)["id"]
		# The sink already held the event by the time the response was written.
		self.assertTrue(self.sink.received)
		self.assertEqual(self.sink.received[0]["invoice_id"], identifier)

	def test_the_same_event_can_arrive_twice(self):
		self.simulator.plan("SINV-TWICE", Behaviour.DUPLICATE_CALLBACKS)
		self.submit("SINV-TWICE", key="key-twice")
		identifiers = [event["event_id"] for event in self.sink.received]
		self.assertNotEqual(len(identifiers), len(set(identifiers)))

	def test_they_can_arrive_in_the_wrong_order(self):
		self.simulator.plan("SINV-BACK", Behaviour.REORDERED_CALLBACKS)
		self.submit("SINV-BACK", key="key-back")
		order = [event["sequence"] for event in self.sink.received]
		self.assertEqual(order, [2, 1])

	def test_every_event_says_it_is_a_simulation(self):
		self.simulator.plan("SINV-MARK", Behaviour.DUPLICATE_CALLBACKS)
		self.submit("SINV-MARK", key="key-mark")
		for event in self.sink.received:
			self.assertEqual(event["environment"], ENVIRONMENT)
			self.assertEqual(event["status_label"], ACCEPTED_LABEL)


class AProviderThatPromisesNothing(SimulatorCase):
	profile = BARE

	def setUp(self):
		super().setUp()
		self.sign_in()

	def test_the_same_key_twice_makes_two_documents(self):
		first = json.loads(self.submit().body)
		second = json.loads(self.submit().body)
		self.assertNotEqual(first["id"], second["id"])

	def test_there_is_nothing_to_look_a_lost_send_up_by(self):
		response = self.send("GET", "/invoices?idempotency_key=key-1", operation=Operation.FIND_SUBMISSION)
		self.assertEqual(response.status, 501)

	def test_it_keeps_no_artifacts(self):
		identifier = json.loads(self.submit().body)["id"]
		response = self.send(
			"POST",
			"/documents/download",
			{"uri": f"{identifier}/receipt"},
			operation=Operation.FETCH_ARTIFACT,
		)
		self.assertEqual(response.status, 501)


class WhatTheRecordShows(SimulatorCase):
	def test_every_exchange_left_an_attempt_with_no_secret_in_it(self):
		self.sign_in()
		self.submit()
		self.assertGreaterEqual(len(self.recorder.attempts), 2)
		for attempt in self.recorder.attempts:
			self.assertEqual(attempt.environment, "Simulation")
			self.assertNotIn(CLIENT["client_secret"], attempt.snippet)
			self.assertNotIn(self.token, attempt.snippet)
			self.assertEqual(attempt.request_headers.get("Authorization", "[redacted]"), "[redacted]")

	def test_the_token_response_never_keeps_the_token(self):
		self.sign_in()
		token_attempt = self.recorder.attempts[0]
		self.assertNotIn(self.token, token_attempt.snippet)
		self.assertIsNotNone(token_attempt.response_digest)


if __name__ == "__main__":
	unittest.main()
