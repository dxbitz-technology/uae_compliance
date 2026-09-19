"""The rules about claiming, letting go, stopping, and correcting.

These were spread across four service files, each with its own copy of which
states mean a document might be with the provider. Copies drift, and the two
that had drifted disagreed about the case that matters: cancelling checked
whether the provider had received the document and correcting did not, so the
same invoice could be corrected into a second revision after the provider
already held the first one.

Nothing here touches a database. The services do the writing and the locking.
This says what is allowed, in one place, where it can be read and checked
without a site.

The rule underneath all of it: a document that might be with the provider is
treated as if it is. Not knowing is not the same as it not having happened.
"""

from __future__ import annotations

from datetime import datetime

# A worker may only pick up work in one of these. Anything else is either
# finished, held for a person, or already somebody else's.
CLAIMABLE = ("Ready", "Retry scheduled")

# Something is with the provider or may be. Nothing may be stopped, corrected
# or cancelled from here, whatever the receipt says.
IN_FLIGHT = ("Sending", "Awaiting outcome", "Unknown")

# States where the document has gone and been settled one way or another.
SETTLED = ("Complete", "Superseded")

# Receipts that mean the provider has the document, or might. Unknown counts,
# and that is the whole point of it.
WITH_THE_PROVIDER = ("Received", "Unknown")

# Nothing has gone out and nobody is holding it, so the intent to send can be
# taken away and the invoice cancelled underneath it.
STOPPABLE = ("Awaiting review", "Ready", "Retry scheduled", "Stopped")

# The same, plus the state a correction is usually made from: the provider
# refused the document and somebody has to prepare a different one.
CORRECTABLE = ("Awaiting review", "Ready", "Retry scheduled", "Attention required", "Stopped")

# Longer than any request is allowed to take, so a claim does not run out
# while the request it covers is still in flight. A claim running out never
# means the other worker stopped, only that nobody has heard from it.
LEASE_SECONDS = 300

# One send makes two requests: sign in, then submit. Each gets the transport's
# own deadline, so the lease has to cover both and leave room. The connector
# tests check this against the transport's real deadline, so changing one
# number without the other fails there rather than in production.
REQUESTS_PER_SEND = 2

# An attempt counts as abandoned only once the claim covering it has run out
# and then some. Recovering one while a worker still holds a live lease takes
# the work away from a worker that is about to answer.
ABANDONED_AFTER_SECONDS = LEASE_SECONDS + 60


def may_overwrite(held: int | None, current: int | None) -> bool:
	"""Whether a worker holding this token may still write its result.

	A worker whose claim ran out may still be holding a reply. That reply is
	about a state the world has already moved past, and writing it would put
	an older answer on top of a newer one.
	"""
	if current is None or held is None:
		return True
	return held >= current


def lease_is_live(expires_at: datetime | None, now: datetime) -> bool:
	"""Whether somebody still holds this submission."""
	return expires_at is not None and expires_at > now


def may_believe_it_never_arrived(current_receipt: str, answered: bool) -> bool:
	"""Whether a fresh answer is allowed to say the provider never had it.

	Only where the provider actually answered. A status call that timed out,
	returned a 500, or told us the endpoint does not exist has established
	nothing, and writing Not sent on the back of one turns "we could not
	find out" into "it never happened". That is the false negative the whole
	recovery path exists to avoid: from Not sent the document becomes
	cancellable and correctable, and a second one goes out.
	"""
	if current_receipt not in WITH_THE_PROVIDER:
		return True
	return answered


def why_it_may_be_out_there(
	state: str,
	asp_receipt: str,
	exchange_state: str,
	reporting_state: str,
	pending_attempt: bool = False,
	lease_live: bool = False,
) -> str | None:
	"""Why this document may already be with the provider, or nothing.

	Both stopping and correcting ask exactly this. Stopping takes away the
	intent to send and correcting makes a second document, and neither is
	safe unless the first one provably never left.

	No attempts having been made is not proof that nothing was issued
	elsewhere. It is proof that this app made none, which is all this
	answers.
	"""
	if state in SETTLED:
		return "it has already been sent and settled"
	if state in IN_FLIGHT:
		return "it is with the provider and we are waiting to hear"
	if pending_attempt:
		return "a request went out for it and has not come back"
	if lease_live:
		return "a worker has this one and is sending it now"
	if asp_receipt in WITH_THE_PROVIDER:
		return "the provider has it, or may have it"
	if exchange_state == "Delivered" or reporting_state == "Accepted":
		return "it has already reached the other side"
	return None
