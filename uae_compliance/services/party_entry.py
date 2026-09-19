"""Creating a customer or supplier together with what we know about its tax.

One request, so one transaction. The party, the address and contact ERPNext
makes from it, and the e-invoicing profile all arrive together or none of
them do. Creating the party and then asking separately for the profile would
leave a party with no profile behind whenever the second call failed.

Incomplete is allowed here. Most of what the rules want is not known when
somebody is typing a new customer in, and refusing to create the customer
until it is would make the app something to work around.
"""

from __future__ import annotations

import frappe
from frappe import _

PROFILE_DOCTYPE = "UAE Peppol Party Profile"
ALLOWED_PARTIES = ("Customer", "Supplier")

# What the dialog may set on the profile. Anything else it sends is dropped,
# because evidence fields are not a person's to fill in.
PROFILE_FIELDS = (
	"establishment_country",
	"party_context",
	"vat_state",
	"vat_number",
	"extra_vat_number",
	"peppol_state",
	"endpoint_scheme",
	"endpoint_value",
	"legal_scheme",
	"legal_value",
	"legal_authority",
)


@frappe.whitelist()
def create_party(doctype: str, values: str) -> dict:
	"""Make the party and its profile in one go.

	`values` is what the quick entry dialog collected. The compliance fields
	are taken out and the rest is handed to ERPNext untouched, so its own
	address and contact handling still does the work.
	"""
	if doctype not in ALLOWED_PARTIES:
		frappe.throw(_("A profile can only be made for a customer or a supplier."))

	supplied = frappe.parse_json(values) or {}
	profile_values = {field: supplied.pop(field, None) for field in PROFILE_FIELDS}

	# The country answers two questions at once when a party is first typed
	# in: where its post goes, and where it is established. They start the
	# same and are separate from then on, because a party can move its
	# registered seat without moving its post room.
	if not profile_values.get("establishment_country"):
		profile_values["establishment_country"] = supplied.get("country")

	party = frappe.new_doc(doctype)
	party.update(supplied)
	party.insert()

	profile = _profile_for(doctype, party.name, profile_values)
	return {"name": party.name, "profile": profile}


def _profile_for(doctype: str, party: str, values: dict) -> str | None:
	"""Record what is known, if anything is.

	A dialog where nobody touched the tax section makes no profile. An empty
	profile is not evidence of anything and it would only sit there looking
	answered.
	"""
	if not any(value for value in values.values()):
		return None

	profile = frappe.new_doc(PROFILE_DOCTYPE)
	profile.party_doctype = doctype
	profile.party = party
	for field, value in values.items():
		if value:
			profile.set(field, value)
	profile.insert()
	return profile.name


@frappe.whitelist()
def set_up_company(company: str, label: str | None = None) -> dict:
	"""Point a company at a seller profile and put it in Preparation.

	Preparation on purpose. It collects and checks without sending anything,
	so a company can be set up and looked at long before there is a provider
	to send through. Going Live is a separate decision with a date on it.
	"""
	if not frappe.has_permission("Company", "write", company):
		raise frappe.PermissionError

	existing = frappe.db.get_value(
		"UAE Peppol Seller Company",
		{"company": company, "parenttype": "UAE Peppol Seller Profile"},
		["parent", "mode"],
		as_dict=True,
	)
	if existing:
		return {"profile": existing.parent, "mode": existing.mode, "created": False}

	details = frappe.db.get_value("Company", company, ["company_name", "tax_id"], as_dict=True)
	profile = frappe.new_doc("UAE Peppol Seller Profile")
	profile.label = label or details.company_name
	if details.tax_id:
		profile.vat_state = "Registered"
		profile.vat_number = details.tax_id
	profile.append("companies", {"company": company, "mode": "Preparation", "review_required": 1})
	profile.insert()
	return {"profile": profile.name, "mode": "Preparation", "created": True}


@frappe.whitelist()
def set_item_type(items: str, item_type: str) -> int:
	"""Say whether these items are goods or services, on the items themselves.

	This is an explicit write to master data and nothing else does it. An
	invoice saving must never change what an item means everywhere else.
	"""
	if item_type not in ("Goods", "Services", "Both"):
		frappe.throw(_("An item is goods, services, or both."))

	names = frappe.parse_json(items) or []
	changed = 0
	for name in names[:100]:
		if not frappe.has_permission("Item", "write", name):
			continue
		frappe.db.set_value("Item", name, "uae_peppol_item_type", item_type)
		changed += 1
	return changed
