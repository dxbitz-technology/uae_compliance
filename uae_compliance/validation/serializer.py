"""Turn a canonical invoice into the XML the official rules expect.

One way in and one way out. Everything the app sends is built here, so there
is a single place to look when the output is wrong and a single place to fix
it. The validator in this package is what proves the result.

Element order matters to the schema, which is why this builds each section in
a fixed sequence rather than iterating over whatever the document happens to
carry. A published example got that order wrong and fails its own schema, so
the order here follows the schema rather than the examples.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from lxml import etree

from uae_compliance.domain.encoding import canonical_decimal
from uae_compliance.domain.schema import NotApplicable

UBL_INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
UBL_CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

SERIALIZER_VERSION = 1

# The currency the rules want everything stated in alongside its own.
LOCAL_CURRENCY = "AED"

CREDIT_NOTE_TYPES = ("381", "81")

# Our words for an item, and the single letter the rules use.
ITEM_TYPE_CODES = {"Goods": "G", "Services": "S", "Both": "B"}

# The eight scenario positions, in the published order. The string is built
# here and nowhere else, so nothing in the app depends on these positions.
SCENARIO_ORDER = (
	"free_zone",
	"deemed_supply",
	"margin_scheme",
	"summary",
	"continuous_supply",
	"agent_billing",
	"ecommerce",
	"export",
)


class SerializerError(ValueError):
	"""The document cannot be written as XML in a form the rules would accept."""


def _q(namespace: str, name: str) -> str:
	return f"{{{namespace}}}{name}"


def _text(value) -> str:
	if isinstance(value, Decimal):
		return canonical_decimal(value)
	if isinstance(value, bool):
		return "true" if value else "false"
	return str(value)


def _child(parent, namespace: str, name: str, value=None, **attributes):
	element = etree.SubElement(parent, _q(namespace, name))
	for key, attribute in attributes.items():
		if attribute is not None:
			element.set(key, _text(attribute))
	if value is not None:
		element.text = _text(value)
	return element


def _present(value) -> bool:
	"""Whether a value is there to be written.

	A field marked as not applicable is a deliberate statement that it has no
	meaning here, so it is left out of the XML rather than written as empty.
	"""
	return value is not None and not isinstance(value, NotApplicable)


def scenario_string(scenario: Mapping) -> str:
	"""The eight position transaction string, built in one place."""
	return "".join("1" if scenario.get(name) else "0" for name in SCENARIO_ORDER)


def _amount(parent, namespace, name, value, currency):
	if _present(value):
		_child(parent, namespace, name, value, currencyID=currency)


def _identifier(parent, namespace, name, identifier, scheme_attribute="schemeID"):
	if isinstance(identifier, Mapping) and identifier.get("value"):
		attributes = {scheme_attribute: identifier.get("scheme")} if identifier.get("scheme") else {}
		_child(parent, namespace, name, identifier["value"], **attributes)


def _legal_registration(parent, registration: Mapping):
	"""The legal registration, with the authority that issued it.

	The rules require the authority whenever the scheme is a trade licence,
	and it means different things per scheme: the issuing authority for a
	licence, the issuing country for a passport. So it is carried, not derived.
	"""
	attributes = {}
	if registration.get("scheme"):
		attributes["schemeAgencyID"] = registration["scheme"]
	if registration.get("authority"):
		attributes["schemeAgencyName"] = registration["authority"]
	_child(parent, CBC, "CompanyID", registration["value"], **attributes)


def _address(parent, address: Mapping):
	node = etree.SubElement(parent, _q(CAC, "PostalAddress"))
	for field, name in (
		("line1", "StreetName"),
		("line2", "AdditionalStreetName"),
		("city", "CityName"),
		("postal_code", "PostalZone"),
		("subdivision", "CountrySubentity"),
	):
		if _present(address.get(field)):
			_child(node, CBC, name, address[field])
	country = etree.SubElement(node, _q(CAC, "Country"))
	_child(country, CBC, "IdentificationCode", address.get("country"))


def _party(parent, wrapper: str, party: Mapping, *, identify: bool = False):
	"""Write one party into the document.

	`identify` writes the party identification element as well as the
	endpoint. The two are different things: the endpoint is where a document
	is delivered, the identification is who the party is. A beneficiary and
	a principal are named by the second, and the rules for both look for it
	specifically, so a document without it fails however complete it looks.
	"""
	holder = etree.SubElement(parent, _q(CAC, wrapper))
	node = etree.SubElement(holder, _q(CAC, "Party"))
	_identifier(node, CBC, "EndpointID", party.get("participant"))
	if identify:
		# Order matters here. The schema puts identification after the
		# endpoint and before the name.
		identification = party.get("participant") or {}
		if identification.get("value"):
			wrap = etree.SubElement(node, _q(CAC, "PartyIdentification"))
			_identifier(wrap, CBC, "ID", identification)
	if _present(party.get("trading_name")):
		name_node = etree.SubElement(node, _q(CAC, "PartyName"))
		_child(name_node, CBC, "Name", party["trading_name"])
	if isinstance(party.get("address"), Mapping):
		_address(node, party["address"])
	for key in ("tax_registration", "extra_tax_registration"):
		registration = party.get(key)
		if isinstance(registration, Mapping) and registration.get("value"):
			scheme = etree.SubElement(node, _q(CAC, "PartyTaxScheme"))
			_child(scheme, CBC, "CompanyID", registration["value"])
			tax_scheme = etree.SubElement(scheme, _q(CAC, "TaxScheme"))
			_child(tax_scheme, CBC, "ID", "VAT")
	legal = etree.SubElement(node, _q(CAC, "PartyLegalEntity"))
	_child(legal, CBC, "RegistrationName", party.get("legal_name"))
	registration = party.get("legal_registration")
	if isinstance(registration, Mapping) and registration.get("value"):
		_legal_registration(legal, registration)
	if isinstance(party.get("contact"), Mapping):
		contact = party["contact"]
		if any(_present(contact.get(f)) for f in ("name", "phone", "email")):
			node_contact = etree.SubElement(node, _q(CAC, "Contact"))
			for field, name in (("name", "Name"), ("phone", "Telephone"), ("email", "ElectronicMail")):
				if _present(contact.get(field)):
					_child(node_contact, CBC, name, contact[field])


def _adjustment(parent, row: Mapping, currency: str, *, is_charge: bool):
	node = etree.SubElement(parent, _q(CAC, "AllowanceCharge"))
	_child(node, CBC, "ChargeIndicator", is_charge)
	if _present(row.get("reason_code")):
		_child(node, CBC, "AllowanceChargeReasonCode", row["reason_code"])
	if _present(row.get("reason")):
		_child(node, CBC, "AllowanceChargeReason", row["reason"])
	if _present(row.get("percentage")):
		_child(node, CBC, "MultiplierFactorNumeric", row["percentage"])
	_amount(node, CBC, "Amount", row.get("amount"), currency)
	_amount(node, CBC, "BaseAmount", row.get("base_amount"), currency)
	category = etree.SubElement(node, _q(CAC, "TaxCategory"))
	_child(category, CBC, "ID", row.get("tax_category"))
	if _present(row.get("tax_rate")):
		_child(category, CBC, "Percent", row["tax_rate"])
	scheme = etree.SubElement(category, _q(CAC, "TaxScheme"))
	_child(scheme, CBC, "ID", "VAT")


def _tax_total(root, document: Mapping, currency: str):
	totals = document.get("totals") or {}
	node = etree.SubElement(root, _q(CAC, "TaxTotal"))
	_amount(node, CBC, "TaxAmount", totals.get("tax"), currency)
	_child(node, CBC, "TaxIncludedIndicator", False)
	for row in document.get("tax_breakdown") or []:
		subtotal = etree.SubElement(node, _q(CAC, "TaxSubtotal"))
		_amount(subtotal, CBC, "TaxableAmount", row.get("taxable_amount"), currency)
		_amount(subtotal, CBC, "TaxAmount", row.get("tax_amount"), currency)
		category = etree.SubElement(subtotal, _q(CAC, "TaxCategory"))
		_child(category, CBC, "ID", row.get("category"))
		if _present(row.get("rate")):
			_child(category, CBC, "Percent", row["rate"])
		if _present(row.get("reason_code")):
			_child(category, CBC, "TaxExemptionReasonCode", row["reason_code"])
		if _present(row.get("reason")):
			_child(category, CBC, "TaxExemptionReason", row["reason"])
		scheme = etree.SubElement(category, _q(CAC, "TaxScheme"))
		_child(scheme, CBC, "ID", "VAT")


def _monetary_total(root, totals: Mapping, currency: str):
	node = etree.SubElement(root, _q(CAC, "LegalMonetaryTotal"))
	for field, name in (
		("line_net", "LineExtensionAmount"),
		("tax_exclusive", "TaxExclusiveAmount"),
		("tax_inclusive", "TaxInclusiveAmount"),
		("allowances", "AllowanceTotalAmount"),
		("charges", "ChargeTotalAmount"),
		("prepaid", "PrepaidAmount"),
		("rounding", "PayableRoundingAmount"),
		("payable", "PayableAmount"),
	):
		_amount(node, CBC, name, totals.get(field), currency)


def _line(root, line: Mapping, currency: str, *, is_credit_note: bool):
	node = etree.SubElement(root, _q(CAC, "CreditNoteLine" if is_credit_note else "InvoiceLine"))
	_child(node, CBC, "ID", line.get("id"))
	quantity_element = "CreditedQuantity" if is_credit_note else "InvoicedQuantity"
	_child(node, CBC, quantity_element, line.get("quantity"), unitCode=line.get("uom_code"))
	_amount(node, CBC, "LineExtensionAmount", line.get("net_amount"), currency)
	for row in line.get("allowances") or []:
		_adjustment(node, row, currency, is_charge=False)
	for row in line.get("charges") or []:
		_adjustment(node, row, currency, is_charge=True)

	item = etree.SubElement(node, _q(CAC, "Item"))
	_child(item, CBC, "Description", line.get("note") or line.get("name"))
	_child(item, CBC, "Name", line.get("name"))
	if _present(line.get("item_code")):
		seller_id = etree.SubElement(item, _q(CAC, "SellersItemIdentification"))
		_child(seller_id, CBC, "ID", line["item_code"])
	# Goods are classified under one scheme and services under another, and the
	# two live in different elements, so each classification is routed by its
	# own scheme rather than all being written to one place.
	classifications = [c for c in (line.get("classifications") or []) if isinstance(c, Mapping)]
	service_codes = [c for c in classifications if c.get("scheme") == "SAC"]
	goods_codes = [c for c in classifications if c.get("scheme") != "SAC"]
	for service in service_codes:
		node_service = etree.SubElement(item, _q(CAC, "AdditionalItemIdentification"))
		_child(node_service, CBC, "ID", service["value"], schemeID="SAC")
	if _present(line.get("item_type")) or goods_codes:
		node_class = etree.SubElement(item, _q(CAC, "CommodityClassification"))
		if _present(line.get("item_type")):
			_child(node_class, CBC, "CommodityCode", ITEM_TYPE_CODES.get(line["item_type"], "B"))
		for goods in goods_codes:
			_child(node_class, CBC, "ItemClassificationCode", goods["value"], listID="HS")
	category = etree.SubElement(item, _q(CAC, "ClassifiedTaxCategory"))
	_child(category, CBC, "ID", line.get("tax_category"))
	if _present(line.get("tax_rate")):
		_child(category, CBC, "Percent", line["tax_rate"])
	scheme = etree.SubElement(category, _q(CAC, "TaxScheme"))
	_child(scheme, CBC, "ID", "VAT")

	price = etree.SubElement(node, _q(CAC, "Price"))
	_amount(price, CBC, "PriceAmount", line.get("net_price"), currency)
	base_quantity = line.get("base_quantity") if _present(line.get("base_quantity")) else Decimal(1)
	_child(price, CBC, "BaseQuantity", base_quantity, unitCode=line.get("uom_code"))
	# The rules want the price discount stated even when it is nothing, with
	# the gross price it came off, so both are always written.
	discount = etree.SubElement(price, _q(CAC, "AllowanceCharge"))
	_child(discount, CBC, "ChargeIndicator", False)
	price_discount = line.get("price_discount") if _present(line.get("price_discount")) else Decimal(0)
	gross = line.get("gross_price") if _present(line.get("gross_price")) else line.get("net_price")
	_amount(discount, CBC, "Amount", price_discount, currency)
	_amount(discount, CBC, "BaseAmount", gross, currency)

	extension = etree.SubElement(node, _q(CAC, "ItemPriceExtension"))
	net = line.get("net_amount")
	line_tax = _line_tax(line)
	_amount(extension, CBC, "Amount", (net or Decimal(0)) + line_tax, currency)
	if line.get("tax_category") != "E":
		tax_total = etree.SubElement(extension, _q(CAC, "TaxTotal"))
		_amount(tax_total, CBC, "TaxAmount", line_tax, currency)


def _line_tax(line: Mapping) -> Decimal:
	"""The tax on one line, as it was posted.

	Read rather than worked out. Three lines of 33.33 at five percent each
	round to 1.67 and state 5.01 on a document whose posted tax is 5.00, so
	multiplying here puts the parts and the whole at odds.

	Working it out is kept only for a document nothing extracted, which is
	a hand built one in a test. Anything this app produced carries the
	posted figure.
	"""
	posted = line.get("tax_amount")
	if isinstance(posted, Decimal):
		return posted

	net = line.get("net_amount")
	rate = line.get("tax_rate")
	if not isinstance(net, Decimal) or not isinstance(rate, Decimal):
		return Decimal(0)
	places = -net.as_tuple().exponent
	return (net * rate / Decimal(100)).quantize(Decimal(1).scaleb(-max(places, 2)))


def _exchange_rate(root, document: Mapping, currency: str):
	"""The rate to dirhams, which an invoice in another currency must carry.

	Three rules read this: one wants the rate to exist, one wants the source
	and target currencies to be the document's and dirhams, and one wants a
	dirham tax total alongside it.
	"""
	if currency == LOCAL_CURRENCY:
		return
	rate = ((document.get("exchange_rates") or {}).get("to_aed") or {}).get("rate")
	if not isinstance(rate, Decimal):
		return
	node = etree.SubElement(root, _q(CAC, "TaxExchangeRate"))
	_child(node, CBC, "SourceCurrencyCode", currency)
	_child(node, CBC, "TargetCurrencyCode", LOCAL_CURRENCY)
	_child(node, CBC, "CalculationRate", _rate_text(rate))


def _rate_text(rate: Decimal) -> str:
	"""A rate at no more than six decimal places, which ibr-002-ae requires.

	The model holds rates wider than that on purpose, as a safety net against
	a value arriving from floating point arithmetic. The document is where
	the published limit applies.
	"""
	trimmed = rate.quantize(Decimal(1).scaleb(-6)).normalize()
	text = canonical_decimal(trimmed)
	return text


def _tax_total_in_dirhams(root, document: Mapping, currency: str):
	"""The tax again, in dirhams, for an invoice that is not in them.

	A second tax total carrying nothing but the amount. It is the figure the
	tax authority reads, so it comes from what was posted rather than from
	multiplying the first one.
	"""
	if currency == LOCAL_CURRENCY:
		return
	amount = (document.get("totals") or {}).get("tax_in_aed")
	if not isinstance(amount, Decimal):
		return
	node = etree.SubElement(root, _q(CAC, "TaxTotal"))
	_amount(node, CBC, "TaxAmount", amount, LOCAL_CURRENCY)


def to_xml(document: Mapping) -> bytes:
	"""Write the canonical invoice as UBL XML.

	The element order follows the schema, not the published examples, because
	one of those examples fails its own schema on ordering.
	"""
	if not isinstance(document, Mapping):
		raise SerializerError("expected a canonical document")
	meta = document.get("document")
	if not isinstance(meta, Mapping):
		raise SerializerError("the document section is missing")
	type_code = meta.get("type_code")
	is_credit_note = type_code in CREDIT_NOTE_TYPES
	namespace = UBL_CREDIT_NOTE if is_credit_note else UBL_INVOICE
	currency = meta.get("currency")
	if not currency:
		raise SerializerError("the document currency is missing")

	root = etree.Element(
		_q(namespace, "CreditNote" if is_credit_note else "Invoice"),
		nsmap={None: namespace, "cac": CAC, "cbc": CBC},
	)
	context = document.get("context") or {}
	_child(root, CBC, "CustomizationID", context.get("customization_id"))
	_child(root, CBC, "ProfileID", context.get("profile_id"))
	_child(root, CBC, "ProfileExecutionID", scenario_string(document.get("scenario") or {}))
	_child(root, CBC, "ID", meta.get("number"))
	if _present(meta.get("uuid")):
		_child(root, CBC, "UUID", meta["uuid"])
	_child(root, CBC, "IssueDate", meta.get("issue_date"))
	if _present(meta.get("due_date")) and not is_credit_note:
		_child(root, CBC, "DueDate", meta["due_date"])
	_child(
		root,
		CBC,
		"CreditNoteTypeCode" if is_credit_note else "InvoiceTypeCode",
		type_code,
	)
	if _present(meta.get("note")):
		_child(root, CBC, "Note", meta["note"])
	if _present(meta.get("tax_point_date")):
		_child(root, CBC, "TaxPointDate", meta["tax_point_date"])
	_child(root, CBC, "DocumentCurrencyCode", currency)
	if _present(meta.get("tax_currency")):
		_child(root, CBC, "TaxCurrencyCode", meta["tax_currency"])
	if _present(meta.get("buyer_reference")):
		_child(root, CBC, "BuyerReference", meta["buyer_reference"])

	period = meta.get("period")
	if isinstance(period, Mapping):
		node_period = etree.SubElement(root, _q(CAC, "InvoicePeriod"))
		_child(node_period, CBC, "StartDate", period.get("start_date"))
		_child(node_period, CBC, "EndDate", period.get("end_date"))

	references = document.get("references") or {}
	# The credit reason sits here, before the references, and the rules read it
	# together with them: a volume discount credit note carries the reason and
	# no preceding reference, every other one carries both.
	if _present(references.get("credit_reason_code")):
		response = etree.SubElement(root, _q(CAC, "DiscrepancyResponse"))
		_child(response, CBC, "ResponseCode", references["credit_reason_code"])
		if _present(references.get("credit_reason")):
			_child(response, CBC, "Description", references["credit_reason"])
	if _present(references.get("purchase_order")):
		order = etree.SubElement(root, _q(CAC, "OrderReference"))
		_child(order, CBC, "ID", references["purchase_order"])
	for preceding in references.get("preceding") or []:
		billing = etree.SubElement(root, _q(CAC, "BillingReference"))
		reference = etree.SubElement(billing, _q(CAC, "InvoiceDocumentReference"))
		_child(reference, CBC, "ID", preceding.get("number"))
		if _present(preceding.get("issue_date")):
			_child(reference, CBC, "IssueDate", preceding["issue_date"])
	if _present(references.get("contract")):
		contract = etree.SubElement(root, _q(CAC, "ContractDocumentReference"))
		_child(contract, CBC, "ID", references["contract"])

	inclusive_aed = (document.get("totals") or {}).get("tax_inclusive_aed")
	if isinstance(inclusive_aed, Decimal):
		# The dirham total including tax, written as words rather than as an
		# amount. That is how the published example does it and ibr-175-ae
		# looks for the description rather than a value.
		aed = etree.SubElement(root, _q(CAC, "AdditionalDocumentReference"))
		_child(aed, CBC, "ID", LOCAL_CURRENCY)
		_child(aed, CBC, "DocumentTypeCode", "aedtotal-incl-vat")
		_child(aed, CBC, "DocumentDescription", f"{LOCAL_CURRENCY} {canonical_decimal(inclusive_aed)}")

	parties = document.get("parties") or {}
	_party(root, "AccountingSupplierParty", parties.get("seller") or {})
	_party(root, "AccountingCustomerParty", parties.get("buyer") or {})
	# The order is the schema's, not ours. A beneficiary sits in the buyer
	# customer element and a principal in the seller supplier element, which
	# is where their rules look for them, and the first comes before the
	# second.
	for key, wrapper in (("beneficiary", "BuyerCustomerParty"), ("principal", "SellerSupplierParty")):
		if isinstance(parties.get(key), Mapping):
			_party(root, wrapper, parties[key], identify=True)

	delivery = document.get("delivery") or {}
	if delivery:
		node = etree.SubElement(root, _q(CAC, "Delivery"))
		if _present(delivery.get("date")):
			_child(node, CBC, "ActualDeliveryDate", delivery["date"])
		if isinstance(delivery.get("address"), Mapping):
			location = etree.SubElement(node, _q(CAC, "DeliveryLocation"))
			address = etree.SubElement(location, _q(CAC, "Address"))
			for field, name in (
				("line1", "StreetName"),
				("city", "CityName"),
				("subdivision", "CountrySubentity"),
			):
				if _present(delivery["address"].get(field)):
					_child(address, CBC, name, delivery["address"][field])
			country = etree.SubElement(address, _q(CAC, "Country"))
			_child(country, CBC, "IdentificationCode", delivery["address"].get("country"))

	payment = document.get("payment") or {}
	if _present(payment.get("means_code")):
		node = etree.SubElement(root, _q(CAC, "PaymentMeans"))
		_child(node, CBC, "PaymentMeansCode", payment["means_code"])
		account = payment.get("account")
		if isinstance(account, Mapping) and account.get("identifier"):
			payee = etree.SubElement(node, _q(CAC, "PayeeFinancialAccount"))
			_child(payee, CBC, "ID", account["identifier"])
			if _present(account.get("name")):
				_child(payee, CBC, "Name", account["name"])
	if _present(payment.get("terms")):
		terms = etree.SubElement(root, _q(CAC, "PaymentTerms"))
		_child(terms, CBC, "Note", payment["terms"])

	for row in document.get("allowances") or []:
		_adjustment(root, row, currency, is_charge=False)
	for row in document.get("charges") or []:
		_adjustment(root, row, currency, is_charge=True)

	_exchange_rate(root, document, currency)
	_tax_total(root, document, currency)
	_tax_total_in_dirhams(root, document, currency)
	_monetary_total(root, document.get("totals") or {}, currency)
	for line in document.get("lines") or []:
		_line(root, line, currency, is_credit_note=is_credit_note)

	return etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
