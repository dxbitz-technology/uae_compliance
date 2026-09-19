"""Which invoices are ready and which are not, and what is missing.

The point of this report is the last column. A list of invoices that says
Needs details and nothing else makes somebody open each one to find out why.
This carries the reason across, so a person can work through a morning's
worth without opening anything.
"""

import json

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columns(), rows(filters)


def columns():
	return [
		{
			"fieldname": "sales_invoice",
			"label": _("Invoice"),
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 160,
		},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 170,
		},
		{
			"fieldname": "grand_total",
			"label": _("Total"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 110,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 80,
			"hidden": 1,
		},
		{"fieldname": "mode", "label": _("Mode"), "fieldtype": "Data", "width": 100},
		{"fieldname": "readiness", "label": _("Readiness"), "fieldtype": "Data", "width": 150},
		{"fieldname": "errors", "label": _("Errors"), "fieldtype": "Int", "width": 70},
		{"fieldname": "checked_at", "label": _("Last Checked"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "needs", "label": _("What Is Missing"), "fieldtype": "Data", "width": 400},
	]


def rows(filters):
	conditions = {}
	if filters.get("company"):
		conditions["company"] = filters.company
	if filters.get("readiness"):
		conditions["readiness"] = filters.readiness

	records = frappe.get_all(
		"UAE Peppol Invoice",
		filters=conditions,
		fields=["name", "sales_invoice", "company", "mode", "readiness", "errors", "checked_at", "findings"],
		order_by="modified desc",
		limit=500,
	)
	if not records:
		return []

	# One query for every invoice rather than one per row. A month of
	# invoices should not be a month of round trips.
	invoice_filters = {"name": ["in", [row.sales_invoice for row in records]]}
	if filters.get("from_date") and filters.get("to_date"):
		invoice_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		invoice_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		invoice_filters["posting_date"] = ["<=", filters.to_date]

	sources = {
		row.name: row
		for row in frappe.get_all(
			"Sales Invoice",
			filters=invoice_filters,
			fields=["name", "posting_date", "customer", "grand_total", "currency"],
		)
	}

	out = []
	for record in records:
		source = sources.get(record.sales_invoice)
		if not source:
			# Either filtered out by date, or the caller cannot read it.
			continue
		out.append(
			{
				"sales_invoice": record.sales_invoice,
				"company": record.company,
				"posting_date": source.posting_date,
				"customer": source.customer,
				"grand_total": source.grand_total,
				"currency": source.currency,
				"mode": record.mode,
				"readiness": record.readiness,
				"errors": record.errors,
				"checked_at": record.checked_at,
				"needs": summarise(record.findings),
			}
		)
	return out


def summarise(findings: str | None) -> str:
	"""The first few things wrong, in words, rather than a count."""
	if not findings:
		return ""
	try:
		items = json.loads(findings)
	except ValueError:
		return ""
	messages = [item.get("message", "") for item in items if item.get("severity") == "Error"]
	if not messages:
		messages = [item.get("message", "") for item in items]
	shown = messages[:3]
	if len(messages) > 3:
		shown.append(_("and {0} more").format(len(messages) - 3))
	return " ".join(shown)
