"""Checking that the evidence we hold is still the evidence we recorded.

A submission carries a manifest: what was kept, how big it was, and the
hash of its contents. None of that is worth anything unless somebody
occasionally reads the bytes back and compares.

This is the check spec 11.3 asks for after a restore, and it is the one
that tells a restore apart from a restore that half worked. It reads and
never repairs. Where evidence has gone or changed, that is something a
person decides about, because the alternatives are all worse than saying
so.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from uae_compliance.domain.encoding import sha256_hex
from uae_compliance.services.freeze import SUBMISSION_DOCTYPE

# Bounded, because a site with years of history should not be read in one
# go by a scheduled job.
BATCH = 200


def check_one(submission: str) -> dict:
	"""Read back everything one submission says it holds."""
	row = frappe.db.get_value(
		SUBMISSION_DOCTYPE,
		submission,
		["evidence_manifest", "evidence_state", "company"],
		as_dict=True,
	)
	if not row:
		return {"submission": submission, "state": "Missing", "problems": ["No such submission."]}

	manifest = json.loads(row.evidence_manifest or "[]")
	if not manifest:
		return {
			"submission": submission,
			"company": row.company,
			"state": row.evidence_state,
			"checked": 0,
			"problems": [],
		}

	problems = []
	checked = 0
	for entry in manifest:
		kind = entry.get("kind") or "unnamed"
		name = entry.get("file")
		if not name or not frappe.db.exists("File", name):
			problems.append(_("{0}: the file record is gone.").format(kind))
			continue
		try:
			content = frappe.get_doc("File", name).get_content()
		except FileNotFoundError:
			problems.append(_("{0}: recorded, but the bytes are not on disk.").format(kind))
			continue
		except Exception as error:
			problems.append(_("{0}: could not be read. {1}").format(kind, type(error).__name__))
			continue

		if isinstance(content, str):
			content = content.encode("utf-8")
		checked += 1

		expected = entry.get("sha256")
		if expected and sha256_hex(content) != expected:
			problems.append(_("{0}: the bytes have changed since they were kept.").format(kind))
		size = entry.get("bytes")
		if size is not None and len(content) != size:
			problems.append(_("{0}: {1} bytes now, {2} when it was kept.").format(kind, len(content), size))

	return {
		"submission": submission,
		"company": row.company,
		"state": row.evidence_state,
		"checked": checked,
		"problems": problems,
	}


def check_all(limit: int = BATCH) -> dict:
	"""Read back the evidence for a bounded run of submissions.

	Returns a summary rather than a list of everything, because the useful
	answer on a healthy site is a count and on an unhealthy one is the
	handful that are wrong.
	"""
	names = frappe.get_all(
		SUBMISSION_DOCTYPE,
		filters={"evidence_state": "Complete"},
		fields=["name"],
		order_by="creation desc",
		limit=limit,
	)

	wrong = []
	files = 0
	for row in names:
		found = check_one(row.name)
		files += found["checked"]
		if found["problems"]:
			wrong.append(found)

	return {
		"submissions": len(names),
		"files": files,
		"intact": len(names) - len(wrong),
		"wrong": wrong,
	}


@frappe.whitelist()
def check_evidence(limit: int = BATCH) -> dict:
	"""The same check, for somebody who asked for it.

	Manager only, because it reads across companies and its answer is about
	the deployment rather than about one invoice.
	"""
	if not frappe.has_permission(SUBMISSION_DOCTYPE, "write"):
		raise frappe.PermissionError
	return check_all(int(limit))


def after_restore() -> dict:
	"""What to run once a restored site is up.

	Two separate questions. Is the evidence we hold still intact, and has
	anything been left mid flight by the backup being taken while work was
	in the air. Neither is repaired here.
	"""
	from uae_compliance.services.outbox import LOG_DOCTYPE

	evidence = check_all()
	in_the_air = frappe.db.count(LOG_DOCTYPE, {"state": "Pending"})
	unknown = frappe.db.count(SUBMISSION_DOCTYPE, {"processing_state": "Unknown"})

	return {
		"evidence": evidence,
		"requests_with_no_answer": in_the_air,
		"outcomes_not_known": unknown,
		"ready_to_resume": not evidence["wrong"] and not in_the_air and not unknown,
	}
