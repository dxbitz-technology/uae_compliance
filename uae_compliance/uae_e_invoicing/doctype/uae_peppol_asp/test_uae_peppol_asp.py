"""The provider connection, tested against a real site.

These need a database. They cover the two things that would do real damage:
a connection being repointed at a different provider after it has carried
work, and a credential outliving the record that explained what it was for.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password

CREDENTIAL_DOCTYPE = "UAE Peppol ASP Credential"


def stored_secret_exists(row_name: str) -> bool:
	"""Whether an encrypted value is still sitting in the table for this row."""
	return bool(
		frappe.db.sql(
			"select 1 from `__Auth` where doctype=%s and name=%s and fieldname='secret'",
			(CREDENTIAL_DOCTYPE, row_name),
		)
	)


class TestUAEPeppolASP(IntegrationTestCase):
	def a_connection(self, label="Test Provider", **values):
		doc = frappe.get_doc(
			{
				"doctype": "UAE Peppol ASP",
				"label": label,
				"provider_key": "example",
				"environment": "Simulation",
				"base_url": "https://example.invalid",
				**values,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def with_credential(self, doc, key="client_secret", secret="a-secret-value"):
		doc.append("credentials", {"credential_key": key, "secret": secret})
		doc.save(ignore_permissions=True)
		return doc.credentials[-1]

	def test_a_fresh_connection_starts_disabled_and_unused(self):
		doc = self.a_connection("Fresh One")
		self.assertFalse(doc.enabled)
		self.assertFalse(doc.has_been_used)
		self.assertEqual(doc.connection_state, "Not checked")

	def test_provider_and_environment_can_change_before_anything_is_sent(self):
		doc = self.a_connection("Not Yet Used")
		doc.environment = "Sandbox"
		doc.provider_key = "another"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.environment, "Sandbox")

	def test_the_provider_cannot_change_once_it_has_carried_work(self):
		doc = self.a_connection("Used One")
		frappe.db.set_value("UAE Peppol ASP", doc.name, "has_been_used", 1)
		doc.reload()
		doc.provider_key = "someone-else"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_the_environment_cannot_change_once_it_has_carried_work(self):
		# Sandbox to production on the same record would quietly rewrite what
		# every past submission through it meant.
		doc = self.a_connection("Used Two")
		frappe.db.set_value("UAE Peppol ASP", doc.name, "has_been_used", 1)
		doc.reload()
		doc.environment = "Production"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_the_address_cannot_change_once_it_has_carried_work(self):
		# Repointing a used connection moves the polling and the credentials
		# of every past submission to a different server.
		doc = self.a_connection("Used Address")
		frappe.db.set_value("UAE Peppol ASP", doc.name, "has_been_used", 1)
		doc.reload()
		doc.base_url = "https://somewhere-else.invalid"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_clearing_the_flag_does_not_unlock_a_connection_with_records(self):
		# The flag is an ordinary field, so a write can clear it. The attempt
		# records are the evidence, and they do not have a reset switch.
		doc = self.a_connection("Used Evidence")
		log = frappe.new_doc("UAE Peppol Transmission Log")
		log.attempt_id = frappe.generate_hash(length=32)
		log.connection = doc.name
		log.operation = "http:submit"
		log.state = "Finished"
		log.insert(ignore_permissions=True)

		frappe.db.set_value("UAE Peppol ASP", doc.name, "has_been_used", 0)
		doc.reload()
		doc.environment = "Production"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_rotating_a_credential_on_a_used_connection_is_allowed(self):
		# Changing the secret is expected. Changing who is on the other end is not.
		doc = self.a_connection("Used Three")
		self.with_credential(doc)
		frappe.db.set_value("UAE Peppol ASP", doc.name, "has_been_used", 1)
		doc.reload()
		doc.credentials[0].secret = "a-new-secret"
		doc.save(ignore_permissions=True)
		self.assertEqual(
			get_decrypted_password(CREDENTIAL_DOCTYPE, doc.credentials[0].name, "secret"),
			"a-new-secret",
		)

	def test_a_secret_is_stored_encrypted_and_not_in_the_row(self):
		doc = self.a_connection("Secret Holder")
		row = self.with_credential(doc, secret="top-secret")
		stored = frappe.db.get_value(CREDENTIAL_DOCTYPE, row.name, "secret")
		self.assertNotEqual(stored, "top-secret")
		self.assertEqual(get_decrypted_password(CREDENTIAL_DOCTYPE, row.name, "secret"), "top-secret")

	def test_removing_a_credential_row_takes_its_secret_with_it(self):
		# The framework deletes the row and leaves the secret behind, so the
		# connection has to clean up after itself.
		doc = self.a_connection("Dropper")
		row = self.with_credential(doc)
		self.assertTrue(stored_secret_exists(row.name))
		doc.credentials = []
		doc.save(ignore_permissions=True)
		self.assertFalse(stored_secret_exists(row.name))

	def test_deleting_a_connection_takes_its_credentials_with_it(self):
		doc = self.a_connection("Doomed")
		row = self.with_credential(doc)
		self.assertTrue(stored_secret_exists(row.name))
		doc.delete(ignore_permissions=True)
		self.assertFalse(stored_secret_exists(row.name))

	def test_removing_one_credential_leaves_the_others_alone(self):
		doc = self.a_connection("Two Keys")
		first = self.with_credential(doc, key="client_id", secret="one")
		second = self.with_credential(doc, key="client_secret", secret="two")
		doc.credentials = [r for r in doc.credentials if r.name != first.name]
		doc.save(ignore_permissions=True)
		self.assertFalse(stored_secret_exists(first.name))
		self.assertTrue(stored_secret_exists(second.name))

	def test_the_same_credential_key_twice_is_refused(self):
		doc = self.a_connection("Duplicated")
		doc.append("credentials", {"credential_key": "client_secret", "secret": "one"})
		doc.append("credentials", {"credential_key": "client_secret", "secret": "two"})
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_two_connections_cannot_share_a_label(self):
		self.a_connection("Only One Of These")
		with self.assertRaises(frappe.DuplicateEntryError):
			self.a_connection("Only One Of These")

	def test_saving_counts_up_the_configuration_revision(self):
		# A submission records which configuration it used, so every saved
		# change has to be countable.
		doc = self.a_connection("Counter")
		self.assertEqual(doc.config_revision, 0)
		doc.base_url = "https://example.invalid/v2"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.config_revision, 1)
