"""Reading a document somebody else wrote.

The serializer's opposite, and deliberately much smaller. It pulls out what
a person needs to decide what to do with an incoming invoice: who sent it,
what it is, and what it says is owed. It does not rebuild the canonical
model, because we did not produce this document and a faithful copy of
somebody else's invoice is the XML itself, which is kept.

Everything comes through the hardened parse. A document from outside is the
one place where a hostile file is a real possibility.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from uae_compliance.validation.safe_xml import parse_bytes

CBC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"
CAC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"


def summarise(data: bytes) -> dict:
	"""What one incoming document says, in plain fields.

	Anything it does not say comes back empty rather than guessed. A missing
	value on somebody else's invoice is their omission to explain, not ours
	to fill in.
	"""
	tree = parse_bytes(data)
	# The hardened parse hands back a tree. Everything below works on the
	# document element itself.
	root = tree.getroot() if hasattr(tree, "getroot") else tree
	credit_note = root.tag.endswith("CreditNote")

	supplier = _party(root, "AccountingSupplierParty")
	customer = _party(root, "AccountingCustomerParty")
	totals = _totals(root)

	return {
		"is_credit_note": credit_note,
		"document_number": _text(root, f"{CBC}ID"),
		"document_uuid": _text(root, f"{CBC}UUID"),
		"issue_date": _text(root, f"{CBC}IssueDate"),
		"type_code": _text(root, f"{CBC}CreditNoteTypeCode" if credit_note else f"{CBC}InvoiceTypeCode"),
		"currency": _text(root, f"{CBC}DocumentCurrencyCode"),
		"supplier_name": supplier["name"],
		"supplier_tax_id": supplier["tax_id"],
		"supplier_endpoint": supplier["endpoint"],
		"customer_name": customer["name"],
		"customer_tax_id": customer["tax_id"],
		"customer_endpoint": customer["endpoint"],
		"line_count": len(root.findall(f"{CAC}CreditNoteLine" if credit_note else f"{CAC}InvoiceLine")),
		**totals,
	}


def _party(root, wrapper: str) -> dict:
	node = root.find(f"{CAC}{wrapper}/{CAC}Party")
	if node is None:
		return {"name": "", "tax_id": "", "endpoint": ""}
	legal = node.find(f"{CAC}PartyLegalEntity/{CBC}RegistrationName")
	name = legal.text if legal is not None and legal.text else ""
	if not name:
		trading = node.find(f"{CAC}PartyName/{CBC}Name")
		name = trading.text if trading is not None and trading.text else ""
	return {
		"name": (name or "").strip(),
		"tax_id": _text(node, f"{CAC}PartyTaxScheme/{CBC}CompanyID"),
		"endpoint": _text(node, f"{CBC}EndpointID"),
	}


def _totals(root) -> dict:
	monetary = root.find(f"{CAC}LegalMonetaryTotal")
	tax = root.find(f"{CAC}TaxTotal/{CBC}TaxAmount")
	return {
		"tax_exclusive": _number(monetary, f"{CBC}TaxExclusiveAmount"),
		"tax_inclusive": _number(monetary, f"{CBC}TaxInclusiveAmount"),
		"payable": _number(monetary, f"{CBC}PayableAmount"),
		"tax_total": _as_decimal(tax.text if tax is not None else None),
	}


def _text(node, path: str) -> str:
	if node is None:
		return ""
	found = node.find(path) if "/" in path or path.startswith("{") else None
	if found is None:
		found = node.find(path)
	return (found.text or "").strip() if found is not None and found.text else ""


def _number(node, path: str) -> Decimal | None:
	if node is None:
		return None
	found = node.find(path)
	return _as_decimal(found.text if found is not None else None)


def _as_decimal(value) -> Decimal | None:
	if value is None or not str(value).strip():
		return None
	try:
		return Decimal(str(value).strip())
	except InvalidOperation:
		return None
