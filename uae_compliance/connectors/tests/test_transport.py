"""Checks on the way out.

These are about the two things that would hurt: a request reaching somewhere
it should not, and a secret ending up in a record somebody can read.
"""

from __future__ import annotations

import socket
import unittest

from uae_compliance.connectors.transport import (
	Attempt,
	BlockedAddress,
	InMemoryRecorder,
	Policy,
	PolicyError,
	Request,
	Response,
	Transport,
	UntrustedHost,
	redact_headers,
	redact_url,
)
from uae_compliance.domain.connector import Environment, Operation


def a_policy(**kwargs):
	base = {
		"environment": Environment.SANDBOX,
		"trusted_hosts": ("api.example.test",),
	}
	base.update(kwargs)
	return Policy(**base)


def a_request(**kwargs):
	base = {
		"operation": Operation.SUBMIT,
		"method": "POST",
		"url": "https://api.example.test/invoices",
		"label": "submit",
	}
	base.update(kwargs)
	return Request(**base)


def resolving_to(address, family=socket.AF_INET):
	def resolve(host, port):
		return [(family, address)]

	return resolve


class WhereARequestMayGo(unittest.TestCase):
	def setUp(self):
		self.recorder = InMemoryRecorder()

	def transport(self, policy=None, **kwargs):
		return Transport(policy or a_policy(), self.recorder, **kwargs)

	def test_an_untrusted_host_is_refused(self):
		with self.assertRaises(UntrustedHost):
			self.transport().fetch(a_request(url="https://elsewhere.test/invoices"))

	def test_a_refused_request_is_still_recorded_as_an_attempt(self):
		with self.assertRaises(UntrustedHost):
			self.transport().fetch(a_request(url="https://elsewhere.test/invoices"))
		attempt = self.recorder.last()
		self.assertEqual(attempt.result, "Blocked")
		self.assertEqual(attempt.error_code, "TRANSPORT_HOST_NOT_TRUSTED")
		self.assertIsNone(attempt.status)

	def test_plain_http_is_refused_unless_it_was_allowed(self):
		with self.assertRaises(UntrustedHost):
			self.transport().fetch(a_request(url="http://api.example.test/invoices"))

	def test_a_credential_in_the_address_is_refused(self):
		with self.assertRaises(UntrustedHost):
			self.transport().fetch(a_request(url="https://user:pass@api.example.test/invoices"))

	def test_a_trusted_name_that_resolves_to_loopback_is_refused(self):
		transport = self.transport(resolve=resolving_to("127.0.0.1"))
		with self.assertRaises(BlockedAddress):
			transport.fetch(a_request())

	def test_a_trusted_name_that_resolves_to_the_metadata_service_is_refused(self):
		transport = self.transport(resolve=resolving_to("169.254.169.254"))
		with self.assertRaises(BlockedAddress):
			transport.fetch(a_request())

	def test_a_subdomain_entry_does_not_match_a_lookalike(self):
		policy = a_policy(trusted_hosts=(".example.test",))
		self.assertTrue(policy.trusts("api.example.test"))
		self.assertTrue(policy.trusts("example.test"))
		self.assertFalse(policy.trusts("example.test.attacker.invalid"))


class WhatProductionMayBeConfiguredToDo(unittest.TestCase):
	def test_production_cannot_be_allowed_to_reach_private_addresses(self):
		with self.assertRaises(PolicyError):
			a_policy(environment=Environment.PRODUCTION, allow_private_addresses=True)

	def test_production_cannot_be_allowed_to_drop_to_plain_http(self):
		with self.assertRaises(PolicyError):
			a_policy(environment=Environment.PRODUCTION, allow_plain_http=True)

	def test_production_cannot_be_allowed_to_skip_certificate_checks(self):
		with self.assertRaises(PolicyError):
			a_policy(environment=Environment.PRODUCTION, verify_tls=False)

	def test_a_simulation_policy_may_reach_loopback(self):
		policy = a_policy(
			environment=Environment.SIMULATION,
			trusted_hosts=("localhost",),
			allow_private_addresses=True,
			allow_plain_http=True,
		)
		self.assertTrue(policy.trusts("localhost"))

	def test_a_transport_needs_somewhere_it_is_allowed_to_go(self):
		with self.assertRaises(PolicyError):
			a_policy(trusted_hosts=())


class WhatGetsWrittenDown(unittest.TestCase):
	def test_a_credential_header_never_reaches_the_record(self):
		safe = redact_headers({"Authorization": "Bearer sim_abc123", "Accept": "application/json"})
		self.assertEqual(safe["Authorization"], "[redacted]")
		self.assertEqual(safe["Accept"], "application/json")

	def test_a_header_that_merely_sounds_like_a_credential_is_redacted_too(self):
		safe = redact_headers({"X-Provider-Session-Token": "abc"})
		self.assertEqual(safe["X-Provider-Session-Token"], "[redacted]")

	def test_a_known_secret_is_masked_wherever_it_appears(self):
		safe = redact_headers({"X-Trace": "call for sim_secret_value ok"}, ("sim_secret_value",))
		self.assertNotIn("sim_secret_value", safe["X-Trace"])

	def test_a_token_in_the_query_string_is_masked(self):
		safe = redact_url("https://api.example.test/invoices?access_token=abc123&page=2")
		self.assertNotIn("abc123", safe)
		self.assertIn("page=2", safe)

	def test_user_information_is_dropped_from_a_recorded_address(self):
		safe = redact_url("https://user:pass@api.example.test/invoices")
		self.assertNotIn("pass", safe)
		self.assertIn("api.example.test", safe)


class WhatTheProviderSaidAboutWaiting(unittest.TestCase):
	def response(self, headers):
		return Response(status=429, headers=headers, body=b"", url="", diagnostic_ref="a", elapsed_ms=1)

	def test_a_plain_number_of_seconds(self):
		self.assertEqual(self.response({"Retry-After": "90"}).retry_after_seconds(), 90)

	def test_a_date_is_turned_into_a_wait(self):
		when = "Wed, 21 Oct 2026 07:28:00 GMT"
		seconds = self.response({"Retry-After": when}).retry_after_seconds(now=1792567620.0)
		self.assertEqual(seconds, 60)

	def test_nothing_at_all(self):
		self.assertIsNone(self.response({}).retry_after_seconds())


class WhatTheRecorderIsAllowedToBe(unittest.TestCase):
	def test_the_in_memory_recorder_answers_the_protocol(self):
		from uae_compliance.connectors.transport import Recorder

		self.assertIsInstance(InMemoryRecorder(), Recorder)

	def test_it_hands_back_a_reference_for_each_attempt(self):
		recorder = InMemoryRecorder()
		blank = Attempt(
			operation="submit",
			label="submit",
			correlation=None,
			connection=None,
			environment="Simulation",
			method="POST",
			url="https://api.example.test/invoices",
			request_headers={},
			request_digest=None,
			request_bytes=0,
			status=200,
			response_headers={},
			response_digest=None,
			response_bytes=0,
			snippet="",
			started_at="2026-09-18T00:00:00+00:00",
			elapsed_ms=1,
			result="Completed",
		)
		self.assertEqual(recorder.record(blank), "attempt-1")
		self.assertEqual(recorder.record(blank), "attempt-2")


if __name__ == "__main__":
	unittest.main()
