"""Stopping a copy of a site from sending real invoices.

Restoring a production backup onto a test server gives you a database that
believes everything it believed before, including that it may transmit. That
is how a staging box sends live invoices to real customers.

So the permission to send in Production does not live in the database. It
lives in the site's own configuration file, and it names the site it was
granted for.

That file travels further than it looks. A database only restore leaves it
behind, but a backup taken with the configuration carries it, key and all,
and restoring that puts the permission on the copy. So the guard is not the
key being absent. It is what the key says, and where it is read.

Restored under any other site name, the key names a site this is not, and
Production sending is refused. Restored under its own name on another
machine the key matches and the second guard catches it: the database
records which machine this site last sent from, and when that changes
underneath us outbound work is paused and says why. A manager lifts that
deliberately after a genuine move.

Neither guard covers a restore under the same name on the same machine,
because that is not a copy. That is the site.
"""

from __future__ import annotations

import hashlib
import socket

import frappe
from frappe import _

SETTINGS = "UAE Peppol Settings"

# The key a deployment sets in site_config.json to allow production sending.
# Its value is the site name, so the key cannot be copied between sites and
# keep working.
CONFIG_KEY = "uae_peppol_production_send"

# Where the note of the last sending machine is kept. Deliberately in the
# database, because it is the thing that travels with a restore and so is
# what reveals one.
HOST_KEY = "uae_peppol_last_host"


def host_fingerprint() -> str:
	"""A short, stable name for the machine this site is running on.

	Hashed rather than stored plainly, so a backup being read somewhere does
	not hand over the names of internal hosts.
	"""
	return hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()[:16]


def production_sending_allowed() -> tuple[bool, str]:
	"""Whether this deployment may send in Production, and why not if not."""
	granted = frappe.conf.get(CONFIG_KEY)
	if not granted:
		return False, _("Production sending has not been enabled for this deployment.")
	if granted != frappe.local.site:
		# The key was granted for a different site, which means the config
		# was copied rather than set here.
		return False, _("Production sending was enabled for another site, not this one.")
	return True, ""


def check_environment() -> tuple[bool, str]:
	"""Whether anything may go out from here at all.

	Called before work is picked up. Returns whether to carry on, and the
	reason to record when not.
	"""
	current = host_fingerprint()
	known = frappe.db.get_global(HOST_KEY)

	if known and known != current:
		hold(
			_(
				"This site is running on a different machine than it last sent from. It may be a restored copy."
			)
		)
		return False, _(
			"The machine changed. Outbound work is paused until somebody confirms this is the right site."
		)

	if not known:
		frappe.db.set_global(HOST_KEY, current)
	return True, ""


def may_send(environment: str) -> tuple[bool, str]:
	"""Whether one particular connection's environment may be used now."""
	allowed, reason = check_environment()
	if not allowed:
		return False, reason
	if environment == "Production":
		return production_sending_allowed()
	return True, ""


def hold(reason: str):
	"""Pause outbound work and say why, without touching anything else.

	A pause stops new sends and retries. It does not change what validation
	says, throw queued work away, or stop us finding out what happened to
	something already sent.
	"""
	settings = frappe.get_single(SETTINGS)
	if settings.pause_outbound:
		return
	settings.pause_outbound = 1
	settings.pause_reason = reason
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()


@frappe.whitelist()
def confirm_this_machine() -> dict:
	"""Say that this really is the right site on a new machine.

	A manager does this deliberately after a genuine move. It records the
	machine and lifts the hold, and it never happens on its own.
	"""
	if not frappe.has_permission(SETTINGS, "write"):
		raise frappe.PermissionError

	frappe.db.set_global(HOST_KEY, host_fingerprint())
	settings = frappe.get_single(SETTINGS)
	settings.pause_outbound = 0
	settings.pause_reason = None
	settings.save()
	return {"host": host_fingerprint(), "paused": False}


def status() -> dict:
	"""What a person needs to see about this deployment."""
	allowed, reason = production_sending_allowed()
	return {
		"site": frappe.local.site,
		"host": host_fingerprint(),
		"known_host": frappe.db.get_global(HOST_KEY),
		"production_sending": allowed,
		"reason": reason,
	}
