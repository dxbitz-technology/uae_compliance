"""What the simulator can be told to do, and what kind of provider it can pretend to be.

Two separate things. A profile is what a provider is like all the time: whether
it honours an idempotency key, whether anything can be looked up, whether it
keeps artifacts. A behaviour is what happens to one document: the awkward
endings a real provider produces on a bad day and which are otherwise almost
impossible to see before a client does.

The one the app has to survive is the bare profile. A provider with no safe
lookup and no idempotency promise means an ambiguous send can never be
resolved, and the app must hold it for a person rather than guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Behaviour(StrEnum):
	ACCEPT = "accept"
	REJECT_VALIDATION = "reject validation"
	RATE_LIMIT = "rate limit"
	# The document is kept and the connection drops before the answer. From
	# the caller's side this is indistinguishable from its own worker dying,
	# which is the point of it.
	LOSE_RESPONSE = "lose response"
	CALLBACK_BEFORE_RESPONSE = "callback before response"
	DUPLICATE_CALLBACKS = "duplicate callbacks"
	REORDERED_CALLBACKS = "reordered callbacks"
	DELIVERED_REPORTING_FAILED = "delivered, reporting failed"
	REPORTED_DELIVERY_FAILED = "reported, delivery failed"
	MISSING_ARTIFACT = "missing artifact"


# What each behaviour settles to once the provider has finished with it. The
# words are the provider's own: Processing, Completed, Rejected, Failed, with
# delivery and reporting held apart, which is the shape section 9.4 records.
SETTLEMENTS = {
	Behaviour.ACCEPT: ("Completed", "delivered", "accepted"),
	Behaviour.LOSE_RESPONSE: ("Completed", "delivered", "accepted"),
	Behaviour.CALLBACK_BEFORE_RESPONSE: ("Completed", "delivered", "accepted"),
	Behaviour.DUPLICATE_CALLBACKS: ("Completed", "delivered", "accepted"),
	Behaviour.REORDERED_CALLBACKS: ("Completed", "delivered", "accepted"),
	Behaviour.MISSING_ARTIFACT: ("Completed", "delivered", "accepted"),
	# The two halves fail on their own. Neither one says anything about the
	# other, which is exactly what the app must not assume.
	Behaviour.DELIVERED_REPORTING_FAILED: ("Failed", "delivered", "rejected"),
	Behaviour.REPORTED_DELIVERY_FAILED: ("Failed", "rejected", "accepted"),
	Behaviour.RATE_LIMIT: ("Processing", "pending", "pending"),
	Behaviour.REJECT_VALIDATION: ("Rejected", "rejected", "rejected"),
}

# What a rejection says. Provider codes, deliberately not ours, so the adapter
# has real mapping to do rather than passing something through.
VALIDATION_ERRORS = (
	{
		"code": "AE-VAT-0012",
		"path": "/Invoice/cac:AccountingCustomerParty",
		"message": "Buyer tax registration is not recognised",
	},
	{
		"code": "AE-FMT-0004",
		"path": "/Invoice/cbc:IssueDate",
		"message": "Issue date is later than the date received",
	},
)


@dataclass(frozen=True)
class Profile:
	"""What kind of provider this simulator is being today."""

	name: str = "full"
	honours_idempotency: bool = True
	idempotency_scope: str = "client and key"
	idempotency_expiry_seconds: int = 86400
	allows_lookup: bool = True
	serves_artifacts: bool = True
	token_seconds: float = 900.0
	page_size: int = 2
	retry_after_seconds: int = 30


FULL = Profile()

# A provider that promises nothing. No idempotency key, no way to search, no
# artifacts. An ambiguous send against this one can never be settled, and the
# app has to say so rather than send the document again.
BARE = Profile(
	name="bare",
	honours_idempotency=False,
	allows_lookup=False,
	serves_artifacts=False,
)

PROFILES = {profile.name: profile for profile in (FULL, BARE)}
