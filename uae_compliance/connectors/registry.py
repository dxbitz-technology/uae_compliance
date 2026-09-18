"""The adapters this installation will actually run, and what a call to one looks like.

An adapter is handed over as an object that is already imported. A name, a
dotted path or anything else that would have to be resolved is refused, so
nothing in a settings record and nothing in a request can cause this app to
import and run code of its own choosing.

Another app may add an adapter through the `uae_peppol_adapters` hook:

    # in the other app's hooks.py
    uae_peppol_adapters = ["other_app.peppol.adapter.build"]

Each entry names something in that app's own source that returns an adapter
object. The Frappe layer reads the hook and resolves the entries, because it
is the only part of the app that knows which apps are installed. It then
calls `load_hook_adapters` with the resolved objects. Nothing here imports
anything, which is what keeps a value out of configuration from ever reaching
an import.

A hook adapter cannot take a built-in provider key. A third-party app that
could shadow a trusted adapter would be a way to replace it.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from uae_compliance.connectors.transport import Transport
from uae_compliance.domain.connector import (
	Adapter,
	ArtifactRef,
	ContractError,
	Environment,
	Operation,
	Outcome,
	Registry,
)

HOOK_NAME = "uae_peppol_adapters"

# Everything the simulator issues carries one of these. A Production
# connection refuses them, so a demo credential or a document the simulator
# invented cannot be sent to a real provider by changing one field.
SIMULATION_CREDENTIAL_PREFIX = "sim_"
SIMULATION_ID_PREFIX = "SIM-"

# Names that mean this machine. The transport blocks the addresses as well;
# this catches the common case at the point somebody types it in.
LOCAL_NAMES = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "ip6-localhost"})


@dataclass
class Session:
	"""The token for one connection, held in memory for as long as it is valid.

	Not frozen, because a refresh replaces it. Never written to a job
	argument, an attempt or a log; the transport masks it wherever it appears.
	"""

	token: str | None = None
	expires_at: float | None = None

	def valid(self, now: float | None = None, margin: float = 30.0) -> bool:
		"""Whether the token will still be good for the call about to be made.

		The margin is there because a token that expires during the request is
		the same problem as one that expired before it.
		"""
		if not self.token:
			return False
		if self.expires_at is None:
			return True
		return (now if now is not None else time.time()) + margin < self.expires_at

	def hold(self, token: str, expires_in: float | None, now: float | None = None) -> None:
		self.token = token
		moment = now if now is not None else time.time()
		self.expires_at = None if expires_in is None else moment + expires_in

	def clear(self) -> None:
		self.token = None
		self.expires_at = None


@dataclass(frozen=True)
class Connection:
	"""One provider connection: where it is, which environment it serves, what it needs to sign in.

	The credentials stay on this object and go nowhere else. `secrets` is what
	the transport masks.
	"""

	provider_key: str
	connection_id: str
	environment: Environment
	base_url: str
	credentials: Mapping[str, str] = field(default_factory=dict)
	settings: Mapping[str, str] = field(default_factory=dict)
	session: Session = field(default_factory=Session)

	def __post_init__(self):
		if not self.provider_key or not self.connection_id:
			raise ContractError("a connection needs a provider key and its own name")
		parts = urlsplit(self.base_url)
		if parts.scheme not in ("http", "https") or not parts.hostname:
			raise ContractError(f"{self.connection_id}: the base address must be an http or https URL")
		if self.environment is Environment.PRODUCTION:
			if parts.hostname.lower() in LOCAL_NAMES:
				raise ContractError("a Production connection cannot point at this machine")
			for key, value in self.credentials.items():
				if str(value).startswith(SIMULATION_CREDENTIAL_PREFIX):
					raise ContractError(f"{key} is a simulation credential and cannot be used in Production")

	def url(self, path: str) -> str:
		return self.base_url.rstrip("/") + "/" + path.lstrip("/")

	def secrets(self) -> tuple[str, ...]:
		values = [str(value) for value in self.credentials.values() if value]
		if self.session.token:
			values.append(self.session.token)
		return tuple(values)


@dataclass(frozen=True)
class BusinessRequest:
	"""The frozen bytes that were approved, with the digest that says so.

	A worker may build an authentication envelope around this. It may not
	rebuild the content, so the digest is checked here rather than trusted.
	"""

	media_type: str
	body: bytes
	digest: str = ""

	def __post_init__(self):
		if not self.media_type:
			raise ContractError("a business request must say what it is")
		if not isinstance(self.body, bytes):
			raise ContractError("a business request is bytes, frozen at approval")
		actual = hashlib.sha256(self.body).hexdigest()
		if not self.digest:
			object.__setattr__(self, "digest", actual)
		elif self.digest != actual:
			raise ContractError("the approved bytes do not match their digest")


@dataclass(frozen=True)
class Call:
	"""One operation against one connection.

	`document` is the canonical invoice, for an adapter whose provider takes
	its own format. `request` is the frozen payload, for an adapter whose
	provider takes the reference XML. An adapter uses whichever its declared
	request format says, and says so plainly when the other one arrives.
	"""

	operation: Operation
	connection: Connection
	document: Mapping | None = None
	request: BusinessRequest | None = None
	idempotency_key: str | None = None
	provider_ids: Mapping[str, str] = field(default_factory=dict)
	artifact: ArtifactRef | None = None
	cursor: str | None = None
	page_size: int | None = None
	correlation: str | None = None

	def __post_init__(self):
		if self.connection.environment is Environment.PRODUCTION:
			for key, value in self.provider_ids.items():
				if str(value).startswith(SIMULATION_ID_PREFIX):
					raise ContractError(f"{key} was issued by the simulator and has no meaning in Production")


@runtime_checkable
class ProviderAdapter(Protocol):
	"""What an installed adapter offers.

	`descriptor` is the capability declaration from the contract. `perform`
	does one operation and returns the contract's own outcome. Everything
	external goes through the transport it is handed.
	"""

	descriptor: Adapter

	def perform(self, call: Call, transport: Transport) -> Outcome: ...


class AdapterRegistry:
	"""The adapters this installation trusts, with their declarations.

	The declaration side is the contract's own registry, so the rules about
	contract versions and duplicate keys live in one place and are not
	restated here.
	"""

	def __init__(self):
		# The contract's own registry, which owns the rules about contract
		# versions and duplicate keys.
		self._declarations = Registry()
		self._adapters: dict[str, ProviderAdapter] = {}
		self._built_in: set[str] = set()

	def register(self, adapter: ProviderAdapter, *, built_in: bool = False) -> None:
		if isinstance(adapter, str | bytes):
			raise ContractError("register an adapter object, never a name or an import path to load")
		declaration = getattr(adapter, "descriptor", None)
		if not isinstance(declaration, Adapter):
			raise ContractError("an adapter must carry the capability declaration it was built from")
		if not callable(getattr(adapter, "perform", None)):
			raise ContractError(
				f"{declaration.provider_key}: an adapter must be able to perform an operation"
			)
		self._declarations.register(declaration)
		self._adapters[declaration.provider_key] = adapter
		if built_in:
			self._built_in.add(declaration.provider_key)

	def get(self, provider_key: str) -> ProviderAdapter:
		if provider_key not in self._adapters:
			raise ContractError(f"{provider_key} is not an installed adapter")
		return self._adapters[provider_key]

	def declaration(self, provider_key: str) -> Adapter:
		return self._declarations.get(provider_key)

	def keys(self) -> tuple[str, ...]:
		return self._declarations.keys()

	def is_built_in(self, provider_key: str) -> bool:
		return provider_key in self._built_in

	def require(self, provider_key: str, operation: Operation) -> ProviderAdapter:
		"""Fetch an adapter for an operation it has declared. An undeclared one does not exist."""
		self._declarations.require(provider_key, operation)
		return self.get(provider_key)

	def for_connection(self, connection: Connection, operation: Operation) -> ProviderAdapter:
		"""The adapter for this connection, checked against the environment it serves.

		An adapter that has not declared an environment is not used there, even
		if the operation itself is supported. A sandbox-only adapter reaching
		Production is exactly the accident this stops.
		"""
		adapter = self.require(connection.provider_key, operation)
		declaration = self.declaration(connection.provider_key)
		if connection.environment not in declaration.environments:
			raise ContractError(f"{declaration.provider_key} does not serve {connection.environment.value}")
		return adapter


def built_in_adapters() -> tuple[ProviderAdapter, ...]:
	"""The adapters shipped with this app, listed here and nowhere else.

	They are imported inside this function, because an adapter imports the
	call shapes above. The two test adapters land with their own packet. Until
	then this installation has no provider to call, which is the honest state
	of it.
	"""
	return ()


def installed() -> AdapterRegistry:
	registry = AdapterRegistry()
	for adapter in built_in_adapters():
		registry.register(adapter, built_in=True)
	return registry


def load_hook_adapters(
	registry: AdapterRegistry,
	entries: Iterable[tuple[str, object]],
	resolve: Callable[[str], object] | None = None,
) -> tuple[str, ...]:
	"""Add adapters other installed apps declared, and say which were added.

	`entries` are pairs of the app that declared it and the value it declared.
	A value that is already an adapter object is used as it is. A value that
	is a name needs `resolve`, which the Frappe layer supplies as its own
	attribute lookup. Without it, a name is refused rather than imported.
	"""
	added = []
	for app, value in entries:
		adapter = value
		if isinstance(adapter, str):
			if resolve is None:
				raise ContractError(f"{app}: {HOOK_NAME} named {adapter} and nothing was given to resolve it")
			adapter = resolve(adapter)
		declaration = getattr(adapter, "descriptor", None)
		if not isinstance(declaration, Adapter):
			raise ContractError(f"{app}: {HOOK_NAME} did not produce an adapter")
		if registry.is_built_in(declaration.provider_key):
			raise ContractError(f"{app}: {declaration.provider_key} is built in and cannot be replaced")
		registry.register(adapter)
		added.append(declaration.provider_key)
	return tuple(added)
