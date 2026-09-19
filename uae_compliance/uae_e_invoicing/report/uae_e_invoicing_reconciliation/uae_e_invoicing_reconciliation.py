"""Everything that has gone quiet, in one place.

This is the report somebody opens when they want to know whether anything
has been forgotten. It deliberately does not only list problems with the
provider. Most of what goes wrong in a system like this is work that fell
between two steps: an invoice submitted with nothing watching it, a
submission nobody approved, an attempt that went out and never came back.

Each row says what it is and what to do about it, because a list of
identifiers with no explanation is a list somebody scrolls past.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

# How long something may sit before it is worth mentioning. Short enough to
# be useful, long enough that ordinary work in progress does not show up.
QUIET_MINUTES = 30


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), rows(filters)


def columns():
	return [
		{"fieldname": "issue", "label": _("What"), "fieldtype": "Data", "width": 220},
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 160,
		},
		{
			"fieldname": "reference",
			"label": _("Record"),
			"fieldtype": "Dynamic Link",
			"options": "reference_type",
			"width": 180,
		},
		{"fieldname": "reference_type", "label": _("Type"), "fieldtype": "Data", "width": 190},
		{"fieldname": "since", "label": _("Since"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "detail", "label": _("What To Do"), "fieldtype": "Data", "width": 420},
	]


def rows(filters):
	company = filters.get("company")
	found = []
	found += submitted_with_nothing_watching(company)
	found += unapproved(company)
	found += attempts_that_never_came_back(company)
	found += outcomes_nobody_knows(company)
	found += missing_evidence(company)
	found += stale_drafts(company)
	found.sort(key=lambda row: row.get("since") or now_datetime(), reverse=False)
	return found


def submitted_with_nothing_watching(company):
	"""An invoice that was submitted in a company we cover, with no record.

	This is the one that matters most. It means an invoice went through the
	books and the app never saw it, so nobody is going to notice it was
	never sent.
	"""
	companies = _live_companies(company)
	if not companies:
		return []

	watched = set(frappe.get_list("UAE Peppol Invoice", pluck="sales_invoice"))
	rows = frappe.get_list(
		"Sales Invoice",
		filters={"docstatus": 1, "company": ["in", companies]},
		fields=["name", "company", "posting_date", "modified"],
		order_by="modified desc",
		limit=500,
	)
	return [
		{
			"issue": _("Submitted, never looked at"),
			"company": row.company,
			"reference": row.name,
			"reference_type": "Sales Invoice",
			"since": row.modified,
			"detail": _(
				"This invoice was submitted while the company was switched on and has no e-invoicing record."
			),
		}
		for row in rows
		if row.name not in watched
	]


def unapproved(company):
	cutoff = add_to_date(now_datetime(), minutes=-QUIET_MINUTES)
	rows = frappe.get_list(
		"UAE Peppol Submission",
		filters=_with_company({"processing_state": "Awaiting review", "modified": ["<", cutoff]}, company),
		fields=["name", "company", "document_number", "modified"],
		limit=200,
	)
	return [
		{
			"issue": _("Waiting for review"),
			"company": row.company,
			"reference": row.name,
			"reference_type": "UAE Peppol Submission",
			"since": row.modified,
			"detail": _("{0} is frozen and ready but nobody has approved it.").format(row.document_number),
		}
		for row in rows
	]


def attempts_that_never_came_back(company):
	rows = frappe.get_list(
		"UAE Peppol Transmission Log",
		filters=_with_company({"state": "Pending"}, company),
		fields=["attempt_id", "company", "submission", "operation", "started_at"],
		limit=200,
	)
	return [
		{
			"issue": _("A request with no answer"),
			"company": row.company,
			"reference": row.submission,
			"reference_type": "UAE Peppol Submission",
			"since": row.started_at,
			"detail": _(
				"A {0} went out and nothing came back. It may have arrived, so it is never simply sent again."
			).format(row.operation),
		}
		for row in rows
	]


def outcomes_nobody_knows(company):
	rows = frappe.get_list(
		"UAE Peppol Submission",
		filters=_with_company({"processing_state": ["in", ["Unknown", "Attention required"]]}, company),
		fields=["name", "company", "document_number", "processing_state", "attention_reason", "modified"],
		limit=200,
	)
	return [
		{
			"issue": _("Needs a person"),
			"company": row.company,
			"reference": row.name,
			"reference_type": "UAE Peppol Submission",
			"since": row.modified,
			"detail": row.attention_reason
			or _("{0} is {1}.").format(row.document_number, row.processing_state),
		}
		for row in rows
	]


def missing_evidence(company):
	"""Delivered and reported, but we are not holding what proves it."""
	rows = frappe.get_list(
		"UAE Peppol Submission",
		filters=_with_company(
			{"evidence_state": ["in", ["Pending", "Unavailable", "Invalid"]], "asp_receipt": "Received"},
			company,
		),
		fields=["name", "company", "document_number", "evidence_state", "modified"],
		limit=200,
	)
	return [
		{
			"issue": _("Evidence not held"),
			"company": row.company,
			"reference": row.name,
			"reference_type": "UAE Peppol Submission",
			"since": row.modified,
			"detail": _("{0} reached the provider but its evidence is {1}.").format(
				row.document_number, row.evidence_state.lower()
			),
		}
		for row in rows
	]


def stale_drafts(company):
	"""Checked once, then something underneath it moved."""
	rows = frappe.get_list(
		"UAE Peppol Invoice",
		filters=_with_company({"readiness": "Stale"}, company),
		fields=["sales_invoice", "company", "modified"],
		limit=200,
	)
	return [
		{
			"issue": _("Checked, then changed"),
			"company": row.company,
			"reference": row.sales_invoice,
			"reference_type": "Sales Invoice",
			"since": row.modified,
			"detail": _("Something this invoice depends on has changed since it was checked."),
		}
		for row in rows
	]


def _live_companies(company):
	filters = {"parenttype": "UAE Peppol Seller Profile", "mode": ["in", ["Preparation", "Live"]]}
	if company:
		filters["company"] = company
	return frappe.get_list("UAE Peppol Seller Company", filters=filters, pluck="company")


def _with_company(filters: dict, company) -> dict:
	if company:
		filters["company"] = company
	return filters
