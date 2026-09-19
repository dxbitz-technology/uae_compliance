"""The master records an invoice depends on, read once and frozen.

What is read here is what the invoice meant on the day it was issued. The
address chosen on the invoice is the one that travels with it. Editing a
party's primary address afterwards does not reach back into a document that
has already gone.

Nothing in this file writes. A missing master is a finding, never a guess.
The one exception is a company nobody configured, which reads as Off so the
app stays invisible on a site that never asked for it.

Every record this touches is noted with the time it last changed. That list
becomes the master fingerprint, which is how a draft learns that something it
depends on has moved underneath it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import frappe

from uae_compliance.domain.findings import Finding, Severity, SourceRef, Stage
from uae_compliance.domain.scope import Mode, mode_of

CODE_NO_SELLER = "MASTER-0001"
CODE_NO_SELLER_ADDRESS = "MASTER-0002"
CODE_NO_BUYER_ADDRESS = "MASTER-0003"
CODE_NO_BUYER_PROFILE = "MASTER-0004"
CODE_NO_COUNTRY = "MASTER-0005"
CODE_NO_SELLER_IDENTITY = "MASTER-0006"
CODE_NO_BUYER_ENDPOINT = "MASTER-0007"
CODE_NO_SELLER_TAX_NUMBER = "MASTER-0008"

SELLER_DOCTYPE = "UAE Peppol Seller Profile"
BINDING_DOCTYPE = "UAE Peppol Seller Company"
PARTY_PROFILE_DOCTYPE = "UAE Peppol Party Profile"


@dataclass
class Resolution:
	"""What the masters said, and what was missing when they said it."""

	mode: Mode = Mode.OFF
	seller_profile: str | None = None
	effective_from: str | None = None
	review_required: bool = True
	seller: dict = field(default_factory=dict)
	buyer: dict = field(default_factory=dict)
	buyer_profile: str | None = None
	delivery: dict = field(default_factory=dict)
	findings: list[Finding] = field(default_factory=list)
	revisions: dict[str, str] = field(default_factory=dict)
	# What has already been asked during this one extraction. An invoice
	# with five hundred lines of the same item should ask about that item
	# once, not five hundred times.
	looked_up: dict = field(default_factory=dict)

	def note(self, finding: Finding):
		self.findings.append(finding)

	def remember(self, key, build):
		"""Answer from what we already asked, or ask once and keep it.

		Only for master data, which cannot change while one extraction runs.
		Findings are deliberately not cached: the same missing unit on three
		lines is three things to fix, each pointing at its own row.
		"""
		if key not in self.looked_up:
			self.looked_up[key] = build()
		return self.looked_up[key]

	def seen(self, doctype: str, name: str | None, modified=None):
		"""Record that this document was read, and when it last changed.

		Asking twice about the same record is one query too many. On an
		invoice with a thousand lines of the same item that was a thousand
		queries for one answer.
		"""
		if not name:
			return
		key = f"{doctype}:{name}"
		if key in self.revisions:
			return
		if modified is None:
			modified = self.remember(
				("modified", doctype, name),
				lambda: frappe.db.get_value(doctype, name, "modified"),
			)
		self.revisions[key] = str(modified or "")


def resolve(invoice) -> Resolution:
	"""Read every master this invoice depends on.

	`invoice` is a Sales Invoice document. It is read, never changed.
	"""
	out = Resolution()
	source = SourceRef(doctype="Sales Invoice", name=invoice.name)

	binding = _seller_binding(invoice.company)
	if not binding:
		# No seller owns this company, so the app has nothing to say about it.
		# This is not a gap to report. It is the app staying out of the way.
		return out

	out.seller_profile = binding.parent
	out.mode = mode_of(binding.mode)
	out.effective_from = str(binding.effective_from or "") or None
	out.review_required = bool(binding.review_required)
	out.seen(SELLER_DOCTYPE, binding.parent)

	out.seller = _seller_party(invoice, binding, out, source)
	out.buyer = _buyer_party(invoice, out, source)
	out.delivery = _delivery(invoice, out)
	return out


def _seller_binding(company: str):
	"""The row that binds this company to a seller, if one does.

	A company belongs to one binding, which the record itself enforces, so
	the first row found is the only row.
	"""
	rows = frappe.get_all(
		BINDING_DOCTYPE,
		filters={"company": company, "parenttype": SELLER_DOCTYPE},
		fields=["parent", "mode", "effective_from", "review_required", "default_address"],
		limit=1,
	)
	return frappe._dict(rows[0]) if rows else None


def _seller_party(invoice, binding, out: Resolution, source: SourceRef) -> dict:
	profile = frappe.get_doc(SELLER_DOCTYPE, binding.parent)
	company = frappe.get_doc("Company", invoice.company)
	out.seen("Company", company.name, company.modified)

	# The invoice's own choice wins over the seller's default. Spec 4.1.
	address_name = invoice.company_address or binding.default_address
	address = _address(address_name, out)
	if not address:
		out.note(
			Finding(
				code=CODE_NO_SELLER_ADDRESS,
				severity=Severity.ERROR,
				stage=Stage.MASTERS,
				message="The selling company has no address on this invoice.",
				path="parties.seller.address",
				source=source,
				repair="Pick a company address on the invoice, or set a default one on the seller profile.",
			)
		)

	party = {
		"legal_name": company.company_name,
		"country": (address or {}).get("country"),
		"address": address,
	}
	if profile.participant_value:
		party["participant"] = {
			"scheme": profile.participant_scheme,
			"value": profile.participant_value,
		}
	else:
		out.note(
			Finding(
				code=CODE_NO_SELLER_IDENTITY,
				severity=Severity.ERROR,
				stage=Stage.MASTERS,
				message="The seller has no network identity yet.",
				path="parties.seller.participant",
				source=source,
				repair="Add the seller's participant identifier to its profile.",
			)
		)

	# The company's own registration is authoritative where it is filled in.
	# The profile carries it only until the native field does.
	tax_number = company.tax_id or profile.vat_number
	if tax_number:
		party["tax_registration"] = {"scheme": "VAT", "value": tax_number}
	elif profile.vat_state == "Registered":
		out.note(
			Finding(
				code=CODE_NO_SELLER_TAX_NUMBER,
				severity=Severity.ERROR,
				stage=Stage.MASTERS,
				message="The seller is marked registered but carries no tax number.",
				path="parties.seller.tax_registration",
				source=source,
				repair="Add the tax registration number to the company or the seller profile.",
			)
		)

	if profile.legal_value:
		party["legal_registration"] = {
			"scheme": profile.legal_scheme,
			"value": profile.legal_value,
			"authority": profile.legal_authority or None,
		}
	return party


def _buyer_party(invoice, out: Resolution, source: SourceRef) -> dict:
	customer = frappe.get_doc("Customer", invoice.customer)
	out.seen("Customer", customer.name, customer.modified)

	profile_name = frappe.db.get_value(
		PARTY_PROFILE_DOCTYPE, {"party_doctype": "Customer", "party": invoice.customer}, "name"
	)
	profile = frappe.get_doc(PARTY_PROFILE_DOCTYPE, profile_name) if profile_name else None
	if profile:
		out.buyer_profile = profile.name
		out.seen(PARTY_PROFILE_DOCTYPE, profile.name, profile.modified)
	else:
		out.note(
			Finding(
				code=CODE_NO_BUYER_PROFILE,
				severity=Severity.ERROR,
				stage=Stage.MASTERS,
				message="This customer has no e-invoicing profile.",
				path="parties.buyer",
				source=source,
				repair="Create a party profile for the customer.",
			)
		)

	# No fallback to whichever address is primary today. Spec 5.2.
	address = _address(invoice.customer_address, out)
	if not address:
		out.note(
			Finding(
				code=CODE_NO_BUYER_ADDRESS,
				severity=Severity.ERROR,
				stage=Stage.MASTERS,
				message="The customer has no billing address on this invoice.",
				path="parties.buyer.address",
				source=source,
				repair="Pick a billing address on the invoice.",
			)
		)

	party = {
		"legal_name": customer.customer_name,
		"address": address,
		"contact": _contact(invoice),
	}

	# The country a party is established in and the country its post arrives
	# in are different facts. The profile holds the first, the address the
	# second, and neither overwrites the other.
	established = profile.establishment_country if profile else None
	party["country"] = _country_code(established, out) or (address or {}).get("country")
	if not party["country"]:
		out.note(
			Finding(
				code=CODE_NO_COUNTRY,
				severity=Severity.ERROR,
				stage=Stage.MASTERS,
				message="The customer's country is not known.",
				path="parties.buyer.country",
				source=source,
				repair="Set the establishment country on the party profile, or a country on the address.",
			)
		)

	if profile:
		if profile.endpoint_value:
			party["participant"] = {
				"scheme": profile.endpoint_scheme,
				"value": profile.endpoint_value,
			}
		else:
			out.note(
				Finding(
					code=CODE_NO_BUYER_ENDPOINT,
					severity=Severity.ERROR,
					stage=Stage.MASTERS,
					message="The customer has no network address.",
					path="parties.buyer.participant",
					source=source,
					repair="Add the customer's endpoint to its profile, or check the directory.",
				)
			)
		# A foreign party may hold a UAE registration as well as its own.
		# Both are kept. See decision D016.
		number = customer.tax_id or profile.vat_number
		if number:
			party["tax_registration"] = {"scheme": "VAT", "value": number}
		if profile.extra_vat_number:
			party["extra_tax_registration"] = {"scheme": "VAT", "value": profile.extra_vat_number}
		if profile.legal_value:
			party["legal_registration"] = {
				"scheme": profile.legal_scheme,
				"value": profile.legal_value,
				"authority": profile.legal_authority or None,
			}
	elif customer.tax_id:
		party["tax_registration"] = {"scheme": "VAT", "value": customer.tax_id}

	return party


def _delivery(invoice, out: Resolution) -> dict:
	"""Where the goods went, when the invoice says.

	Dispatch and shipping are different things and ERPNext holds both. The
	one that belongs on the document is where the customer received it.
	"""
	address = _address(invoice.shipping_address_name, out)
	if not address:
		return {}
	return {"address": address, "party_name": invoice.customer_name or None}


def _address(name: str | None, out: Resolution) -> dict | None:
	if not name:
		return None
	doc = frappe.get_doc("Address", name)
	out.seen("Address", doc.name, doc.modified)
	return {
		"line1": doc.address_line1 or None,
		"line2": doc.address_line2 or None,
		"city": doc.city or None,
		"subdivision": _subdivision(doc),
		"postal_code": doc.pincode or None,
		"country": _country_code(doc.country, out),
	}


def _subdivision(address) -> str | None:
	"""The country subdivision, which ibr-143-ae and ibr-144-ae both require.

	On a UAE site the emirate is its own field, put there by ERPNext's own
	regional setup, and the general state field is usually left empty. So the
	emirate is asked first and the state answers for everywhere else.
	"""
	return address.get("emirate") or address.state or None


def _contact(invoice) -> dict:
	contact = {
		"name": invoice.contact_display or None,
		"email": invoice.contact_email or None,
		"phone": invoice.contact_mobile or None,
	}
	return contact if any(contact.values()) else {}


def _country_code(country_name: str | None, out: Resolution) -> str | None:
	"""Turn a country name into the two letter code the rules ask for."""
	if not country_name:
		return None
	code = frappe.db.get_value("Country", country_name, "code")
	out.seen("Country", country_name)
	return code.upper() if code else None
