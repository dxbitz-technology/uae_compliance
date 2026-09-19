"""Collecting the documents suppliers have sent us.

Everything here stops short of the accounts. A supplier's invoice arriving
is a claim about what we owe, and a claim gets looked at by somebody before
it becomes a liability in the books. Nothing is posted, no supplier is
created, and no item is invented to make a line fit.

The place marker is kept on the connection, so a restart carries on where it
left off rather than reading the whole inbox again. A document that arrives
twice is recognised by the provider's own reference, and the same reference
turning up with different contents is an integrity problem rather than a
duplicate.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from uae_compliance.connectors import registry as connectors
from uae_compliance.connectors.transport import Transport
from uae_compliance.domain.connector import Disposition, Operation
from uae_compliance.domain.encoding import sha256_hex

INBOUND_DOCTYPE = "UAE Peppol Inbound"
ASP_DOCTYPE = "UAE Peppol ASP"

# One page at a time. A provider's inbox can be long and nothing good comes
# of reading all of it into one worker.
PAGE_SIZE = 20


def collect_all(limit_pages: int = 5) -> int:
	"""Scheduler entry. Collect from every connection that was asked to."""
	total = 0
	for name in frappe.get_all(ASP_DOCTYPE, filters={"enabled": 1, "receive_enabled": 1}, pluck="name"):
		total += collect(name, limit_pages)
	return total


def collect(connection_name: str, limit_pages: int = 5) -> int:
	"""Read this connection's inbox, from wherever it had got to."""
	from uae_compliance.services.recorder import FrappeRecorder
	from uae_compliance.services.sending import _connection_and_adapter_for, _policy_for

	asp = frappe.get_doc(ASP_DOCTYPE, connection_name)
	if not asp.receive_enabled:
		return 0

	connection, adapter = _connection_and_adapter_for(asp, Operation.FETCH_INBOUND)
	recorder = FrappeRecorder(None, None, asp.name)
	transport = Transport(_policy_for(connection, adapter), recorder)

	cursor = asp.inbound_cursor
	stored = 0

	for _page in range(limit_pages):
		call = connectors.Call(
			operation=Operation.FETCH_INBOUND,
			connection=connection,
			cursor=cursor,
			page_size=PAGE_SIZE,
			correlation=asp.name,
		)
		outcome = adapter.perform(call, transport)
		if outcome.disposition is not Disposition.SUCCEEDED:
			break

		for artifact in outcome.artifacts:
			if artifact.kind == "inbound" and artifact.fetched:
				stored += _land(asp, artifact)

		# The marker moves only after the page is safely down. A crash
		# between the two reads the same page again, which the duplicate
		# check handles, and that is the right way round.
		frappe.db.set_value(
			ASP_DOCTYPE,
			asp.name,
			{"inbound_cursor": outcome.event_cursor, "inbound_checked_at": now_datetime()},
			update_modified=False,
		)
		frappe.db.commit()

		cursor = outcome.event_cursor
		if not cursor:
			break

	return stored


def _land(asp, artifact) -> int:
	"""Keep one arrived document, unless we already have it."""
	digest = sha256_hex(artifact.body)
	existing = frappe.db.get_value(
		INBOUND_DOCTYPE,
		{"connection": asp.name, "document_uuid": artifact.identifier},
		["name", "payload_digest"],
		as_dict=True,
	)
	if existing:
		if existing.payload_digest != digest:
			# Same reference, different document. Somebody has to look at
			# that rather than us picking one.
			_keep_conflict(existing.name, artifact, digest)
		return 0

	summary = _read(artifact.body)
	doc = frappe.new_doc(INBOUND_DOCTYPE)
	doc.connection = asp.name
	doc.environment = asp.environment
	doc.provider_key = asp.provider_key
	doc.received_at = now_datetime()
	doc.payload_digest = digest
	doc.document_uuid = artifact.identifier
	doc.state = "Received"

	for field, value in summary.items():
		if doc.meta.has_field(field) and value not in (None, ""):
			doc.set(field, value)

	# Frappe fills a company link from the site default when nothing sets
	# it. On a document somebody else wrote that is worse than leaving it
	# blank: a supplier's invoice would be attributed to whichever company
	# happens to be the default rather than the one it was addressed to.
	doc.company = None
	try:
		doc.insert(ignore_permissions=True)
	except frappe.UniqueValidationError, frappe.DuplicateEntryError:
		# Two collectors racing the same page. The check above reads before
		# it writes, so both can pass it; the database kept the first
		# landing and this one is the duplicate it would have seen.
		return 0
	_store_body(doc, artifact)
	_match(doc, summary)
	return 1


def _keep_conflict(name: str, artifact, digest: str):
	"""The same reference arrived again saying something else.

	The difference between the two bodies is the evidence, so the later one
	is kept beside the first rather than dropped. The person who looks at
	this decides which one is real; nothing here does.
	"""
	marker = f"{name}-conflict-{digest[:12]}.xml"
	if not frappe.db.exists(
		"File", {"attached_to_doctype": INBOUND_DOCTYPE, "attached_to_name": name, "file_name": marker}
	):
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": marker,
				"attached_to_doctype": INBOUND_DOCTYPE,
				"attached_to_name": name,
				"is_private": 1,
				"content": artifact.body,
			}
		).insert(ignore_permissions=True)
	frappe.db.set_value(
		INBOUND_DOCTYPE,
		name,
		{
			"state": "Unmatched",
			"match_note": _("This arrived again with different contents. Both versions are kept."),
		},
	)


def _read(body: bytes) -> dict:
	"""What the document says, or nothing useful if it will not parse."""
	from uae_compliance.validation.reader import summarise

	try:
		found = summarise(body)
	except Exception:
		return {"validation_state": "Unavailable", "validation_note": _("This document could not be read.")}

	return {
		"supplier_name": found["supplier_name"],
		"supplier_tax_id": found["supplier_tax_id"],
		"supplier_endpoint": found["supplier_endpoint"],
		"document_number": found["document_number"],
		"type_code": found["type_code"],
		"issue_date": found["issue_date"],
		"order_reference": found["order_reference"],
		"currency": found["currency"],
		"tax_exclusive": found["tax_exclusive"],
		"tax_total": found["tax_total"],
		"payable": found["payable"],
		"line_count": found["line_count"],
		"_customer_tax_id": found["customer_tax_id"],
	}


def _store_body(doc, artifact):
	saved = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{doc.name}-inbound.xml",
			"attached_to_doctype": INBOUND_DOCTYPE,
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": artifact.body,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value(INBOUND_DOCTYPE, doc.name, "payload_file", saved.name, update_modified=False)


def _match(doc, summary: dict):
	"""Work out who sent it and who it is for, without inventing either.

	A supplier is matched by its tax number or its network address. A name
	is not enough and a near miss is not a match. Where nothing matches, the
	document waits for a person, because creating a supplier record from a
	document somebody else wrote is how a fake invoice becomes a real payee.
	"""
	notes = []
	supplier = _find_supplier(doc.supplier_tax_id, doc.supplier_endpoint)
	if supplier:
		frappe.db.set_value(INBOUND_DOCTYPE, doc.name, "supplier", supplier, update_modified=False)
		notes.append(_("Supplier matched on its tax number or network address."))
	else:
		notes.append(_("No supplier matches this sender. Nothing is created from the document."))

	company = _find_company(summary.get("_customer_tax_id"))
	# Written either way. Leaving the field alone would let a default put
	# something back.
	frappe.db.set_value(INBOUND_DOCTYPE, doc.name, "company", company, update_modified=False)
	if not company:
		notes.append(_("It is not clear which company this was sent to."))

	frappe.db.set_value(
		INBOUND_DOCTYPE,
		doc.name,
		{
			"match_note": " ".join(notes),
			"state": "Received" if supplier and company else "Unmatched",
		},
		update_modified=False,
	)


def _find_supplier(tax_id: str | None, endpoint: str | None) -> str | None:
	if tax_id:
		found = frappe.db.get_value("Supplier", {"tax_id": tax_id}, "name")
		if found:
			return found
		profile = frappe.db.get_value(
			"UAE Peppol Party Profile",
			{"party_doctype": "Supplier", "vat_number": tax_id},
			"party",
		)
		if profile:
			return profile
	if endpoint:
		return frappe.db.get_value(
			"UAE Peppol Party Profile",
			{"party_doctype": "Supplier", "endpoint_value": endpoint},
			"party",
		)
	return None


def _find_company(tax_id: str | None) -> str | None:
	"""Which of our companies this was addressed to.

	By tax number only. Guessing from a name would put a supplier's invoice
	against the wrong books.
	"""
	if not tax_id:
		return None
	found = frappe.db.get_value("Company", {"tax_id": tax_id}, "name")
	if found:
		return found
	# A VAT group shares one number across profiles, so more than one match
	# says nothing about which entity the document was for. Picking one
	# would attribute a supplier's invoice by luck.
	sellers = frappe.get_all(
		"UAE Peppol Seller Profile", filters={"vat_number": tax_id}, pluck="name", limit=2
	)
	if len(sellers) != 1:
		return None
	seller = sellers[0]

	# A profile can cover several companies, and a tax number shared across
	# a group tells us nothing about which of them the document was for.
	# Picking the first row would attribute a supplier's invoice by luck.
	companies = frappe.get_all(
		"UAE Peppol Seller Company",
		filters={"parent": seller, "parenttype": "UAE Peppol Seller Profile"},
		pluck="company",
	)
	return companies[0] if len(companies) == 1 else None
