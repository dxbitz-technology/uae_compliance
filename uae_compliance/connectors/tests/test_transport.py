"""Checks on the way out.

These are about the two things that would hurt: a request reaching somewhere
it should not, and a secret ending up in a record somebody can read.
"""

from __future__ import annotations

import socket
import unittest

from uae_compliance.connectors.transport import (
	MAX_DIAGNOSTIC_CHARS,
	Attempt,
	BlockedAddress,
	InMemoryRecorder,
	Policy,
	PolicyError,
	Request,
	Response,
	Transport,
	UntrustedHost,
	policy_for,
	redact_headers,
	redact_url,
	safe_traceback,
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

	def test_a_trusted_name_that_resolves_to_an_ordinary_private_address_is_refused(self):
		for address in ("10.1.2.3", "192.168.0.7", "172.16.4.4"):
			transport = self.transport(resolve=resolving_to(address))
			with self.assertRaises(BlockedAddress, msg=address):
				transport.fetch(a_request())

	def test_a_trusted_name_that_resolves_into_the_shared_address_space_is_refused(self):
		# 100.64.0.0/10 is not private as far as the standard library is
		# concerned, and it is where carrier networks and some providers
		# put internal services.
		transport = self.transport(resolve=resolving_to("100.64.1.1"))
		with self.assertRaises(BlockedAddress):
			transport.fetch(a_request())

	def test_a_trusted_name_that_resolves_to_loopback_through_an_ipv6_mapping_is_refused(self):
		transport = self.transport(resolve=resolving_to("::ffff:127.0.0.1", socket.AF_INET6))
		with self.assertRaises(BlockedAddress):
			transport.fetch(a_request())

	def test_a_trusted_name_that_resolves_to_the_metadata_service_over_ipv6_is_refused(self):
		transport = self.transport(resolve=resolving_to("fd00:ec2::254", socket.AF_INET6))
		with self.assertRaises(BlockedAddress):
			transport.fetch(a_request())

	def test_an_address_that_cannot_even_be_read_is_not_called(self):
		transport = self.transport(resolve=resolving_to("not an address at all"))
		with self.assertRaises(BlockedAddress):
			transport.fetch(a_request())


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


class WhatEachEnvironmentIsGiven(unittest.TestCase):
	def test_a_simulation_connection_may_reach_this_machine(self):
		policy = policy_for(Environment.SIMULATION, "http://127.0.0.1:8899/api")
		self.assertTrue(policy.allow_private_addresses)
		self.assertTrue(policy.allow_plain_http)
		self.assertFalse(policy.verify_tls)
		self.assertEqual(policy.trusted_hosts, ("127.0.0.1",))

	def test_a_sandbox_connection_is_somebody_elses_server_and_is_treated_as_one(self):
		policy = policy_for(Environment.SANDBOX, "https://sandbox.example.test/api")
		self.assertTrue(policy.verify_tls)
		self.assertFalse(policy.allow_private_addresses)
		self.assertFalse(policy.allow_plain_http)

	def test_a_production_connection_gets_the_strict_policy(self):
		policy = policy_for(Environment.PRODUCTION, "https://api.example.test/v1")
		self.assertTrue(policy.verify_tls)
		self.assertFalse(policy.allow_private_addresses)
		self.assertEqual(policy.trusted_hosts, ("api.example.test",))

	def test_only_the_address_the_connection_names_is_trusted(self):
		policy = policy_for(Environment.PRODUCTION, "https://api.example.test/v1")
		self.assertFalse(policy.trusts("evil.test"))
		self.assertFalse(policy.trusts("api.example.test.evil.test"))

	def test_a_connection_with_no_host_is_refused_rather_than_trusting_everything(self):
		with self.assertRaises(PolicyError):
			policy_for(Environment.PRODUCTION, "not a url")


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

	def test_a_token_in_an_address_inside_a_header_is_masked_too(self):
		# The header name says nothing secret, so only looking at the name
		# put the credential straight into the log.
		safe = redact_headers({"Location": "https://api.example.test/back?access_token=abc123"})
		self.assertNotIn("abc123", safe["Location"])
		self.assertIn("api.example.test", safe["Location"])

	def test_a_token_in_an_address_inside_a_link_header_is_masked_too(self):
		value = '<https://api.example.test/page?session=zzz9999&n=2>; rel="next"'
		safe = redact_headers({"Link": value})
		self.assertNotIn("zzz9999", safe["Link"])
		self.assertIn("n=2", safe["Link"])

	def test_an_ordinary_header_is_left_alone(self):
		safe = redact_headers({"Content-Type": "application/xml"})
		self.assertEqual(safe["Content-Type"], "application/xml")


# Assembled at run time so they appear only in frame variables, never in a
# source line the traceback quotes.
SAMPLE_TOKEN = "live-token-" + "998877"
SAMPLE_SECRET = "live-client-secret-" + "112233"
SAMPLE_BODY = b"<Invoice>" + b"what the customer bought" + b"</Invoice>"


class WhatAFailureIsAllowedToSay(unittest.TestCase):
	"""The error log is a place people read, so the same rules apply to it."""

	def failure(self):
		"""A send that falls over with the real things in its frames.

		The values are built rather than written in, because a traceback
		carries the source line of each frame and a literal in this file
		would prove the wrong thing.
		"""

		def inner(headers, credentials, body):
			raise OSError("connection reset by peer")

		headers = {"Authorization": "Bearer " + SAMPLE_TOKEN}
		credentials = {"client_secret": SAMPLE_SECRET}
		body = SAMPLE_BODY
		try:
			inner(headers, credentials, body)
		except OSError as error:
			return error
		return None

	def test_nothing_from_inside_the_frames_is_written_down(self):
		text = safe_traceback(self.failure())
		self.assertNotIn(SAMPLE_TOKEN, text)
		self.assertNotIn(SAMPLE_SECRET, text)
		self.assertNotIn("what the customer bought", text)

	def test_where_it_happened_is_still_written_down(self):
		text = safe_traceback(self.failure())
		self.assertIn("OSError", text)
		self.assertIn("connection reset by peer", text)
		self.assertIn("test_transport.py", text)

	def test_a_known_secret_in_the_message_itself_is_masked(self):
		error = RuntimeError("could not sign in with " + SAMPLE_SECRET)
		text = safe_traceback(error, (SAMPLE_SECRET,))
		self.assertNotIn(SAMPLE_SECRET, text)
		self.assertIn("[redacted]", text)

	def test_a_token_in_an_address_in_the_message_is_masked(self):
		error = RuntimeError("POST https://api.example.test/t?api_key=zzz9999 failed")
		text = safe_traceback(error)
		self.assertNotIn("zzz9999", text)

	def test_it_is_bounded(self):
		error = RuntimeError("x" * (MAX_DIAGNOSTIC_CHARS * 2))
		self.assertLessEqual(len(safe_traceback(error)), MAX_DIAGNOSTIC_CHARS + 40)


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
