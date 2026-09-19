"""Freezing what goes out, at the moment the invoice is submitted.

This is the point where a draft stops being something anyone can change and
becomes a record of what was sent. Everything it needs is settled here, in
the invoice's own transaction, so either the invoice submits with its
submission or neither happens.

Two things follow from that and shape the whole file. The bytes are written
and read back before the work is allowed to be sendable, because a database
transaction does not roll back a file and work that can transmit without its
request evidence is worse than work that cannot transmit. And the control row
is locked first, so two people submitting at once produce one submission
rather than two documents with the same number.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from uae_compliance.domain.canonical import VOLATILE_PATHS
from uae_compliance.domain.encoding import business_hash, canonical_bytes, payload_hash, sha256_hex
from uae_compliance.domain.findings import Level
from uae_compliance.domain.scope import Mode
from uae_compliance.services import validation
from uae_compliance.services.working import WORKING_DOCTYPE, mode_for, record_for_submission
from uae_compliance.validation.artifacts import PINT_VERSION
from uae_compliance.validation.serializer import SERIALIZER_VERSION, to_xml

SUBMISSION_DOCTYPE = "UAE Peppol Submission"

# States that mean a submission is still doing something. Only one of these
# may exist for a working record at a time.
ACTIVE_STATES = (
	"Awaiting review",
	"Ready",
	"Sending",
	"Awaiting outcome",
	"Retry scheduled",
	"Unknown",
	"Attention required",
)


class NotFrozen(Exception):
	"""Nothing was frozen, and the reason is worth carrying."""


def freeze_on_submit(invoice) -> str | None:
	"""Make the submission for this invoice, if it is one we send.

	Called from the invoice's own submit, so it runs inside that transaction.
	Returns the submission name, or nothing when there is nothing to send.
	"""
	if mode_for(invoice.company) is not Mode.LIVE:
		# Preparation checks and shows and sends nothing, so it freezes
		# nothing. A snapshot from a simulation is a separate, clearly marked
		# thing and never becomes this one.
		return None

	control = frappe.db.get_value(WORKING_DOCTYPE, {"sales_invoice": invoice.name}, "name")
	if not control:
		# Drafted while the company was off and submitted after it went Live,
		# with no save in between. Returning nothing here submitted the
		# invoice with nobody watching it, and only the reconciliation report
		# would ever say so. Made now, in the same transaction, so a refusal
		# further down still takes the record away with it.
		control = record_for_submission(invoice)
	if not control:
		return None

	# Lock first. Everything after this reads a view nobody else can move.
	frappe.db.sql(f"select name from `tab{WORKING_DOCTYPE}` where name = %s for update", (control,))

	if _already_active(control):
		# Not an error. A second submit of the same invoice should find the
		# work that is already there rather than make a rival copy of it.
		return _already_active(control)

	# The connection is resolved before anything is built, because a Live
	# company with nowhere to send is a configuration gap to say plainly,
	# and the environment on the frozen document is the connection's own.
	connection = sending_connection(invoice.company)

	result = validation.check(invoice, Level.FULL)
	if result.errors:
		frappe.throw(
			_("{0} details need attention before this invoice can be sent.").format(len(result.errors)),
			title=_("Cannot freeze yet"),
		)

	from uae_compliance.erpnext.extract import extract

	document, _findings = extract(invoice, environment=connection.environment)
	if document is None:
		raise NotFrozen("the company was switched off while freezing")

	return create_submission(invoice, control, document, result, connection)


def _already_active(control: str) -> str | None:
	return frappe.db.get_value(
		SUBMISSION_DOCTYPE,
		{"control": control, "processing_state": ["in", ACTIVE_STATES]},
		"name",
	)


def sending_connection(company: str):
	"""The connection this company's seller sends through, resolved now.

	A submission frozen without one is work no worker can carry, discovered
	only when the queue quietly parks it for attention. Missing configuration
	is said here instead, while the person who can fix it is looking.
	"""
	profile = frappe.db.get_value(
		"UAE Peppol Seller Company",
		{"company": company, "parenttype": "UAE Peppol Seller Profile"},
		"parent",
	)
	asp_name = profile and frappe.db.get_value("UAE Peppol Seller Profile", profile, "current_asp")
	if not asp_name:
		frappe.throw(
			_(
				"The seller profile has no provider connection, so this invoice has nowhere to go. "
				"Set the current ASP on the seller profile."
			),
			title=_("No connection"),
		)
	asp = frappe.db.get_value(
		"UAE Peppol ASP",
		asp_name,
		["name", "provider_key", "environment", "config_revision", "enabled"],
		as_dict=True,
	)
	if not asp.enabled:
		frappe.throw(
			_("The connection {0} is switched off, so this invoice has nowhere to go.").format(asp.name),
			title=_("Connection disabled"),
		)

	from uae_compliance.services.sending import _installed_registry

	try:
		declaration = _installed_registry().declaration(asp.provider_key)
	except Exception:
		frappe.throw(
			_("The connection {0} names the provider {1}, which is not an installed adapter.").format(
				asp.name, asp.provider_key
			),
			title=_("No adapter"),
		)
	asp.adapter_version = declaration.adapter_version
	return asp


def create_submission(invoice, control: str, document: dict, result, connection=None) -> str:
	canonical = canonical_bytes(document)
	xml = to_xml(document)
	revision = _next_revision(control)
	uuid = document["document"]["uuid"]

	doc = frappe.new_doc(SUBMISSION_DOCTYPE)
	doc.control = control
	doc.company = invoice.company
	doc.revision = revision
	doc.document_number = document["document"]["number"]
	doc.document_uuid = uuid
	doc.type_code = document["document"]["type_code"]
	# Stable, and derived from the document rather than from a display
	# series, so it means the same thing to a provider on every attempt.
	doc.idempotency_key = f"{uuid}:{revision}"
	doc.canonical_version = document["provenance"]["schema_version"]
	doc.canonical_hash = business_hash(document, VOLATILE_PATHS)
	doc.payload_hash = payload_hash(xml)
	doc.source_fingerprint = document["provenance"]["source_fingerprint"]
	doc.master_fingerprint = document["provenance"]["master_fingerprint"]
	doc.frozen_at = now_datetime()
	doc.ruleset_version = PINT_VERSION
	doc.serializer_version = str(SERIALIZER_VERSION)
	doc.extraction_version = document["provenance"]["extraction_version"]
	doc.environment = document["context"]["environment"]
	if connection is not None:
		doc.connection = connection.name
		doc.config_revision = connection.config_revision
		doc.adapter_version = connection.adapter_version

	buyer = (document.get("parties") or {}).get("buyer") or {}
	route = buyer.get("participant") or {}
	doc.route_scheme = route.get("scheme")
	doc.route_value = route.get("value")
	doc.route_reason = "The buyer's recorded network address."

	doc.processing_state = "Awaiting review"
	doc.evidence_state = "Pending"
	doc.insert(ignore_permissions=True)

	# The bytes go down before the work can ever be picked up, and they are
	# read back to prove they are really there.
	manifest = _store(doc, canonical, xml)
	doc.db_set("evidence_manifest", frappe.as_json(manifest), update_modified=False)
	doc.db_set("evidence_state", "Complete", update_modified=False)

	frappe.db.set_value(WORKING_DOCTYPE, control, "latest_submission", doc.name, update_modified=False)
	_approve_by_policy_where_waived(doc.name)
	return doc.name


def _approve_by_policy_where_waived(submission: str):
	"""Record the policy approval for a company that has waived review.

	On the same immutable revision, in the same transaction, so the record
	says an approval was given and why, rather than the queue simply taking
	unreviewed work. A refusal, most likely a missing route, leaves the
	submission awaiting review, where the daily summary already points.
	"""
	# Imported here because the approval service reads this module's names.
	from uae_compliance.services import approval

	try:
		approval.approve_by_policy(submission)
	except frappe.ValidationError:
		pass


def _next_revision(control: str) -> int:
	highest = frappe.db.sql(
		f"select max(revision) from `tab{SUBMISSION_DOCTYPE}` where control = %s", (control,)
	)[0][0]
	return (highest or 0) + 1


def _store(submission, canonical: bytes, xml: bytes) -> list[dict]:
	"""Write the frozen artifacts and prove they can be read back.

	A file that was written but cannot be read is the same as no file, and a
	submission holding a hash for bytes nobody can fetch is not evidence of
	anything.
	"""
	manifest = []
	for kind, content, extension, mime in (
		("canonical", canonical, "json", "application/json"),
		("reference-xml", xml, "xml", "application/xml"),
	):
		name = f"{submission.name}-{kind}.{extension}"
		saved = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": name,
				"attached_to_doctype": submission.doctype,
				"attached_to_name": submission.name,
				"is_private": 1,
				"content": content,
			}
		).insert(ignore_permissions=True)

		read_back = saved.get_content()
		if isinstance(read_back, str):
			read_back = read_back.encode("utf-8")
		if sha256_hex(read_back) != sha256_hex(content):
			raise NotFrozen(f"{kind} was written but did not read back the same")

		manifest.append(
			{
				"kind": kind,
				"file": saved.name,
				"sha256": sha256_hex(content),
				"bytes": len(content),
				"mime": mime,
				"source": "This app",
			}
		)
	return manifest


def on_invoice_submit(invoice, method=None):
	"""Hook. Runs inside the invoice's own submit transaction."""
	freeze_on_submit(invoice)
