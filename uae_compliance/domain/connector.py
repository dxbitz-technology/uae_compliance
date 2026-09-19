"""The contract a provider adapter fills in, and what an operation returns.

No HTTP lives here and no provider is named. This is the shape every adapter
has to fit, so nothing downstream has to know whose service is on the other
end. A provider's own status codes are carried for the record and never
decide anything.

The rule this module exists to hold:

  When we do not know whether the provider took the document, we do not send
  it again unless that provider has promised, in writing and in its declared
  capabilities, that sending it again is safe.

A duplicate legal invoice is worse than a delayed one. Every other rule here
is in service of that one.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from uae_compliance.domain.findings import Finding, Stage

CONTRACT_VERSION = 1


class ContractError(ValueError):
	"""An adapter or an outcome was described in a way that is not safe to act on."""


class Environment(StrEnum):
	SIMULATION = "Simulation"
	SANDBOX = "Sandbox"
	PRODUCTION = "Production"


class Operation(StrEnum):
	"""The exact operation names. An adapter declares which ones it supports."""

	AUTHENTICATE = "authenticate"
	SUBMIT = "submit"
	GET_STATUS = "get_status"
	FIND_SUBMISSION = "find_submission"
	LOOKUP_PARTICIPANT = "lookup_participant"
	FETCH_ARTIFACT = "fetch_artifact"
	WITHDRAW = "withdraw"
	FETCH_INBOUND = "fetch_inbound"


class Disposition(StrEnum):
	"""What happened to the request, kept apart from what it means.

	A provider saying no to the document is a different thing from the network
	failing, and both are different from our credentials being stale. Merging
	them would send someone to fix the wrong thing.
	"""

	SUCCEEDED = "Succeeded"
	BUSINESS_REJECTED = "Business rejected"
	AUTHENTICATION_FAILED = "Authentication failed"
	RATE_LIMITED = "Rate limited"
	TRANSPORT_FAILED = "Transport failed"
	TIMED_OUT = "Timed out"
	UNKNOWN = "Unknown"


class Effect(StrEnum):
	"""Whether the thing we asked for actually happened on the other side."""

	NOT_APPLIED = "Not applied"
	APPLIED = "Applied"
	UNKNOWN = "Unknown"


class Advice(StrEnum):
	"""What the worker may do next. Nothing else decides this."""

	DO_NOT_RETRY = "Do not retry"
	RETRY_SAME_PAYLOAD = "Retry the same payload"
	RECONCILE_FIRST = "Reconcile first"
	HOLD_FOR_PERSON = "Hold for a person"
	REFRESH_AUTHENTICATION = "Refresh authentication"


# The four dimensions from the states table. They move on their own and one
# can never be read off another.
class AspReceipt(StrEnum):
	NOT_SENT = "Not sent"
	UNKNOWN = "Unknown"
	RECEIVED = "Received"
	REJECTED = "Rejected"


class Exchange(StrEnum):
	NOT_STARTED = "Not started"
	PENDING = "Pending"
	DELIVERED = "Delivered"
	REJECTED = "Rejected"
	UNKNOWN = "Unknown"
	NOT_APPLICABLE = "Not applicable"


class Reporting(StrEnum):
	NOT_STARTED = "Not started"
	PENDING = "Pending"
	ACCEPTED = "Accepted"
	REJECTED = "Rejected"
	UNKNOWN = "Unknown"
	NOT_APPLICABLE = "Not applicable"


class Evidence(StrEnum):
	COMPLETE = "Complete"
	PENDING = "Pending"
	UNAVAILABLE = "Unavailable"
	INVALID = "Invalid"


@dataclass(frozen=True)
class Route:
	"""What a given document actually has to collect before it is done.

	Which acknowledgements apply depends on the scenario and the route, not on
	what the provider happened to send back. Defaults assume both apply, so a
	route that skips one has to say so deliberately.
	"""

	exchange_required: bool = True
	reporting_required: bool = True


@dataclass(frozen=True)
class Acknowledgements:
	"""The four outcomes, each held separately.

	Transport succeeding says nothing about delivery, and delivery says
	nothing about reporting. Nothing here is allowed to imply anything else.
	"""

	asp_receipt: AspReceipt = AspReceipt.NOT_SENT
	exchange: Exchange = Exchange.NOT_STARTED
	reporting: Reporting = Reporting.NOT_STARTED
	evidence: Evidence = Evidence.PENDING

	def complete(self, route: "Route") -> bool:
		"""Everything this route needs has arrived. One success is not enough.

		The route says which acknowledgements this document actually needs.
		A step may only be marked as not applicable where the route says it
		does not apply; otherwise a document could be called complete having
		never been reported.
		"""
		if self.asp_receipt is not AspReceipt.RECEIVED:
			return False
		if self.evidence is not Evidence.COMPLETE:
			return False
		if route.exchange_required:
			if self.exchange is not Exchange.DELIVERED:
				return False
		elif self.exchange not in (Exchange.DELIVERED, Exchange.NOT_APPLICABLE):
			return False
		if route.reporting_required:
			if self.reporting is not Reporting.ACCEPTED:
				return False
		elif self.reporting not in (Reporting.ACCEPTED, Reporting.NOT_APPLICABLE):
			return False
		return True


@dataclass(frozen=True)
class Idempotency:
	"""What the provider promises about sending the same thing twice.

	`scope` names what the key covers and `expiry_seconds` how long the
	promise lasts. An adapter that makes no promise leaves this as None, and
	then an ambiguous send is never repeated.
	"""

	scope: str
	expiry_seconds: int

	def __post_init__(self):
		if not self.scope:
			raise ContractError("an idempotency promise must say what it covers")
		if self.expiry_seconds <= 0:
			raise ContractError("an idempotency promise must last a positive time")


@dataclass(frozen=True)
class Adapter:
	"""What an adapter declares about itself.

	A capability that is not declared does not exist. Nothing is assumed from
	the fact that a provider is popular or that another adapter has it.
	"""

	provider_key: str
	label: str
	adapter_version: str
	contract_version: int
	environments: tuple[Environment, ...]
	operations: frozenset[Operation]
	request_format: str
	authentication: str
	idempotency: Idempotency | None = None
	can_search_by_key: bool = False
	event_authentication: str | None = None
	events_carry_order: bool = False
	supports_artifacts: bool = False
	pagination: str | None = None
	scenarios: tuple[str, ...] = ()

	def __post_init__(self):
		if not self.provider_key:
			raise ContractError("an adapter needs a provider key")
		if self.contract_version != CONTRACT_VERSION:
			raise ContractError(
				f"{self.provider_key}: built against contract {self.contract_version}, "
				f"this app speaks {CONTRACT_VERSION}"
			)
		if not self.environments:
			raise ContractError(f"{self.provider_key}: an adapter must support an environment")
		missing = {Operation.AUTHENTICATE, Operation.SUBMIT} - self.operations
		if missing:
			raise ContractError(f"{self.provider_key}: cannot send without " + ", ".join(sorted(missing)))

	def supports(self, operation: Operation) -> bool:
		return operation in self.operations

	def can_resolve_an_ambiguous_send(self) -> bool:
		"""Whether an unknown outcome can be settled without guessing."""
		return bool(self.idempotency) or self.can_search_by_key


@dataclass(frozen=True)
class ArtifactRef:
	"""A file the provider holds or returned.

	It starts as a reference, because listing what exists and fetching it are
	different operations and the first should not drag the files across. Once
	something has actually been fetched, `body` carries the bytes and the
	hash is worked out from them rather than trusted.

	Without this, retrieval could succeed and the file still could not be
	kept, which is how a submission ends up holding a hash for bytes nobody
	has.
	"""

	kind: str
	identifier: str
	media_type: str | None = None
	sha256: str | None = None
	body: bytes | None = None

	def __post_init__(self):
		if not self.kind or not self.identifier:
			raise ContractError("an artifact needs a kind and an identifier")
		if self.body is None:
			return
		if not isinstance(self.body, bytes):
			raise ContractError(f"{self.kind}: a fetched artifact is bytes")
		actual = hashlib.sha256(self.body).hexdigest()
		if not self.sha256:
			object.__setattr__(self, "sha256", actual)
		elif self.sha256 != actual:
			raise ContractError(f"{self.kind}: the bytes do not match the hash they arrived with")

	@property
	def fetched(self) -> bool:
		return self.body is not None


@dataclass(frozen=True)
class Outcome:
	"""What one operation produced, in our words rather than the provider's.

	`provider_code` and `diagnostic_ref` are kept so an attempt can be
	explained later. Nothing in this app may branch on them. Every decision
	comes from the fields above them. The diagnostic reference points at
	evidence held privately rather than carrying response text around.
	"""

	operation: Operation
	disposition: Disposition
	effect: Effect
	advice: Advice
	acknowledgements: Acknowledgements = field(default_factory=Acknowledgements)
	provider_ids: Mapping[str, str] = field(default_factory=dict)
	findings: Sequence[Finding] = ()
	artifacts: Sequence[ArtifactRef] = ()
	retry_after_seconds: int | None = None
	event_cursor: str | None = None
	provider_code: str | None = None
	diagnostic_ref: str | None = None

	def __post_init__(self):
		_check_effect_matches_disposition(self)
		_check_advice_is_safe(self)
		for item in self.findings:
			if item.stage is not Stage.PROVIDER_RESPONSE:
				raise ContractError(
					f"{item.code}: a finding from a provider belongs to the provider response stage"
				)
		if self.disposition is Disposition.RATE_LIMITED and self.retry_after_seconds is None:
			raise ContractError("a rate limit must say how long to wait")
		if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
			raise ContractError("a wait cannot be negative")


# What each disposition is allowed to say about the effect. A provider saying
# no means the document was seen and refused, so nothing was applied. A
# timeout means we genuinely do not know.
_ALLOWED_EFFECTS = {
	Disposition.SUCCEEDED: {Effect.APPLIED},
	Disposition.BUSINESS_REJECTED: {Effect.NOT_APPLIED},
	Disposition.AUTHENTICATION_FAILED: {Effect.NOT_APPLIED},
	Disposition.RATE_LIMITED: {Effect.NOT_APPLIED},
	# A refused connection applied nothing; a failure after the bytes left
	# might have. Both are real, so the adapter has to say which.
	Disposition.TRANSPORT_FAILED: {Effect.NOT_APPLIED, Effect.UNKNOWN},
	Disposition.TIMED_OUT: {Effect.UNKNOWN},
	Disposition.UNKNOWN: {Effect.UNKNOWN},
}


def _check_effect_matches_disposition(outcome: Outcome) -> None:
	allowed = _ALLOWED_EFFECTS[outcome.disposition]
	if outcome.effect not in allowed:
		raise ContractError(f"{outcome.disposition.value} cannot report the effect as {outcome.effect.value}")


def _check_advice_is_safe(outcome: Outcome) -> None:
	if outcome.effect is Effect.UNKNOWN and outcome.advice is Advice.RETRY_SAME_PAYLOAD:
		raise ContractError("an unknown outcome cannot be retried blindly; reconcile first or hold it")
	if outcome.effect is Effect.APPLIED and outcome.advice is Advice.RETRY_SAME_PAYLOAD:
		# The provider already has it. Sending it again is how a client ends up
		# with two of the same legal invoice. Whatever is still missing, a
		# status or an artifact, is fetched by its own operation.
		raise ContractError(
			"the provider already took this; fetch what is missing rather than sending it again"
		)
	if outcome.disposition is Disposition.BUSINESS_REJECTED and outcome.advice in (
		Advice.RETRY_SAME_PAYLOAD,
		Advice.RECONCILE_FIRST,
	):
		raise ContractError("a rejected document needs a correction, not another attempt")
	if outcome.disposition is Disposition.RATE_LIMITED and outcome.advice not in (
		Advice.RETRY_SAME_PAYLOAD,
		Advice.HOLD_FOR_PERSON,
	):
		raise ContractError("a rate limit is waited out, not corrected")


def advise(outcome: Outcome, adapter: Adapter) -> Advice:
	"""What to do about an outcome, given what this provider actually promises.

	The adapter's own capabilities decide it. An ambiguous send is only ever
	repeated where the provider has promised that repeating is safe, and is
	held for a person when nothing can settle it.
	"""
	if outcome.effect is not Effect.UNKNOWN:
		return outcome.advice
	if adapter.can_resolve_an_ambiguous_send():
		return Advice.RECONCILE_FIRST
	return Advice.HOLD_FOR_PERSON


class Registry:
	"""The adapters this installation trusts.

	An adapter is handed over as an object that is already imported. A name or
	a path is refused, so nothing in configuration or in a request can cause
	this app to import and run arbitrary code.
	"""

	def __init__(self):
		self._adapters: dict[str, Adapter] = {}

	def register(self, adapter: Adapter) -> None:
		if not isinstance(adapter, Adapter):
			raise ContractError("register an adapter object, never a name or an import path to load")
		if adapter.provider_key in self._adapters:
			raise ContractError(f"{adapter.provider_key} is already registered")
		self._adapters[adapter.provider_key] = adapter

	def get(self, provider_key: str) -> Adapter:
		if provider_key not in self._adapters:
			raise ContractError(f"{provider_key} is not an installed adapter")
		return self._adapters[provider_key]

	def keys(self) -> tuple[str, ...]:
		return tuple(sorted(self._adapters))

	def require(self, provider_key: str, operation: Operation) -> Adapter:
		"""Fetch an adapter for an operation it has actually declared."""
		adapter = self.get(provider_key)
		if not adapter.supports(operation):
			raise ContractError(f"{provider_key} does not support {operation.value}")
		return adapter
