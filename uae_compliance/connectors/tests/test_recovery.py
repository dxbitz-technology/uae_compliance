"""The crash windows, against a provider on a real socket.

Every case here is one of the windows in spec 8.3, played out rather than
argued about. The simulator loses responses and drops connections for real,
so what these exercise is the same code that would run against an ASP.

What they cannot cover is the database half of a window: two workers racing
for one claim, and a result landing after somebody else has taken the work
over. Those need a transaction and live in the site tests.
"""

from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from uae_compliance.connectors.adapters.reference_xml import ReferenceXmlAdapter
from uae_compliance.connectors.adapters.simulated_json import SimulatedJsonAdapter
from uae_compliance.connectors.registry import BusinessRequest, Call, Connection
from uae_compliance.connectors.simulator import BARE, Behaviour, Simulator, SimulatorServer, Store
from uae_compliance.connectors.transport import (
	InMemoryRecorder,
	Policy,
	Request,
	RequestTimedOut,
	Transport,
)
from uae_compliance.domain.connector import (
	Advice,
	AspReceipt,
	Disposition,
	Effect,
	Environment,
	Operation,
)
from uae_compliance.domain.recovery import (
	LEASE_SECONDS,
	REQUESTS_PER_SEND,
	may_believe_it_never_arrived,
)
from uae_compliance.validation.serializer import to_xml
from uae_compliance.validation.tests.test_serializer import an_invoice

CREDENTIALS = {"client_id": "sim_client", "client_secret": "sim_secret_value"}


class AgainstTheSimulator(unittest.TestCase):
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

	def connection(self, provider_key="reference_xml"):
		return Connection(
			provider_key=provider_key,
			connection_id=f"{provider_key} simulation",
			environment=Environment.SIMULATION,
			base_url=self.server.base_url,
			credentials=dict(CREDENTIALS),
		)

	def a_send(self, number, key, connection=None):
		document = an_invoice(number=number)
		return Call(
			operation=Operation.SUBMIT,
			connection=connection or self.connection(),
			document=document,
			request=BusinessRequest(media_type="application/xml", body=to_xml(document)),
			idempotency_key=key,
			correlation=number,
		)

	def documents_for(self, number):
		return self.store.find_by_number("sim_client", number)


class WhenTheAnswerNeverArrives(AgainstTheSimulator):
	"""Spec 8.3: after remote acceptance but before the response."""

	def test_the_provider_has_the_document_even_though_we_were_not_told(self):
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		adapter = ReferenceXmlAdapter()
		outcome = adapter.perform(self.a_send("SINV-LOST", "key-lost"), self.transport)

		self.assertIs(outcome.effect, Effect.UNKNOWN)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.UNKNOWN)
		# The dangerous part. Nothing came back, and the invoice is there.
		self.assertEqual(len(self.documents_for("SINV-LOST")), 1)

	def test_the_next_worker_finds_it_instead_of_sending_it_again(self):
		self.simulator.plan("SINV-LOST", Behaviour.LOSE_RESPONSE)
		adapter = ReferenceXmlAdapter()
		connection = self.connection()
		adapter.perform(self.a_send("SINV-LOST", "key-lost", connection), self.transport)

		found = adapter.perform(
			Call(
				operation=Operation.FIND_SUBMISSION,
				connection=connection,
				idempotency_key="key-lost",
			),
			self.transport,
		)
		self.assertIs(found.acknowledgements.asp_receipt, AspReceipt.RECEIVED)
		self.assertEqual(len(self.documents_for("SINV-LOST")), 1)


class WhenTheSameThingIsSentTwice(AgainstTheSimulator):
	"""Spec I05: a retry uses the same bytes and the same key."""

	def test_a_provider_that_honours_the_key_keeps_one_document(self):
		adapter = ReferenceXmlAdapter()
		connection = self.connection()
		first = adapter.perform(self.a_send("SINV-TWICE", "key-twice", connection), self.transport)
		second = adapter.perform(self.a_send("SINV-TWICE", "key-twice", connection), self.transport)

		self.assertEqual(first.provider_ids["document_id"], second.provider_ids["document_id"])
		self.assertEqual(len(self.documents_for("SINV-TWICE")), 1)

	def test_a_lost_response_followed_by_the_same_key_still_keeps_one(self):
		# The crash window and the retry together. This is the only sequence
		# in which repeating an ambiguous send is ever allowed, and it is
		# allowed because the provider promised the key means something.
		self.simulator.plan("SINV-AGAIN", Behaviour.LOSE_RESPONSE)
		adapter = ReferenceXmlAdapter()
		connection = self.connection()
		adapter.perform(self.a_send("SINV-AGAIN", "key-again", connection), self.transport)

		self.simulator.plan("SINV-AGAIN", Behaviour.ACCEPT)
		adapter.perform(self.a_send("SINV-AGAIN", "key-again", connection), self.transport)
		self.assertEqual(len(self.documents_for("SINV-AGAIN")), 1)


class WhenTheSearchComesBackEmpty(AgainstTheSimulator):
	"""Asking about a document the provider genuinely never got."""

	def test_it_says_not_sent_rather_than_received(self):
		# An empty result is a real answer and it is the opposite one. Read
		# as a receipt it marks an invoice that never left as gone, and then
		# nothing sends it and nothing may correct it.
		outcome = ReferenceXmlAdapter().perform(
			Call(
				operation=Operation.FIND_SUBMISSION,
				connection=self.connection(),
				idempotency_key="never-sent",
			),
			self.transport,
		)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.NOT_SENT)

	def test_and_it_does_not_offer_to_send_the_same_thing_again(self):
		# Whether to send it now is the app's decision with the whole record
		# in front of it, not something an empty search page settles.
		outcome = ReferenceXmlAdapter().perform(
			Call(
				operation=Operation.FIND_SUBMISSION,
				connection=self.connection(),
				idempotency_key="never-sent",
			),
			self.transport,
		)
		self.assertIsNot(outcome.advice, Advice.RETRY_SAME_PAYLOAD)

	def test_a_search_that_did_find_it_still_says_received(self):
		adapter = ReferenceXmlAdapter()
		connection = self.connection()
		adapter.perform(self.a_send("SINV-HERE", "key-here", connection), self.transport)
		outcome = adapter.perform(
			Call(
				operation=Operation.FIND_SUBMISSION,
				connection=connection,
				idempotency_key="key-here",
			),
			self.transport,
		)
		self.assertIs(outcome.acknowledgements.asp_receipt, AspReceipt.RECEIVED)


class WhenAnAnswerMaySettleAnUnknown(AgainstTheSimulator):
	def test_a_lookup_that_worked_and_found_nothing_settles_it(self):
		outcome = ReferenceXmlAdapter().perform(
			Call(
				operation=Operation.FIND_SUBMISSION,
				connection=self.connection(),
				idempotency_key="never-sent",
			),
			self.transport,
		)
		self.assertIs(outcome.disposition, Disposition.SUCCEEDED)
		self.assertTrue(
			may_believe_it_never_arrived(AspReceipt.UNKNOWN.value, answered=True),
		)


class WhenTheProviderPromisesNothing(AgainstTheSimulator):
	"""Spec 8.4: no safe idempotency and no reliable lookup means a person."""

	profile = BARE

	def test_an_ambiguous_send_is_held_rather_than_repeated(self):
		self.simulator.plan("SINV-BARE", Behaviour.LOSE_RESPONSE)
		outcome = SimulatedJsonAdapter().perform(
			Call(
				operation=Operation.SUBMIT,
				connection=self.connection("simulated_json"),
				document=an_invoice(number="SINV-BARE"),
				correlation="SINV-BARE",
			),
			self.transport,
		)
		self.assertIs(outcome.effect, Effect.UNKNOWN)
		self.assertIs(outcome.advice, Advice.HOLD_FOR_PERSON)

	def test_and_repeating_it_really_would_make_a_second_invoice(self):
		# The reason the rule above is not being careful for its own sake.
		# This provider ignores the key, so the same send twice is two legal
		# documents at the other end.
		self.simulator.plan("SINV-BARE", Behaviour.LOSE_RESPONSE)
		adapter = ReferenceXmlAdapter()
		connection = self.connection()
		adapter.perform(self.a_send("SINV-BARE", "key-bare", connection), self.transport)
		self.simulator.plan("SINV-BARE", Behaviour.ACCEPT)
		adapter.perform(self.a_send("SINV-BARE", "key-bare", connection), self.transport)

		self.assertEqual(len(self.documents_for("SINV-BARE")), 2)

	def test_a_lookup_this_provider_refuses_settles_nothing(self):
		# It answers, and the answer is that it does not do lookups. That is
		# not evidence either way, so an Unknown receipt has to survive it.
		outcome = ReferenceXmlAdapter().perform(
			Call(
				operation=Operation.FIND_SUBMISSION,
				connection=self.connection(),
				idempotency_key="key-bare",
			),
			self.transport,
		)
		self.assertIsNot(outcome.disposition, Disposition.SUCCEEDED)
		self.assertIsNot(outcome.acknowledgements.asp_receipt, AspReceipt.RECEIVED)
		self.assertFalse(
			may_believe_it_never_arrived(
				AspReceipt.UNKNOWN.value, answered=outcome.disposition is Disposition.SUCCEEDED
			)
		)


class ADribblingServer:
	"""A server that answers, slowly, one small piece of the body at a time.

	A provider that fails outright is easy. This one is the awkward case: it
	is answering the whole time, so every single read finishes well inside
	the read timeout, and only the whole exchange runs long.
	"""

	def __init__(self, pieces: int = 20, gap: float = 0.2):
		self.pieces = pieces
		self.gap = gap
		self._socket = socket.socket()
		self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		self._socket.bind(("127.0.0.1", 0))
		self._socket.listen(1)
		self._thread = threading.Thread(target=self._serve, daemon=True)

	@property
	def url(self) -> str:
		return f"http://127.0.0.1:{self._socket.getsockname()[1]}/slow"

	def start(self):
		self._thread.start()
		return self

	def stop(self):
		try:
			self._socket.close()
		except OSError:
			pass
		self._thread.join(timeout=5)

	def _serve(self):
		try:
			client, _address = self._socket.accept()
		except OSError:
			return
		try:
			client.recv(65536)
			body = b"x" * 64
			client.sendall(
				b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
				b"Content-Length: " + str(len(body) * self.pieces).encode() + b"\r\n\r\n"
			)
			for _piece in range(self.pieces):
				client.sendall(body)
				time.sleep(self.gap)
		except OSError:
			pass
		finally:
			try:
				client.close()
			except OSError:
				pass

	def __enter__(self):
		return self.start()

	def __exit__(self, *args):
		self.stop()


class HowLongOneCallMayTake(unittest.TestCase):
	def test_the_deadline_covers_the_whole_exchange_and_not_one_read(self):
		# Without this the read timeout is the only limit, and it restarts on
		# every chunk. A provider dribbling four megabytes in sixty four
		# kilobyte pieces could then hold one call open for far longer than
		# the worker's claim on the work, and the claim would run out with
		# the request still in flight.
		with ADribblingServer() as server:
			transport = Transport(
				Policy(
					environment=Environment.SIMULATION,
					trusted_hosts=("127.0.0.1",),
					allow_plain_http=True,
					allow_private_addresses=True,
					connect_timeout=2.0,
					read_timeout=2.0,
					total_deadline=0.5,
				),
				InMemoryRecorder(),
			)
			started = time.monotonic()
			with self.assertRaises(RequestTimedOut):
				transport.fetch(
					Request(operation=Operation.GET_STATUS, method="GET", url=server.url, label="slow")
				)
			self.assertLess(time.monotonic() - started, 2.0)

	def test_a_claim_outlasts_every_request_one_send_makes(self):
		# A send signs in and then submits, and each of those gets the whole
		# deadline. The claim has to cover both with room to spare, or a
		# worker that is still talking to the provider has its work taken
		# away and reconciliation starts writing to the same row.
		longest = Policy(environment=Environment.SIMULATION, trusted_hosts=("127.0.0.1",)).total_deadline
		self.assertGreater(LEASE_SECONDS, longest * REQUESTS_PER_SEND)


if __name__ == "__main__":
	unittest.main()
