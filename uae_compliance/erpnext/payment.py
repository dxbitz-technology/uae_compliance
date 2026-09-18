"""How the invoice says it is paid.

The AE rules require a payment means code on an invoice, so something has to
answer. ERPNext records how an invoice was paid through Mode of Payment,
which has a type rather than an official code, so the two are lined up here.

Where nothing was recorded the code is 1, which is the published value for an
instrument that has not been stated. That is a statement of absence, not a
guess at the answer. It is flagged so a reader can see the invoice said
nothing rather than assume it said something.
"""

from __future__ import annotations

import frappe

from uae_compliance.domain.findings import Finding, Severity, SourceRef, Stage

CODE_NO_PAYMENT_MEANS = "MAP-0006"

NOT_STATED = "1"

# Mode of Payment carries a type, not an official code. Cash is cash, and a
# bank entry is a transfer to a bank account. Anything else has no safe
# equivalent, so it says nothing rather than something wrong.
BY_TYPE = {
	"Cash": "10",
	"Bank": "42",
}


def means(invoice, source: SourceRef, out) -> tuple[dict, Finding | None]:
	"""The payment means block, and anything worth saying about it."""
	mode = _mode_of_payment(invoice)
	if not mode:
		return {"means_code": NOT_STATED}, _unstated(source)

	kind = frappe.db.get_value("Mode of Payment", mode, "type")
	out.seen("Mode of Payment", mode)
	code = BY_TYPE.get(kind)
	if not code:
		return {"means_code": NOT_STATED, "terms": invoice.terms or None}, _unstated(source, mode)

	block = {"means_code": code}
	if invoice.terms:
		block["terms"] = invoice.terms
	return block, None


def _mode_of_payment(invoice) -> str | None:
	for row in invoice.get("payments") or []:
		if row.mode_of_payment:
			return row.mode_of_payment
	return None


def _unstated(source: SourceRef, mode: str | None = None) -> Finding:
	return Finding(
		code=CODE_NO_PAYMENT_MEANS,
		severity=Severity.WARNING,
		stage=Stage.MAPPING,
		message="The invoice does not say how it is paid, so the payment means is left unstated.",
		path="payment.means_code",
		source=source,
		repair="Record a mode of payment on the invoice.",
		params={"mode": mode or ""},
	)
