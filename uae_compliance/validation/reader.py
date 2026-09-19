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

from uae_compliance.validation.safe_xml import UnsafeDocument, parse_bytes

CBC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"
CAC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"

# Far more lines than any real invoice carries. The size limit alone leaves
# room for tens of thousands of them, and each line becomes a lookup and a
# row in a draft, so the document decides how much work we do unless this
# says otherwise.
MAX_LINES = 1000


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
		# The buyer's own order number, when the document names one. It is
		# how an arrived invoice finds the purchase order it answers.
		"order_reference": _text(root, f"{CAC}OrderReference/{CBC}ID"),
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


def lines(data: bytes) -> list[dict]:
	"""Every line of an incoming document, as it states them.

	Their item codes are theirs. Nothing here tries to turn one into ours,
	because that is a matching decision and it belongs where a person can
	see it.
	"""
	tree = parse_bytes(data)
	root = tree.getroot() if hasattr(tree, "getroot") else tree
	credit_note = root.tag.endswith("CreditNote")
	tag = f"{CAC}CreditNoteLine" if credit_note else f"{CAC}InvoiceLine"
	quantity_tag = f"{CBC}CreditedQuantity" if credit_note else f"{CBC}InvoicedQuantity"

	nodes = root.findall(tag)
	if len(nodes) > MAX_LINES:
		raise UnsafeDocument(f"{len(nodes)} lines is more than the {MAX_LINES} line limit")

	found = []
	for node in nodes:
		quantity = node.find(quantity_tag)
		item = node.find(f"{CAC}Item")
		price = node.find(f"{CAC}Price")
		category = node.find(f"{CAC}Item/{CAC}ClassifiedTaxCategory")
		found.append(
			{
				"id": _text(node, f"{CBC}ID"),
				"quantity": _as_decimal(quantity.text if quantity is not None else None),
				"uom_code": quantity.get("unitCode") if quantity is not None else None,
				"name": _text(item, f"{CBC}Name") if item is not None else "",
				"description": _text(item, f"{CBC}Description") if item is not None else "",
				"their_code": _their_code(item),
				"net_price": _number(price, f"{CBC}PriceAmount"),
				"net_amount": _number(node, f"{CBC}LineExtensionAmount"),
				"tax_category": _text(category, f"{CBC}ID") if category is not None else "",
				"tax_rate": _number(category, f"{CBC}Percent") if category is not None else None,
			}
		)
	return found


def _their_code(item) -> str:
	"""Whatever the sender calls this thing.

	Their own identification first, then the standard one. Both are their
	names for it and neither is ours.
	"""
	if item is None:
		return ""
	for path in (
		f"{CAC}SellersItemIdentification/{CBC}ID",
		f"{CAC}StandardItemIdentification/{CBC}ID",
		f"{CAC}AdditionalItemIdentification/{CBC}ID",
	):
		found = item.find(path)
		if found is not None and found.text:
			return found.text.strip()
	return ""
