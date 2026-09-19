"""What happens when the app is installed or migrated.

The one rule here: a fresh site starts switched off and nothing about
installing the app changes how an existing site behaves. Everything this does
is safe to run again, because a migration runs it every time.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from uae_compliance.domain.canonical import CANONICAL_VERSION
from uae_compliance.validation.artifacts import PINT_VERSION
from uae_compliance.validation.serializer import SERIALIZER_VERSION

RULESET_ID = "PINT AE Billing"

# The one thing the official rules need that no native field carries. Whether
# a line is goods or services decides which classification scheme it is
# published under, and it cannot be read from whether the item is stocked: a
# service can be stocked and a good can be non-stock. Optional on both, so a
# master still saves without it. Spec 4.3.
ITEM_TYPE_FIELDS = {
	"Item": [
		{
			"fieldname": "uae_peppol_item_type",
			"label": "UAE e-Invoicing Type",
			"fieldtype": "Select",
			"options": "\nGoods\nServices\nBoth",
			"insert_after": "customs_tariff_number",
			"description": "Used when this item appears on an e-invoice. Leave blank to take the item group's setting.",
		}
	],
	"Item Group": [
		{
			"fieldname": "uae_peppol_item_type",
			"label": "UAE e-Invoicing Type",
			"fieldtype": "Select",
			"options": "\nGoods\nServices\nBoth",
			"insert_after": "item_group_name",
			"description": "Suggested for items in this group. An item's own setting wins.",
		}
	],
}


def after_install():
	record_installed_rules()
	add_item_type_field()
	add_unique_constraints()


def after_migrate():
	record_installed_rules()
	add_item_type_field()
	add_unique_constraints()


def record_installed_rules():
	"""Write down which rules this release carries.

	Read only in the form, because the rules are pinned in the repository. A
	site cannot be pointed at a different version by editing a field.
	"""
	settings = frappe.get_single("UAE Peppol Settings")
	settings.ruleset_id = RULESET_ID
	settings.ruleset_version = PINT_VERSION
	settings.canonical_version = str(CANONICAL_VERSION)
	settings.serializer_version = str(SERIALIZER_VERSION)
	settings.flags.ignore_permissions = True
	settings.save()


def add_item_type_field():
	"""Add the one optional field this app puts on a native master.

	Safe to run again. The framework updates the field in place rather than
	adding a second one, and it leaves any other app's fields alone.
	"""
	create_custom_fields(ITEM_TYPE_FIELDS, ignore_validate=True)


def add_unique_constraints():
	"""Uniqueness the field schema cannot state, because it spans two fields.

	The landing dedup reads before it writes, and two collectors racing the
	same page can both pass that read. The database is the guard that cannot
	race. Safe to run again: the framework checks for the constraint first.
	"""
	frappe.db.add_unique("UAE Peppol Inbound", ["connection", "document_uuid"])


def before_tests():
	"""Make a bare site usable before the tests run.

	A site created from nothing has no company and none of the records ERPNext
	normally lays down through its setup wizard, so creating a company fails on
	a missing warehouse type. Tests that quietly depend on a developer's
	existing site are not testing anything, so they set the site up themselves.

	Safe to run again. ERPNext's own installer skips what is already there.
	"""
	from erpnext.setup.setup_wizard.operations.install_fixtures import install

	install(country="United Arab Emirates")
	frappe.db.commit()
