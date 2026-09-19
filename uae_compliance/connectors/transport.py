"""The one way out of this app, and the record of everything that went out.

Every exchange with a provider comes through here: getting a token, sending a
document, polling, walking pages, and downloading an artifact. An adapter
that opened its own socket would leave no attempt behind, so there is nothing
else for an adapter to reach for.

Four rules hold this boundary:

  A request goes only to a host the installation already trusts.
  It has a finite deadline and a bounded response, so nothing hangs and
  nothing fills the disk.
  Nothing secret survives into what gets written down.
  Production cannot be pointed at the machine it runs on.

That last one is the reason the address checks exist. A provider connection
is configuration, and configuration is editable, so a Production connection
that resolves to loopback, to a link-local address, or to a cloud metadata
service would turn the transmission settings into a way to read this server.
The policy refuses to allow it rather than trusting anyone to leave it alone.

The recorder is injected. Tests hold attempts in memory. P05 will hand in one
that writes them to the transmission log.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
import time
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol, runtime_checkable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from uae_compliance.domain.connector import Environment, Operation

REDACTED = "[redacted]"

# Headers that carry a credential whatever their value looks like.
SECRET_HEADERS = frozenset(
	{
		"authorization",
		"proxy-authorization",
		"cookie",
		"set-cookie",
		"x-api-key",
		"api-key",
		"x-auth-token",
		"x-amz-security-token",
	}
)

# Any header or query parameter whose name contains one of these is treated as
# a credential too, because provider naming varies and guessing low is safer.
SECRET_WORDS = (
	"token",
	"secret",
	"password",
	"passwd",
	"credential",
	"signature",
	"apikey",
	"api-key",
	"api_key",
	"session",
	"auth",
)

# Well known metadata endpoints. Most already fall inside the link-local or
# private ranges below; they are named so a reader can see they were thought
# about rather than caught by accident.
METADATA_ADDRESSES = frozenset(
	{
		"169.254.169.254",
		"100.100.100.200",
		"fd00:ec2::254",
	}
)

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Enough of a body to explain a failure, and not enough to become a copy of
# the document. The full bytes are held as evidence elsewhere.
SNIPPET_BYTES = 2000

# Enough of a failure to work out what went wrong, and bounded so one bad
# afternoon cannot fill the error log.
MAX_DIAGNOSTIC_CHARS = 8000

# A web address sitting inside some other piece of text: a Location header, a
# Link header, a line of a response body. The query of one of those carries
# credentials as often as a request does.
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+")


class TransportError(RuntimeError):
	"""An exchange could not be made, or was refused before it was made."""

	code = "TRANSPORT_FAILED"


class PolicyError(ValueError):
	"""The transport was configured in a way that is not safe to run."""

	code = "TRANSPORT_POLICY_INVALID"


class UntrustedHost(TransportError):
	code = "TRANSPORT_HOST_NOT_TRUSTED"


class BlockedAddress(TransportError):
	code = "TRANSPORT_ADDRESS_BLOCKED"


class ResponseTooLarge(TransportError):
	code = "TRANSPORT_RESPONSE_TOO_LARGE"


class TooManyRedirects(TransportError):
	code = "TRANSPORT_TOO_MANY_REDIRECTS"


class RequestTimedOut(TransportError):
	code = "TRANSPORT_TIMED_OUT"


@dataclass(frozen=True)
class Policy:
	"""What this installation lets the transport do.

	`trusted_hosts` is matched exactly and in lower case. A leading dot covers
	subdomains, so `.example.com` allows `api.example.com` and not
	`example.com.attacker.test`.
	"""

	environment: Environment
	trusted_hosts: tuple[str, ...]
	connect_timeout: float = 10.0
	read_timeout: float = 30.0
	total_deadline: float = 120.0
	max_response_bytes: int = 4 * 1024 * 1024
	max_redirects: int = 2
	verify_tls: bool = True
	allow_plain_http: bool = False
	allow_private_addresses: bool = False

	def __post_init__(self):
		if not self.trusted_hosts:
			raise PolicyError("a transport needs at least one trusted host")
		for host in self.trusted_hosts:
			if not host or host != host.strip().lower() or "/" in host:
				raise PolicyError(f"{host!r} is not a plain host name")
		for name in ("connect_timeout", "read_timeout", "total_deadline"):
			value = getattr(self, name)
			if value <= 0:
				raise PolicyError(f"{name} must be a positive number of seconds")
		if self.max_response_bytes <= 0:
			raise PolicyError("a response limit must be positive")
		if self.max_redirects < 0:
			raise PolicyError("a redirect budget cannot be negative")
		if self.environment is Environment.PRODUCTION:
			# Not a default that can be overridden. Production reaching its own
			# host is how provider settings become a way to read this server.
			if self.allow_private_addresses:
				raise PolicyError("Production cannot be allowed to reach private addresses")
			if self.allow_plain_http:
				raise PolicyError("Production cannot be allowed to use plain HTTP")
			if not self.verify_tls:
				raise PolicyError("Production cannot be allowed to skip certificate checks")

	def trusts(self, host: str) -> bool:
		host = (host or "").lower()
		for entry in self.trusted_hosts:
			if entry.startswith("."):
				if host.endswith(entry) or host == entry[1:]:
					return True
			elif host == entry:
				return True
		return False


@dataclass(frozen=True)
class Request:
	"""One exchange an adapter wants to make.

	`secrets` holds the values this request carries that must never be written
	down: the client secret, the current token. They are masked wherever they
	appear before anything reaches the recorder.

	`correlation` ties the several requests of one operation together, so a
	token refresh followed by a send reads as one piece of work later.
	"""

	operation: Operation
	method: str
	url: str
	headers: Mapping[str, str] = field(default_factory=dict)
	body: bytes | None = None
	secrets: tuple[str, ...] = ()
	label: str = ""
	correlation: str | None = None
	connection: str | None = None
	secret_response: bool = False

	def __post_init__(self):
		if not self.method:
			raise PolicyError("a request needs a method")
		if self.body is not None and not isinstance(self.body, bytes):
			raise PolicyError("a request body is bytes, already encoded")
		if self.operation is Operation.AUTHENTICATE:
			# The answer to this one is a credential. Nothing can mask a token
			# we have not seen yet, so the body is never kept at all. Forced
			# here rather than left to each adapter to remember.
			object.__setattr__(self, "secret_response", True)


@dataclass(frozen=True)
class Attempt:
	"""What gets written down about one exchange. Everything here is safe to store."""

	operation: str
	label: str
	correlation: str | None
	connection: str | None
	environment: str
	method: str
	url: str
	request_headers: Mapping[str, str]
	request_digest: str | None
	request_bytes: int
	status: int | None
	response_headers: Mapping[str, str]
	response_digest: str | None
	response_bytes: int
	snippet: str
	started_at: str
	elapsed_ms: int
	result: str
	error_code: str | None = None


@runtime_checkable
class Recorder(Protocol):
	"""Where attempts go. The transport does not care what happens to them.

	`record` returns the reference an outcome can carry so somebody can find
	the attempt again. It must not raise; a recorder that cannot write has to
	fail on its own terms rather than stopping an exchange that already
	happened.
	"""

	def record(self, attempt: Attempt) -> str: ...


class InMemoryRecorder:
	"""The recorder tests use. It keeps attempts and hands back a reference."""

	def __init__(self):
		self.attempts: list[Attempt] = []

	def record(self, attempt: Attempt) -> str:
		self.attempts.append(attempt)
		return f"attempt-{len(self.attempts)}"

	def last(self) -> Attempt:
		return self.attempts[-1]


@dataclass(frozen=True)
class Response:
	"""What came back, with the reference to the attempt that produced it."""

	status: int
	headers: Mapping[str, str]
	body: bytes
	url: str
	diagnostic_ref: str
	elapsed_ms: int

	def header(self, name: str) -> str | None:
		wanted = name.lower()
		for key, value in self.headers.items():
			if key.lower() == wanted:
				return value
		return None

	def retry_after_seconds(self, now: float | None = None) -> int | None:
		"""The provider's own wait, in seconds, in either permitted form."""
		raw = self.header("retry-after")
		if not raw:
			return None
		raw = raw.strip()
		if raw.isdigit():
			return int(raw)
		try:
			when = parsedate_to_datetime(raw)
		except TypeError, ValueError:
			return None
		if when.tzinfo is None:
			when = when.replace(tzinfo=UTC)
		moment = now if now is not None else time.time()
		return max(0, int(when.timestamp() - moment))


def digest(body: bytes | None) -> str | None:
	if body is None:
		return None
	return hashlib.sha256(body).hexdigest()


def mask(text: str, secrets: Sequence[str]) -> str:
	"""Take the known secret values out of a piece of text.

	Short values are left alone. A two character secret would match half the
	response and turn the record into noise.
	"""
	for secret in secrets:
		if secret and len(secret) >= 6:
			text = text.replace(secret, REDACTED)
	return text


def _is_secret_name(name: str) -> bool:
	name = name.lower()
	return name in SECRET_HEADERS or any(word in name for word in SECRET_WORDS)


def redact_url(url: str, secrets: Sequence[str] = ()) -> str:
	"""Drop any user information and mask the query values that name a secret."""
	parts = urlsplit(url)
	netloc = parts.hostname or ""
	if parts.port:
		netloc = f"{netloc}:{parts.port}"
	if parts.username or parts.password:
		netloc = f"{REDACTED}@{netloc}"
	query = parts.query
	if query:
		pairs = [
			(k, REDACTED if _is_secret_name(k) else v) for k, v in parse_qsl(query, keep_blank_values=True)
		]
		query = urlencode(pairs)
	return mask(urlunsplit((parts.scheme, netloc, parts.path, query, "")), secrets)


def redact_text(text: str, secrets: Sequence[str] = ()) -> str:
	"""Clean a piece of free text before it is written down.

	Every address in it goes through the same treatment a request address
	gets. A provider that answers with `Location: .../callback?token=...`
	was putting a credential in the log otherwise, because only the header
	name was being looked at and `location` names nothing secret.
	"""
	return mask(URL_IN_TEXT.sub(lambda found: redact_url(found.group(0), secrets), text), secrets)


def redact_headers(headers: Mapping[str, str], secrets: Sequence[str] = ()) -> dict[str, str]:
	safe = {}
	for key, value in headers.items():
		if _is_secret_name(key):
			safe[key] = REDACTED
		else:
			safe[key] = redact_text(str(value), secrets)
	return safe


def safe_traceback(error: BaseException, secrets: Sequence[str] = ()) -> str:
	"""Where a failure happened, and nothing from inside the frames.

	The framework's own error log renders every local variable of every
	frame when it is handed a title and no message. On this path those
	locals are the request headers, the decrypted provider credentials and
	the whole invoice, so the text is built here and only the frames go in
	it.
	"""
	text = redact_text("".join(traceback.format_exception(error)), secrets)
	if len(text) > MAX_DIAGNOSTIC_CHARS:
		text = text[:MAX_DIAGNOSTIC_CHARS] + "\n[the rest is cut]"
	return text


def _snippet(body: bytes, secrets: Sequence[str]) -> str:
	return redact_text(body[:SNIPPET_BYTES].decode("utf-8", "replace"), secrets)


def _address_is_reachable(address: str, policy: Policy) -> bool:
	if address in METADATA_ADDRESSES:
		return False
	try:
		ip = ipaddress.ip_address(address)
	except ValueError:
		# An address we cannot read is one we cannot check, so it is one we
		# do not call.
		return False
	if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
		return policy.allow_private_addresses and ip.is_loopback
	# `is_private` alone leaves the shared address space at 100.64.0.0/10
	# reachable, which is where carrier networks and some providers put
	# internal services. Anything the standard library does not call global
	# is treated the same as a private address.
	if ip.is_private or not ip.is_global:
		return policy.allow_private_addresses
	return True


def policy_for(environment: Environment, base_url: str) -> Policy:
	"""What one provider connection is allowed to do.

	Only the simulator runs on this machine. A Sandbox is somebody else's
	server reached over the internet with real credentials, so it gets the
	same address rules and the same certificate checks as Production.
	Relaxing both for anything that merely was not Production put sandbox
	credentials one man in the middle away from being read.
	"""
	host = (urlsplit(base_url).hostname or "").lower()
	local = environment is Environment.SIMULATION
	return Policy(
		environment=environment,
		trusted_hosts=(host,),
		allow_plain_http=local,
		allow_private_addresses=local,
		verify_tls=not local,
	)


def _now_text() -> str:
	return datetime.now(UTC).isoformat(timespec="seconds")


class Transport:
	"""The audited way out. One object per connection and per worker call.

	`resolve` and `connect` are seams, so a test can prove a host is refused
	without a name server and without a socket. Nothing in the app passes
	them.
	"""

	def __init__(self, policy: Policy, recorder: Recorder, *, resolve=None, connect=None):
		self._policy = policy
		self._recorder = recorder
		self._resolve = resolve or _resolve_addresses
		self._connect = connect or _open_socket

	@property
	def policy(self) -> Policy:
		return self._policy

	def fetch(self, request: Request) -> Response:
		"""Make the exchange, follow any redirect this installation trusts, return the response.

		A provider saying no is a response, not an error. Only a request that
		could not be made at all raises.
		"""
		url = request.url
		method = request.method.upper()
		body = request.body
		headers = dict(request.headers)
		followed = 0
		deadline = time.monotonic() + self._policy.total_deadline
		while True:
			response = self._exchange(request, url, method, headers, body, deadline)
			if response.status not in REDIRECT_STATUSES:
				return response
			location = response.header("location")
			if not location:
				return response
			if followed >= self._policy.max_redirects:
				self._record_refusal(request, url, method, body, TooManyRedirects("too many redirects"))
				raise TooManyRedirects(
					f"more than {self._policy.max_redirects} redirects from {request.label}"
				)
			followed += 1
			target = urljoin(url, location)
			if urlsplit(target).hostname != urlsplit(url).hostname:
				# A new host does not get the credential the old one was given.
				headers = {k: v for k, v in headers.items() if not _is_secret_name(k)}
			url = target
			if response.status == 303 or (response.status in (301, 302) and method not in ("GET", "HEAD")):
				method = "GET"
				body = None

	def _exchange(self, request, url, method, headers, body, deadline) -> Response:
		started = time.monotonic()
		try:
			parts = self._check_url(url)
			address, family = self._pick_address(parts)
			remaining = deadline - time.monotonic()
			if remaining <= 0:
				raise RequestTimedOut(f"{request.label or request.operation.value} ran out of time")
			status, response_headers, payload = self._send(
				parts, address, family, method, headers, body, remaining
			)
		except TransportError as error:
			self._record_refusal(request, url, method, body, error, started)
			raise
		except TimeoutError as error:
			failure = RequestTimedOut(str(error) or "the provider did not answer in time")
			self._record_refusal(request, url, method, body, failure, started)
			raise failure from error
		except (OSError, http.client.HTTPException, ssl.SSLError) as error:
			failure = TransportError(f"{type(error).__name__}: {error}")
			self._record_refusal(request, url, method, body, failure, started)
			raise failure from error

		elapsed = int((time.monotonic() - started) * 1000)
		secrets = request.secrets
		reference = self._recorder.record(
			Attempt(
				operation=request.operation.value,
				label=request.label,
				correlation=request.correlation,
				connection=request.connection,
				environment=self._policy.environment.value,
				method=method,
				url=redact_url(url, secrets),
				request_headers=redact_headers(headers, secrets),
				request_digest=digest(body),
				request_bytes=len(body or b""),
				status=status,
				response_headers=redact_headers(response_headers, secrets),
				response_digest=digest(payload),
				response_bytes=len(payload),
				snippet=REDACTED if request.secret_response else _snippet(payload, secrets),
				started_at=_now_text(),
				elapsed_ms=elapsed,
				result="Completed",
			)
		)
		return Response(
			status=status,
			headers=response_headers,
			body=payload,
			url=url,
			diagnostic_ref=reference,
			elapsed_ms=elapsed,
		)

	def _record_refusal(self, request, url, method, body, error, started=None):
		elapsed = int((time.monotonic() - started) * 1000) if started else 0
		secrets = request.secrets
		self._recorder.record(
			Attempt(
				operation=request.operation.value,
				label=request.label,
				correlation=request.correlation,
				connection=request.connection,
				environment=self._policy.environment.value,
				method=method,
				url=redact_url(url, secrets),
				request_headers=redact_headers(request.headers, secrets),
				request_digest=digest(body),
				request_bytes=len(body or b""),
				status=None,
				response_headers={},
				response_digest=None,
				response_bytes=0,
				snippet="",
				started_at=_now_text(),
				elapsed_ms=elapsed,
				# A refused request is still an attempt. Leaving it out would
				# hide the fact that something tried.
				result="Blocked" if isinstance(error, UntrustedHost | BlockedAddress) else "Failed",
				error_code=getattr(error, "code", TransportError.code),
			)
		)

	def _check_url(self, url: str):
		parts = urlsplit(url)
		if parts.scheme not in ("http", "https"):
			raise UntrustedHost(f"{parts.scheme or 'this'} is not an address this app will call")
		if parts.scheme == "http" and not self._policy.allow_plain_http:
			raise UntrustedHost("plain HTTP is not allowed on this connection")
		if parts.username or parts.password:
			raise UntrustedHost("a credential in the address is not accepted")
		host = parts.hostname
		if not host:
			raise UntrustedHost("the address names no host")
		if not self._policy.trusts(host):
			raise UntrustedHost(f"{host} is not a trusted host for this connection")
		return parts

	def _pick_address(self, parts):
		"""Resolve the name once and keep the address we checked.

		The socket is opened against this exact address, so the name cannot
		resolve to something else between the check and the connection.
		"""
		port = parts.port or (443 if parts.scheme == "https" else 80)
		host = parts.hostname
		try:
			candidates = self._resolve(host, port)
		except OSError as error:
			raise TransportError(f"{host} could not be resolved: {error}") from error
		if not candidates:
			raise TransportError(f"{host} resolved to no address")
		for family, address in candidates:
			if _address_is_reachable(address, self._policy):
				return (address, port), family
		raise BlockedAddress(f"{host} resolves to an address this app will not call")

	def _send(self, parts, address, family, method, headers, body, remaining):
		connect_timeout = min(self._policy.connect_timeout, remaining)
		sock = self._connect(address, family, connect_timeout)
		try:
			if parts.scheme == "https":
				context = ssl.create_default_context()
				if not self._policy.verify_tls:
					context.check_hostname = False
					context.verify_mode = ssl.CERT_NONE
				sock = context.wrap_socket(sock, server_hostname=parts.hostname)
			sock.settimeout(min(self._policy.read_timeout, max(0.001, remaining)))
			connection = http.client.HTTPConnection(parts.hostname, parts.port or None)
			connection.sock = sock
			target = parts.path or "/"
			if parts.query:
				target = f"{target}?{parts.query}"
			connection.request(method, target, body, dict(headers))
			response = connection.getresponse()
			payload = self._read_bounded(response)
			return response.status, dict(response.getheaders()), payload
		finally:
			try:
				sock.close()
			except OSError:
				pass

	def _read_bounded(self, response) -> bytes:
		"""Read up to the limit and refuse anything past it.

		One byte over the limit is read on purpose, so an oversized body is
		caught rather than quietly truncated into something that parses.
		"""
		limit = self._policy.max_response_bytes
		chunks = []
		total = 0
		while total <= limit:
			chunk = response.read(min(65536, limit + 1 - total))
			if not chunk:
				break
			chunks.append(chunk)
			total += len(chunk)
		if total > limit:
			raise ResponseTooLarge(f"the response is larger than {limit} bytes")
		return b"".join(chunks)


def _resolve_addresses(host: str, port: int) -> list[tuple[int, str]]:
	found = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
	return [(family, sockaddr[0]) for family, _type, _proto, _name, sockaddr in found]


def _open_socket(address, family, timeout):
	sock = socket.socket(family, socket.SOCK_STREAM)
	sock.settimeout(timeout)
	try:
		sock.connect(address)
	except OSError:
		sock.close()
		raise
	return sock
