"""A connection to one provider, in one environment.

Two things this guards.

A connection's provider and environment are fixed once anything has gone
through it. Old submissions stay bound to the connection that carried them,
so repointing it at a different provider or from sandbox to production would
quietly rewrite what those records mean. Rotating the credentials on the same
connection is fine and expected; changing who is on the other end is not.

Credentials sit in child rows, which works, but the framework leaves the
stored secret behind when a row or its parent goes. So this cleans up after
itself. See the decision record for where that was established.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.password import delete_all_passwords_for, remove_encrypted_password

# Fixed once the connection has carried anything.
SETTLED_FIELDS = ("provider_key", "environment")

CREDENTIAL_DOCTYPE = "UAE Peppol ASP Credential"


class UAEPeppolASP(Document):
	def validate(self):
		self.protect_settled_fields()
		self.reject_duplicate_credential_keys()
		self.note_removed_credentials()
		self.bump_config_revision()

	def protect_settled_fields(self):
		"""Refuse a change that would rewrite what past submissions meant."""
		if self.is_new() or not self.has_been_used:
			return
		before = self.get_doc_before_save()
		if not before:
			return
		for field in SETTLED_FIELDS:
			if before.get(field) != self.get(field):
				frappe.throw(
					_(
						"This connection has already been used, so its {0} cannot change. "
						"Create a new connection instead."
					).format(_(self.meta.get_label(field))),
					title=_("Connection in use"),
				)

	def reject_duplicate_credential_keys(self):
		seen = set()
		for row in self.credentials or []:
			key = (row.credential_key or "").strip()
			if key in seen:
				frappe.throw(
					_("The credential key {0} appears more than once.").format(key),
					title=_("Duplicate credential"),
				)
			seen.add(key)

	def bump_config_revision(self):
		"""Count every saved change, so a submission can name the configuration it used."""
		if not self.is_new():
			self.config_revision = (self.config_revision or 0) + 1

	def note_removed_credentials(self):
		"""Remember which credential rows this save is dropping.

		Worked out from the document as it was, so only this connection's own
		rows are ever touched.
		"""
		before = self.get_doc_before_save()
		if not before:
			self.flags.removed_credentials = []
			return
		kept = {row.name for row in self.credentials or []}
		self.flags.removed_credentials = [
			row.name for row in (before.credentials or []) if row.name not in kept
		]

	def on_update(self):
		self.forget_removed_credentials()

	def forget_removed_credentials(self):
		"""Delete the stored secret of every credential row this save dropped.

		Removing a child row deletes the row and leaves its encrypted value
		behind, so without this a secret would outlive the record that
		explained what it was for.
		"""
		for name in self.flags.get("removed_credentials") or []:
			remove_encrypted_password(CREDENTIAL_DOCTYPE, name, "secret")

	def on_trash(self):
		"""Take the credentials with it.

		Deleting a document clears its own stored secrets but not those of its
		child rows, so without this a deleted connection would leave its
		credentials in the table.
		"""
		for row in self.credentials or []:
			delete_all_passwords_for(CREDENTIAL_DOCTYPE, row.name)
