"""The canonical invoice, version 1.

This is the one description of what an invoice looks like once it has left
ERPNext and before it becomes XML or a provider's own format. Everything
downstream reads this and nothing reads the source document again.

Two notes on numbers. The scales here are a safety net, not the rounding
rule. They are wide enough to hold what a real invoice carries and narrow
enough to catch a value that arrived from floating point arithmetic with
seventeen decimal places. What each currency actually rounds to is a money
decision and belongs to the money rules, which know the currency.

Scenario flags are named booleans. The official eight character transaction
string is built from them at serialization and never stored here, so nothing
in the model depends on the order of those positions.
"""

from __future__ import annotations

from uae_compliance.domain.schema import Field, Kind, Schema

CANONICAL_VERSION = 1
CANONICAL_NAME = "uae-peppol-invoice"

# Safety net scales. The money rules own real rounding.
AMOUNT_SCALE = 4
PRICE_SCALE = 6
QUANTITY_SCALE = 6
PERCENT_SCALE = 6
EXCHANGE_RATE_SCALE = 9

# Verified against the pinned publication. See decision D015. These are the
# billing family. Self-billing adds 389 and 261 at P12, on a separate
# specialisation that is not pinned here.
DOCUMENT_TYPES = ("380", "480", "381", "81")
TAX_CATEGORIES = ("S", "E", "O", "AE", "Z", "N")
ENVIRONMENTS = ("Simulation", "Sandbox", "Production")
ITEM_TYPES = ("Goods", "Services", "Both")

# The eight official transaction positions, in the published order. The
# serializer turns these into the positional string; nothing else may.
SCENARIO_FLAGS = (
	"free_zone",
	"deemed_supply",
	"margin_scheme",
	"summary",
	"continuous_supply",
	"agent_billing",
	"ecommerce",
	"export",
)


def text(required=False, **kw):
	return Field(Kind.TEXT, required=required, **kw)


def code(allowed, required=False, **kw):
	return Field(Kind.CODE, required=required, allowed=allowed, **kw)


def amount(required=False, **kw):
	return Field(Kind.DECIMAL, required=required, scale=AMOUNT_SCALE, **kw)


def date(required=False, **kw):
	return Field(Kind.DATE, required=required, **kw)


def obj(fields, required=False, **kw):
	return Field(Kind.OBJECT, required=required, fields=fields, **kw)


def array(of, required=False):
	return Field(Kind.ARRAY, required=required, of=of)


PROVENANCE = obj(
	required=True,
	fields={
		"schema_version": text(required=True),
		"extraction_version": text(required=True),
		# Moves on every run, so it is left out of the business hash.
		"extracted_at": Field(Kind.TIMESTAMP, required=True),
		"source_doctype": text(required=True),
		"source_name": text(required=True),
		"company": text(required=True),
		"source_fingerprint": text(required=True),
		"master_fingerprint": text(required=True),
	},
)

CONTEXT = obj(
	required=True,
	fields={
		"jurisdiction": Field(Kind.COUNTRY, required=True),
		"policy_revision": text(required=True),
		"in_scope": Field(Kind.BOOLEAN, required=True),
		"scope_reason": text(),
		"environment": code(ENVIRONMENTS, required=True),
		"standards_version": text(required=True),
		"customization_id": text(required=True),
		"profile_id": text(required=True),
	},
)

ADDRESS = obj(
	fields={
		"line1": text(),
		"line2": text(),
		"city": text(),
		"subdivision": text(),
		"postal_code": text(),
		"country": Field(Kind.COUNTRY, required=True),
	},
)

CONTACT = obj(fields={"name": text(), "email": text(), "phone": text()})

PARTY = obj(
	fields={
		"legal_name": text(required=True),
		"trading_name": text(),
		# The network address. A buyer that is not onboarded has none.
		"participant": Field(Kind.IDENTIFIER),
		"tax_registration": Field(Kind.IDENTIFIER),
		# A foreign party may hold a UAE registration as well as its own.
		# See decision D016. Both are kept; neither overwrites the other.
		"extra_tax_registration": Field(Kind.IDENTIFIER),
		"legal_registration": Field(Kind.IDENTIFIER),
		"country": Field(Kind.COUNTRY, required=True),
		"address": ADDRESS,
		"contact": CONTACT,
	},
)

PARTIES = obj(
	required=True,
	fields={
		"seller": obj(PARTY.fields, required=True),
		"buyer": obj(PARTY.fields, required=True),
		# Named when an agent bills on someone's behalf.
		"principal": obj(PARTY.fields),
		# Required by the free zone rule, which needs the identity and not
		# only the name.
		"beneficiary": obj(PARTY.fields),
	},
)

DOCUMENT = obj(
	required=True,
	fields={
		"number": text(required=True),
		# Required by the rules, and distinct from the legal number: it stays
		# the same for this document wherever it travels.
		"uuid": text(required=True),
		"type_code": code(DOCUMENT_TYPES, required=True),
		"issue_date": date(required=True),
		"due_date": date(may_be_not_applicable=True),
		"tax_point_date": date(may_be_not_applicable=True),
		"period": obj(fields={"start_date": date(required=True), "end_date": date(required=True)}),
		"currency": Field(Kind.CURRENCY, required=True),
		"tax_currency": Field(Kind.CURRENCY, may_be_not_applicable=True),
		"buyer_reference": text(),
		"note": text(),
	},
)

ADJUSTMENT = obj(
	fields={
		"amount": amount(required=True),
		"base_amount": amount(),
		"percentage": Field(Kind.DECIMAL, scale=PERCENT_SCALE),
		"reason": text(),
		"reason_code": text(),
		# An adjustment carries its own tax treatment, because a discount and
		# the line it reduces do not always share one.
		"tax_category": code(TAX_CATEGORIES, required=True),
		"tax_rate": Field(Kind.DECIMAL, required=True, scale=PERCENT_SCALE),
	},
)

LINE = obj(
	fields={
		"id": text(required=True),
		# The row this came from, so a finding can point back at it.
		"source_row": text(required=True),
		"item_code": text(),
		"name": text(required=True),
		"item_type": code(ITEM_TYPES),
		# More than one, because goods are classified under one scheme and
		# services under another, and something that is both needs both.
		"classifications": array(Field(Kind.IDENTIFIER)),
		"quantity": Field(Kind.DECIMAL, required=True, scale=QUANTITY_SCALE),
		"uom_code": text(required=True),
		"base_quantity": Field(Kind.DECIMAL, scale=QUANTITY_SCALE, signed=False),
		"gross_price": Field(Kind.DECIMAL, scale=PRICE_SCALE),
		"net_price": Field(Kind.DECIMAL, required=True, scale=PRICE_SCALE),
		# Already taken off the net price. It is carried for the record and
		# must not be deducted a second time as an allowance. It is a per unit
		# price, so it carries price precision: the official rule requires net
		# price to equal gross price minus this exactly, and a narrower scale
		# here would make prices the model allows impossible to reconcile.
		"price_discount": Field(Kind.DECIMAL, scale=PRICE_SCALE),
		"allowances": array(ADJUSTMENT),
		"charges": array(ADJUSTMENT),
		"net_amount": amount(required=True),
		"tax_category": code(TAX_CATEGORIES, required=True),
		"tax_rate": Field(Kind.DECIMAL, required=True, scale=PERCENT_SCALE),
		# The tax ERPNext posted against this line. Carried rather than
		# worked out from the rate, because three lines of 33.33 at five
		# percent each round to 1.67 and state 5.01 against a posted 5.00.
		"tax_amount": amount(),
		"tax_reason": text(),
		"tax_reason_code": text(),
		"note": text(),
	},
)

TAX_BREAKDOWN_ROW = obj(
	fields={
		"category": code(TAX_CATEGORIES, required=True),
		"rate": Field(Kind.DECIMAL, required=True, scale=PERCENT_SCALE),
		"reason": text(),
		"reason_code": text(),
		"taxable_amount": amount(required=True),
		"tax_amount": amount(required=True),
		# The same tax expressed in dirhams, when the invoice is in another
		# currency and the rules ask for it.
		"tax_amount_aed": amount(),
	},
)

TOTALS = obj(
	required=True,
	fields={
		"line_net": amount(required=True),
		"allowances": amount(required=True),
		"charges": amount(required=True),
		"tax_exclusive": amount(required=True),
		"tax": amount(required=True),
		"tax_inclusive": amount(required=True),
		# Frozen at issue. A payment made afterwards never changes it.
		"prepaid": amount(),
		"rounding": amount(),
		"payable": amount(required=True),
		"tax_in_aed": amount(),
		# The rules ask for this one as text on the document, so it is
		# carried rather than worked out at serialization.
		"tax_inclusive_aed": amount(),
	},
)

REFERENCES = obj(
	fields={
		# More than one, because a credit note can answer several invoices.
		"preceding": array(
			obj(fields={"number": text(required=True), "issue_date": date()}),
		),
		"credit_reason": text(),
		"credit_reason_code": text(),
		"contract": text(),
		"purchase_order": text(),
		"supporting": array(
			obj(fields={"id": text(required=True), "description": text(), "url": text()}),
		),
	},
)

PAYMENT = obj(
	fields={
		"means_code": text(),
		"terms": text(),
		"account": obj(fields={"identifier": text(), "name": text(), "bank": text()}),
	},
)

DELIVERY = obj(
	fields={
		"date": date(),
		"party_name": text(),
		"address": ADDRESS,
	},
)

RATE = obj(
	fields={
		"from_currency": Field(Kind.CURRENCY, required=True),
		"to_currency": Field(Kind.CURRENCY, required=True),
		"rate": Field(Kind.DECIMAL, required=True, scale=EXCHANGE_RATE_SCALE, signed=False),
		"date": date(required=True),
		# Where the rate came from. A missing source is a finding, never a
		# reason to invent one.
		"source": text(required=True),
	},
)

EXCHANGE_RATES = obj(
	fields={
		"to_company": RATE,
		"to_aed": RATE,
	},
)

SCENARIO = obj(
	required=True,
	# Every flag is required, so an extractor has to state each one rather
	# than leaving a scenario silently off.
	fields={name: Field(Kind.BOOLEAN, required=True) for name in SCENARIO_FLAGS},
)

INVOICE = Schema(
	name=CANONICAL_NAME,
	version=CANONICAL_VERSION,
	fields={
		"provenance": PROVENANCE,
		"context": CONTEXT,
		"document": DOCUMENT,
		"parties": PARTIES,
		"lines": array(LINE, required=True),
		"tax_breakdown": array(TAX_BREAKDOWN_ROW, required=True),
		"allowances": array(ADJUSTMENT),
		"charges": array(ADJUSTMENT),
		"totals": TOTALS,
		"references": REFERENCES,
		"payment": PAYMENT,
		"delivery": DELIVERY,
		"scenario": SCENARIO,
		"exchange_rates": EXCHANGE_RATES,
	},
)

# Left out of the business hash, because they move without the invoice
# changing. Each one is required in the model above, so the exclusion cannot
# quietly stop applying when a field happens to be absent.
VOLATILE_PATHS = ("provenance.extracted_at",)
