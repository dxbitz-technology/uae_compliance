"""What happens when the app is installed or migrated.

The one rule here: a fresh site starts switched off and nothing about
installing the app changes how an existing site behaves. Everything this does
is safe to run again, because a migration runs it every time.
"""

import frappe

from uae_compliance.domain.canonical import CANONICAL_VERSION
from uae_compliance.validation.artifacts import PINT_VERSION
from uae_compliance.validation.serializer import SERIALIZER_VERSION

RULESET_ID = "PINT AE Billing"


def after_install():
	record_installed_rules()


def after_migrate():
	record_installed_rules()


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
