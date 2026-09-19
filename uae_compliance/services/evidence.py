"""Getting at the files this app keeps, and stopping anybody else.

The framework already ties a private file to whatever it is attached to, so
reading a submission's evidence needs permission on that submission. What it
does not stop is somebody turning a private file public, or replacing the
bytes under a hash that is supposed to prove what was sent. Those are what
this file stops.

Downloading goes through one action that takes an opaque identifier and
works out the company itself. A caller never says which company it is asking
about, because a caller that can say it can also lie about it.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

SUBMISSION_DOCTYPE = "UAE Peppol Submission"
OWNED_DOCTYPES = (SUBMISSION_DOCTYPE, "UAE Peppol Event")


def guard_file(doc, method=None):
	"""Hook on File. Keeps evidence private and unchanged.

	Evidence is the only thing tying a document that left this system to the
	record of it. Bytes that can be swapped are not evidence, and a hash
	over swappable bytes proves nothing.
	"""
	if doc.attached_to_doctype not in OWNED_DOCTYPES:
		return

	if not doc.is_private:
		frappe.throw(_("E-invoicing evidence is private and cannot be made public."))

	if doc.is_new():
		return

	before = doc.get_doc_before_save()
	if before and before.file_url != doc.file_url:
		frappe.throw(_("E-invoicing evidence cannot be replaced."))


def guard_file_delete(doc, method=None):
	"""Hook on File. Evidence of something sent is not deleted."""
	if doc.attached_to_doctype not in OWNED_DOCTYPES:
		return
	if frappe.session.user == "Administrator" and frappe.flags.in_uninstall:
		return
	frappe.throw(_("E-invoicing evidence is kept."))


@frappe.whitelist()
def download_artifact(submission: str, kind: str) -> dict:
	"""Fetch one piece of evidence, if the caller may read its submission.

	Returns where to get it rather than the bytes, so the framework's own
	file handling stays the one path that serves a private file.
	"""
	doc = frappe.get_doc(SUBMISSION_DOCTYPE, submission)
	doc.check_permission("read")

	manifest = json.loads(doc.evidence_manifest or "[]")
	entry = next((item for item in manifest if item.get("kind") == kind), None)
	if not entry:
		frappe.throw(_("There is nothing of that kind kept for this submission."))

	file_url = frappe.db.get_value("File", entry["file"], "file_url")
	if not file_url:
		frappe.throw(_("That evidence is recorded but its file is missing."))

	return {
		"kind": entry["kind"],
		"file_url": file_url,
		"sha256": entry.get("sha256"),
		"bytes": entry.get("bytes"),
		"source": entry.get("source"),
	}


@frappe.whitelist()
def list_artifacts(submission: str) -> list[dict]:
	"""What is kept for this submission, without the files themselves."""
	doc = frappe.get_doc(SUBMISSION_DOCTYPE, submission)
	doc.check_permission("read")
	manifest = json.loads(doc.evidence_manifest or "[]")
	return [
		{
			"kind": entry.get("kind"),
			"sha256": entry.get("sha256"),
			"bytes": entry.get("bytes"),
			"mime": entry.get("mime"),
			"source": entry.get("source"),
		}
		for entry in manifest
	]
