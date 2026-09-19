"""Where the transport's own record of each exchange is kept.

The transport hands over an attempt describing one HTTP exchange, already
cleaned of headers, tokens and anything secret. This writes it down and hands
back a reference so an outcome can point at it later.

It must never raise. An exchange that already happened cannot be undone by
failing to write about it, and a recorder that cannot write has to fail on
its own terms rather than taking the send down with it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import frappe

from uae_compliance.services.outbox import LOG_DOCTYPE


class FrappeRecorder:
	"""Keeps each exchange as its own attempt row, linked to the submission.

	One business operation can take several exchanges. Signing in, then
	sending, then fetching a page. Each is written separately so a reader can
	see what actually left this machine rather than a summary of it.
	"""

	def __init__(self, submission: str | None, company: str | None, connection: str | None, token: int = 0):
		self.submission = submission
		self.company = company
		self.connection = connection
		self.token = token
		self.references: list[str] = []

	def record(self, attempt) -> str:
		reference = uuid.uuid4().hex
		try:
			log = frappe.new_doc(LOG_DOCTYPE)
			log.attempt_id = reference
			log.submission = self.submission
			log.company = self.company
			log.connection = self.connection
			log.operation = f"http:{attempt.operation}"
			log.state = "Finished"
			log.started_at = _as_local(attempt.started_at)
			log.duration_ms = attempt.elapsed_ms
			log.request_digest = attempt.request_digest
			log.fencing_token = self.token
			log.transport_status = str(attempt.status) if attempt.status is not None else attempt.result
			log.error_class = attempt.error_code
			log.detail = frappe.as_json(
				{
					"label": attempt.label,
					"method": attempt.method,
					"url": attempt.url,
					"request_headers": dict(attempt.request_headers),
					"request_bytes": attempt.request_bytes,
					"response_headers": dict(attempt.response_headers),
					"response_bytes": attempt.response_bytes,
					"response_digest": attempt.response_digest,
					"snippet": attempt.snippet,
					"result": attempt.result,
				}
			)
			log.insert(ignore_permissions=True)
			self.references.append(reference)
		except Exception:
			# Losing the note is bad. Losing the send because the note could
			# not be written would be worse.
			frappe.log_error(title="UAE e-invoicing could not record an exchange")
		return reference


def _as_local(text: str):
	"""The transport writes UTC with its offset. The database wants neither.

	Parsing it properly rather than trimming characters off the end, because
	the offset form and the Z form both turn up and a string that almost
	parses is how an attempt record quietly fails to be written.
	"""
	try:
		moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
	except TypeError, ValueError:
		return frappe.utils.now_datetime()
	return moment.replace(tzinfo=None)
