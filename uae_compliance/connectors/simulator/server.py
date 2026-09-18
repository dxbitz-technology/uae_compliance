"""A provider that is not there, answered over real HTTP.

It listens on a socket, reads a request, and writes a response. Nothing is
stubbed out and no method is patched, so what the adapters exercise is the
same code path they would use against a real provider: sockets, deadlines,
status codes, headers, a dropped connection.

It answers quickly. A document is accepted and stored before the caller's
deadline, and what becomes of it afterwards is a separate question that the
caller has to come back and ask. Anything that pretended to finish inside the
send would hide the whole problem this app exists to handle.

Everything it issues says Simulation on it. Credentials have to start with
`sim_` and the identifiers it hands out start with `SIM-`, which a Production
connection refuses. It listens on loopback and it will only deliver a callback
to loopback, so it cannot be turned into a way of reaching anything else.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from uae_compliance.connectors.simulator.behaviour import (
	FULL,
	SETTLEMENTS,
	VALIDATION_ERRORS,
	Behaviour,
	Profile,
)
from uae_compliance.connectors.simulator.store import ACCEPTED_LABEL, ENVIRONMENT, Store

# A demo credential and nothing else. The prefix is what stops a simulation
# client from being pasted into a Production connection.
CREDENTIAL_PREFIX = "sim_"

MAX_REQUEST_BYTES = 2 * 1024 * 1024

LOOPBACK = ("127.0.0.1", "::1", "localhost")


class RequestTooLarge(Exception):
	"""The caller sent more than the simulator will read."""


class Simulator:
	"""The provider's behaviour, with no HTTP in it.

	The handler below turns requests into calls on this object. Keeping them
	apart means a test can set up a document without going through a socket,
	and the behaviour can be read without reading a request parser.
	"""

	def __init__(self, store: Store, profile: Profile = FULL, callback_url: str | None = None):
		self.store = store
		self.profile = profile
		self.callback_url = callback_url
		self.delivered_callbacks: list[dict] = []
		self._planned: dict[str, Behaviour] = {}
		self._lock = threading.Lock()

	def plan(self, number: str, behaviour: Behaviour) -> None:
		"""Say what happens to the next document carrying this number."""
		with self._lock:
			self._planned[number] = behaviour

	def behaviour_for(self, number: str | None) -> Behaviour:
		with self._lock:
			return self._planned.get(number or "", Behaviour.ACCEPT)

	def authenticate(self, client_id: str, client_secret: str, seconds: float | None = None):
		if not client_id.startswith(CREDENTIAL_PREFIX) or not client_secret.startswith(CREDENTIAL_PREFIX):
			return None
		token, expires_at = self.store.issue_token(
			client_id, self.profile.token_seconds if seconds is None else seconds
		)
		return {
			"access_token": token,
			"token_type": "Bearer",
			"expires_in": int(expires_at - time.time()),
			"environment": ENVIRONMENT,
		}

	def accept(self, client_id, key, number, media_type, payload, digest):
		"""Take the document in, quickly, and say what to do about answering.

		Returns the document and the behaviour. Whether the caller ever sees
		that answer is the handler's problem, which is the honest division:
		the provider has the document either way.
		"""
		behaviour = self.behaviour_for(number)
		if behaviour is Behaviour.REJECT_VALIDATION:
			return None, behaviour
		if self.profile.honours_idempotency and key:
			existing = self.store.find_by_key(client_id, key)
			if existing:
				return existing, behaviour
		document = self.store.add_document(
			client_id=client_id,
			idempotency_key=key if self.profile.honours_idempotency else None,
			number=number,
			media_type=media_type,
			digest=digest,
			payload=payload,
			behaviour=behaviour.value,
		)
		if self.profile.serves_artifacts and behaviour is not Behaviour.MISSING_ARTIFACT:
			self.store.add_artifact(
				document.id,
				"receipt",
				"text/plain",
				# Evidence says what it is on its face, so a copy of it that
				# escapes a test cannot be mistaken for the real thing.
				f"{ACCEPTED_LABEL}\n{ENVIRONMENT}\n{document.id}\n{number or ''}\n".encode(),
			)
		return document, behaviour

	def settled(self, identifier: str):
		"""The document as it stands, moved on if its time has come.

		A status read is what advances it. Nothing sleeps and no thread waits,
		so a test never has to pause to see the end state.
		"""
		document = self.store.get(identifier)
		if document is None or document.settled:
			return document
		if document.settle_at and time.time() < document.settle_at:
			return document
		behaviour = Behaviour(document.behaviour)
		status, exchange, reporting = SETTLEMENTS[behaviour]
		return self.store.settle(identifier, status, exchange, reporting)

	def events_for(self, document, behaviour: Behaviour) -> list[dict]:
		"""The callbacks this behaviour sends, in the order they go out.

		Received order is not event order, which is why the reordered case
		exists: the sequence numbers say what really happened and the arrival
		order does not.
		"""
		status, exchange, reporting = SETTLEMENTS[behaviour]
		# The store moves with the events, so what a caller is told and what it
		# would read back never disagree.
		self.settled(document.id)
		received = self.store.add_event(
			document.id,
			1,
			"invoice.received",
			{"status": "Processing", "c3_mls_status": "pending", "c5_mls_status": "pending"},
		)
		updated = self.store.add_event(
			document.id,
			2,
			"invoice.updated",
			{"status": status, "c3_mls_status": exchange, "c5_mls_status": reporting},
		)
		if behaviour is Behaviour.DUPLICATE_CALLBACKS:
			return [received, updated, updated]
		if behaviour is Behaviour.REORDERED_CALLBACKS:
			return [updated, received]
		return [received, updated]

	def deliver(self, events) -> None:
		"""Post the callbacks to whatever registered for them.

		Loopback only. A simulator that would post anywhere is a way of
		reaching anywhere.
		"""
		if not self.callback_url:
			self.delivered_callbacks.extend(events)
			return
		parts = urlsplit(self.callback_url)
		if parts.hostname not in LOOPBACK:
			raise ValueError("the simulator delivers callbacks to this machine only")
		for event in events:
			body = json.dumps(event).encode()
			connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
			try:
				connection.request(
					"POST",
					parts.path or "/",
					body,
					{"Content-Type": "application/json", "Content-Length": str(len(body))},
				)
				connection.getresponse().read()
			finally:
				connection.close()
			self.delivered_callbacks.append(event)


class _Handler(BaseHTTPRequestHandler):
	protocol_version = "HTTP/1.1"

	# The test output is for the test, not for a web server's access log.
	def log_message(self, fmt, *args):
		pass

	@property
	def simulator(self) -> Simulator:
		return self.server.simulator

	def do_POST(self):
		self._route("POST")

	def do_GET(self):
		self._route("GET")

	def _route(self, method):
		parts = urlsplit(self.path)
		path = parts.path.rstrip("/") or "/"
		query = parse_qs(parts.query)
		try:
			if method == "POST" and path == "/api/v1/oauth/token":
				return self._token()
			if method == "POST" and path == "/api/v1/oauth/token/refresh":
				return self._token()
			if method == "POST" and path == "/api/v1/invoices":
				return self._submit()
			if method == "GET" and path == "/api/v1/invoices":
				return self._list(query)
			if method == "GET" and path.startswith("/api/v1/invoices/"):
				return self._status(path.rsplit("/", 1)[-1])
			if method == "POST" and path == "/api/v1/documents/download":
				return self._download()
			self._json(404, {"error": "no such endpoint", "environment": ENVIRONMENT})
		except RequestTooLarge:
			self._json(413, {"error": "too large", "environment": ENVIRONMENT})
		except Exception as error:
			# A simulator that dies quietly would look like a network fault and
			# send somebody hunting in the wrong place.
			self._json(500, {"error": f"{type(error).__name__}: {error}", "environment": ENVIRONMENT})

	def _body(self) -> bytes:
		length = int(self.headers.get("Content-Length") or 0)
		if length > MAX_REQUEST_BYTES:
			raise RequestTooLarge(str(length))
		return self.rfile.read(length) if length else b""

	def _json(self, status: int, payload: dict, headers: dict | None = None):
		body = json.dumps(payload).encode()
		self.send_response(status)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(body)))
		self.send_header("X-Simulation", ENVIRONMENT)
		for key, value in (headers or {}).items():
			self.send_header(key, value)
		self.end_headers()
		self.wfile.write(body)

	def _client(self) -> str | None:
		raw = self.headers.get("Authorization") or ""
		if not raw.startswith("Bearer "):
			return None
		return self.simulator.store.client_for(raw[7:].strip())

	def _needs_client(self) -> str | None:
		client = self._client()
		if client is None:
			self._json(
				401,
				{"error": "token_expired", "detail": "Sign in again", "environment": ENVIRONMENT},
			)
		return client

	def _token(self):
		payload = _read_json(self._body())
		answer = self.simulator.authenticate(
			str(payload.get("client_id") or ""),
			str(payload.get("client_secret") or ""),
			seconds=payload.get("expires_in"),
		)
		if answer is None:
			return self._json(401, {"error": "invalid_client", "environment": ENVIRONMENT})
		return self._json(200, answer)

	def _submit(self):
		client = self._needs_client()
		if client is None:
			return None
		raw = self._body()
		media_type = self.headers.get("Content-Type", "")
		key = self.headers.get("Idempotency-Key")
		number = _number_in(raw, media_type)
		simulator = self.simulator
		behaviour = simulator.behaviour_for(number)

		if behaviour is Behaviour.RATE_LIMIT:
			return self._json(
				429,
				{"error": "rate_limited", "environment": ENVIRONMENT},
				{"Retry-After": str(simulator.profile.retry_after_seconds)},
			)

		existing = None
		if simulator.profile.honours_idempotency and key:
			existing = simulator.store.find_by_key(client, key)

		document, behaviour = simulator.accept(client, key, number, media_type, raw, _digest_of(self.headers))
		if document is None:
			return self._json(
				422,
				{
					"status": "Rejected",
					"errors": list(VALIDATION_ERRORS),
					"status_label": ACCEPTED_LABEL,
					"environment": ENVIRONMENT,
				},
			)

		if behaviour is Behaviour.CALLBACK_BEFORE_RESPONSE:
			# The callback goes out first on purpose. An event about a document
			# the caller has not been told about yet has to be kept and matched
			# up later.
			simulator.deliver(simulator.events_for(document, behaviour))

		if behaviour is Behaviour.LOSE_RESPONSE:
			# The document is stored. The caller gets nothing, and cannot know
			# whether it arrived. This is the case the whole contract is for.
			self.close_connection = True
			return None

		body = document.as_json()
		body["duplicate"] = existing is not None
		if behaviour in (Behaviour.DUPLICATE_CALLBACKS, Behaviour.REORDERED_CALLBACKS):
			simulator.deliver(simulator.events_for(document, behaviour))
		return self._json(200 if existing else 201, body)

	def _status(self, identifier):
		client = self._needs_client()
		if client is None:
			return None
		document = self.simulator.settled(identifier)
		if document is None or document.client_id != client:
			return self._json(404, {"error": "not_found", "environment": ENVIRONMENT})
		body = document.as_json()
		body["artifacts"] = [
			{"kind": row["kind"], "identifier": row["identifier"], "media_type": row["media_type"]}
			for row in self.simulator.store.artifacts_of(document.id)
		]
		if Behaviour(document.behaviour) is Behaviour.MISSING_ARTIFACT:
			# The provider says the evidence exists and cannot produce it. A
			# real one does this, and it must not be read as the document
			# having failed.
			body["artifacts"] = [
				{"kind": "receipt", "identifier": f"{document.id}/receipt", "media_type": "text/plain"}
			]
		if Behaviour(document.behaviour) is Behaviour.REJECT_VALIDATION:
			body["errors"] = list(VALIDATION_ERRORS)
		return self._json(200, body)

	def _list(self, query):
		client = self._needs_client()
		if client is None:
			return None
		simulator = self.simulator
		key = _one(query, "idempotency_key")
		number = _one(query, "number")
		if (key or number) and not simulator.profile.allows_lookup:
			# Nothing to search by. An ambiguous send against this provider
			# stays ambiguous, which the app has to live with.
			return self._json(
				501,
				{"error": "lookup_not_supported", "environment": ENVIRONMENT},
			)
		if key:
			found = simulator.store.find_by_key(client, key)
			results = [found] if found else []
			return self._json(200, {"results": [d.as_json() for d in results], "next": None})
		if number:
			results = simulator.store.find_by_number(client, number)
			return self._json(200, {"results": [d.as_json() for d in results], "next": None})
		limit = int(_one(query, "limit") or simulator.profile.page_size)
		page, cursor = simulator.store.page(client, _one(query, "cursor"), limit)
		return self._json(
			200,
			{
				"results": [simulator.settled(d.id).as_json() for d in page],
				"next": cursor,
				"environment": ENVIRONMENT,
			},
		)

	def _download(self):
		client = self._needs_client()
		if client is None:
			return None
		payload = _read_json(self._body())
		identifier = str(payload.get("uri") or "")
		if not self.simulator.profile.serves_artifacts:
			return self._json(501, {"error": "artifacts_not_supported", "environment": ENVIRONMENT})
		row = self.simulator.store.artifact(identifier)
		if row is None:
			return self._json(404, {"error": "artifact_missing", "environment": ENVIRONMENT})
		body = bytes(row["body"])
		self.send_response(200)
		self.send_header("Content-Type", row["media_type"])
		self.send_header("Content-Length", str(len(body)))
		self.send_header("X-Simulation", ENVIRONMENT)
		self.end_headers()
		self.wfile.write(body)
		return None


class SimulatorServer:
	"""The simulator on a real socket, on loopback, on a port the machine picks."""

	def __init__(self, simulator: Simulator, host: str = "127.0.0.1", port: int = 0):
		if host not in LOOPBACK:
			raise ValueError("the simulator listens on this machine only")
		self._server = ThreadingHTTPServer((host, port), _Handler)
		self._server.simulator = simulator
		self._server.daemon_threads = True
		self._thread = None
		self.simulator = simulator

	@property
	def port(self) -> int:
		return self._server.server_address[1]

	@property
	def base_url(self) -> str:
		return f"http://127.0.0.1:{self.port}/api/v1"

	def start(self) -> "SimulatorServer":
		# A short poll interval, because the default one makes every shutdown
		# wait half a second and a test suite pays for that many times over.
		self._thread = threading.Thread(target=self._server.serve_forever, args=(0.05,), daemon=True)
		self._thread.start()
		return self

	def wait(self) -> None:
		if self._thread:
			self._thread.join()

	def stop(self) -> None:
		self._server.shutdown()
		self._server.server_close()
		if self._thread:
			self._thread.join(timeout=5)

	def __enter__(self):
		return self.start()

	def __exit__(self, *args):
		self.stop()


class CallbackSink:
	"""Somewhere for the simulator to post callbacks, so a test can see what arrived."""

	def __init__(self, host: str = "127.0.0.1", port: int = 0):
		self.received: list[dict] = []
		sink = self

		class Handler(BaseHTTPRequestHandler):
			protocol_version = "HTTP/1.1"

			def log_message(self, fmt, *args):
				pass

			def do_POST(self):
				length = int(self.headers.get("Content-Length") or 0)
				sink.received.append(_read_json(self.rfile.read(length)))
				self.send_response(204)
				self.send_header("Content-Length", "0")
				self.end_headers()

		self._server = ThreadingHTTPServer((host, port), Handler)
		self._server.daemon_threads = True
		self._thread = None

	@property
	def url(self) -> str:
		return f"http://127.0.0.1:{self._server.server_address[1]}/callback"

	def start(self) -> "CallbackSink":
		self._thread = threading.Thread(target=self._server.serve_forever, args=(0.05,), daemon=True)
		self._thread.start()
		return self

	def stop(self) -> None:
		self._server.shutdown()
		self._server.server_close()
		if self._thread:
			self._thread.join(timeout=5)

	def __enter__(self):
		return self.start()

	def __exit__(self, *args):
		self.stop()


def _read_json(raw: bytes) -> dict:
	if not raw:
		return {}
	try:
		value = json.loads(raw.decode("utf-8"))
	except UnicodeDecodeError, ValueError:
		return {}
	return value if isinstance(value, dict) else {}


def _one(query, name):
	values = query.get(name)
	return values[0] if values else None


def _digest_of(headers) -> str | None:
	return headers.get("X-Content-Digest")


def _number_in(raw: bytes, media_type: str) -> str | None:
	"""Find the document number, whatever shape the provider was sent.

	The simulator has to work for both test adapters, so it reads the number
	out of JSON and out of XML. A real provider parses its own format; this
	one has to parse two, which is itself a reminder that they are not the
	same thing.
	"""
	if "json" in media_type:
		return _read_json(raw).get("invoice_number") or _read_json(raw).get("number")
	text = raw.decode("utf-8", "replace")
	start = text.find("<cbc:ID>")
	if start == -1:
		return None
	end = text.find("</cbc:ID>", start)
	return text[start + len("<cbc:ID>") : end].strip() or None
