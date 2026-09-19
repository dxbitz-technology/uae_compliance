"""Picking up work that is waiting to go out.

The submission is the outbox. The queue is a way of getting a worker's
attention, not the record that work exists, so everything here reads the
database and nothing depends on a job still being in Redis.

A claim is one atomic update or it is nothing. Two workers reaching for the
same submission means exactly one of them gets it and the other is told no,
because the alternative is the same legal invoice going out twice.

Nothing here talks to a provider. That is the next phase. This decides what
may be picked up, takes it, and writes down that an attempt is starting.
"""

from __future__ import annotations

import socket
import uuid

import frappe
from frappe.utils import add_to_date, now_datetime

from uae_compliance.services.freeze import SUBMISSION_DOCTYPE

LOG_DOCTYPE = "UAE Peppol Transmission Log"
SETTINGS = "UAE Peppol Settings"

CLAIMABLE = ("Ready", "Retry scheduled")

# Longer than any request is allowed to take, so a claim does not run out
# while the request it covers is still in flight. A claim running out never
# means the other worker stopped, only that nobody has heard from it.
LEASE_SECONDS = 300


def worker_name() -> str:
	return f"{socket.gethostname()}:{frappe.local.site}"


def paused() -> tuple[bool, str]:
	"""Whether somebody has stopped outbound work, and why.

	A pause stops new sends and retries. It does not change what validation
	says, throw away queued work, or stop us finding out what happened to
	something already sent.
	"""
	settings = frappe.get_cached_doc(SETTINGS)
	return bool(settings.pause_outbound), settings.pause_reason or ""


def due(limit: int = 20) -> list[str]:
	"""Submissions that are ready to go, oldest first.

	Bounded and indexed. A site with a hundred thousand of these must not
	read them all to find the next twenty.
	"""
	stopped, _reason = paused()
	if stopped:
		return []

	now = now_datetime()
	rows = frappe.get_all(
		SUBMISSION_DOCTYPE,
		filters={
			"processing_state": ["in", CLAIMABLE],
			"approved": 1,
			"next_attempt_at": ["<=", now],
		},
		or_filters=[
			["lease_expires_at", "is", "not set"],
			["lease_expires_at", "<", now],
		],
		fields=["name"],
		order_by="next_attempt_at asc",
		limit=limit,
	)
	return [row.name for row in rows]


def claim(submission: str) -> dict | None:
	"""Take one submission, or find out somebody else already has it.

	One update decides it. Everything the update tests is in its own where
	clause, so there is no gap between checking and taking during which
	another worker could do the same.
	"""
	now = now_datetime()
	expires = add_to_date(now, seconds=LEASE_SECONDS)
	owner = worker_name()

	frappe.db.sql(
		f"""
		update `tab{SUBMISSION_DOCTYPE}`
		set lease_owner = %(owner)s,
			lease_expires_at = %(expires)s,
			fencing_token = fencing_token + 1,
			processing_state = 'Sending',
			modified = %(now)s
		where name = %(name)s
			and approved = 1
			and processing_state in ('Ready', 'Retry scheduled')
			and (lease_expires_at is null or lease_expires_at < %(now)s)
		""",
		{"owner": owner, "expires": expires, "now": now, "name": submission},
	)
	if not frappe.db.sql("select row_count()")[0][0]:
		return None

	held = frappe.db.get_value(
		SUBMISSION_DOCTYPE,
		submission,
		["fencing_token", "canonical_hash", "approved_canonical_hash", "payload_hash", "connection"],
		as_dict=True,
	)
	if held.canonical_hash != held.approved_canonical_hash or not held.payload_hash:
		# Approved content and current content have to be the same thing.
		# They cannot normally differ, so if they do something is wrong that
		# a person should look at rather than a worker push past.
		release(submission, "Attention required", "What was approved is not what is here.")
		return None

	return {"token": held.fencing_token, "owner": owner, "connection": held.connection}


def release(submission: str, state: str, reason: str | None = None):
	"""Let go of a claim and say where the work has got to."""
	values = {
		"lease_owner": None,
		"lease_expires_at": None,
		"processing_state": state,
	}
	if reason:
		values["attention_reason"] = reason
	frappe.db.set_value(SUBMISSION_DOCTYPE, submission, values)


def start_attempt(submission: str, operation: str, token: int, request_digest: str) -> str:
	"""Write down that a request is about to go out.

	Before the request, always, and committed before it. If the process dies
	between this and the answer, this record is the only thing that says a
	request may have reached them, and without it the next worker would send
	the same invoice again believing nothing had happened.
	"""
	details = frappe.db.get_value(SUBMISSION_DOCTYPE, submission, ["company", "connection"], as_dict=True)
	log = frappe.new_doc(LOG_DOCTYPE)
	log.attempt_id = uuid.uuid4().hex
	log.submission = submission
	log.company = details.company
	log.connection = details.connection
	log.operation = operation
	log.state = "Pending"
	log.started_at = now_datetime()
	log.request_digest = request_digest
	log.fencing_token = token
	log.worker = worker_name()
	log.insert(ignore_permissions=True)

	frappe.db.sql(
		f"update `tab{SUBMISSION_DOCTYPE}` set attempts = attempts + 1 where name = %s",
		(submission,),
	)
	return log.attempt_id


def finish_attempt(attempt_id: str, token: int, **result) -> bool:
	"""Record what came back, unless a newer claim has been and gone.

	The token is what stops an old worker writing over a newer answer. A
	worker whose claim ran out may still be holding a reply, and that reply
	is about a state the world has already moved past.
	"""
	current = frappe.db.get_value(SUBMISSION_DOCTYPE, _submission_of(attempt_id), "fencing_token")
	if current is not None and token < current:
		return False

	log = frappe.get_doc(LOG_DOCTYPE, attempt_id)
	if log.state == "Finished":
		return False
	log.state = "Finished"
	log.finished_at = now_datetime()
	if log.started_at:
		delta = log.finished_at - log.started_at
		log.duration_ms = int(delta.total_seconds() * 1000)
	for field, value in result.items():
		if log.meta.has_field(field):
			log.set(field, value)
	log.save(ignore_permissions=True)
	return True


def _submission_of(attempt_id: str) -> str:
	return frappe.db.get_value(LOG_DOCTYPE, attempt_id, "submission")


def abandoned(older_than_seconds: int = LEASE_SECONDS) -> list[str]:
	"""Attempts that went out and never came back.

	These are the dangerous ones. Something may have reached the provider,
	so they are handed to reconciliation rather than retried, and never
	quietly marked as failed.
	"""
	cutoff = add_to_date(now_datetime(), seconds=-older_than_seconds)
	return [
		row.attempt_id
		for row in frappe.get_all(
			LOG_DOCTYPE,
			filters={"state": "Pending", "started_at": ["<", cutoff]},
			fields=["attempt_id"],
		)
	]
