"""Two short strings that say whether anything has moved.

A draft that was checked yesterday may not still be right today. The source
invoice can be edited, and so can the masters it leans on. Rather than
rechecking everything on every form load, the check records a fingerprint of
what it read, and a later load compares.

The fingerprints only have to change when something relevant changes. They
are not evidence of what the invoice said, which is the frozen snapshot's
job, so they carry no amounts and nothing private.
"""

from __future__ import annotations

from uae_compliance.domain.encoding import sha256_hex

# The source fields a compliance check actually depends on. A change to any
# of these can change the outcome, so they are what the fingerprint covers.
# Adding a field here is safe. Leaving one out means a stale check can look
# current, so err towards including it.
WATCHED = (
	"modified",
	"docstatus",
	"company",
	"customer",
	"customer_address",
	"shipping_address_name",
	"company_address",
	"currency",
	"conversion_rate",
	"posting_date",
	"due_date",
	"is_return",
	"return_against",
	"is_debit_note",
	"po_no",
	"po_date",
	"net_total",
	"total_taxes_and_charges",
	"grand_total",
	"rounding_adjustment",
	"rounded_total",
	"discount_amount",
	"apply_discount_on",
	"additional_discount_percentage",
	"total_advance",
	"incoterm",
	"named_place",
	"from_date",
	"to_date",
)


def source_fingerprint(invoice) -> str:
	"""What this invoice looked like when it was read.

	`modified` alone would do for a saved document, but a preview runs on
	values that are not saved yet, where `modified` has not moved. So the
	values that matter are named rather than assumed.
	"""
	parts = [f"{name}={_flat(invoice.get(name))}" for name in WATCHED]
	for row in invoice.get("items") or []:
		parts.append(
			"item:"
			+ ",".join(
				_flat(row.get(name))
				for name in ("name", "item_code", "qty", "uom", "rate", "net_amount", "item_tax_template")
			)
		)
	for row in invoice.get("taxes") or []:
		parts.append(
			"tax:"
			+ ",".join(
				_flat(row.get(name))
				for name in ("name", "account_head", "rate", "tax_amount", "included_in_print_rate")
			)
		)
	return sha256_hex("\n".join(parts).encode("utf-8"))


def master_fingerprint(revisions: dict[str, str]) -> str:
	"""What the masters looked like when they were read.

	Sorted, so the same set of records always produces the same string
	whatever order they happened to be read in.
	"""
	parts = [f"{key}={value}" for key, value in sorted(revisions.items())]
	return sha256_hex("\n".join(parts).encode("utf-8"))


def _flat(value) -> str:
	if value is None:
		return ""
	return str(value)
