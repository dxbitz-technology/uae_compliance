"""Documents suppliers send us, and what becomes of them.

The newest code in the app and the only part that puts something into the
books, so it needs the most suspicion. The theme running through these: an
arriving document is a claim about what we owe, not a fact, and the app
must never turn one into a liability on its own.

These build on the published example invoices rather than documents this
app wrote. A reader that only understands its own output is not a reader.
"""

import pathlib

import frappe
from frappe.tests import IntegrationTestCase

from uae_compliance.development.fixtures import a_company

EXAMPLES = (
	pathlib.Path(frappe.get_app_path("uae_compliance"))
	/ "standards"
	/ "pint_ae"
	/ "1.0.4"
	/ "trn-invoice"
	/ "example"
)
SUPPLIER = "Receiving Test Supplier"
SUPPLIER_TAX_ID = "198765432102003"
CONNECTION = "Receiving Test Connection"


def an_example() -> bytes:
	"""A published invoice, standing in for one a supplier sent."""
	return sorted(EXAMPLES.glob("*.xml"))[0].read_bytes()


def a_connection() -> str:
	if not frappe.db.exists("UAE Peppol ASP", CONNECTION):
		frappe.get_doc(
			{
				"doctype": "UAE Peppol ASP",
				"label": CONNECTION,
				"provider_key": "reference_xml",
				"environment": "Simulation",
				"base_url": "http://127.0.0.1:9999/api/v1",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	return CONNECTION


PROD_CONNECTION = "Entering Order Connection"


def a_production_connection() -> str:
	"""A Production connection, so entering a purchase is not blocked.

	Nothing is ever sent through it. It exists because a simulation document
	must never become a real purchase, and these tests need one that can.
	"""
	if not frappe.db.exists("UAE Peppol ASP", PROD_CONNECTION):
		frappe.get_doc(
			{
				"doctype": "UAE Peppol ASP",
				"label": PROD_CONNECTION,
				"provider_key": "reference_xml",
				"environment": "Production",
				"base_url": "https://asp.example.test/api/v1",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	return PROD_CONNECTION


def a_supplier() -> str:
	if not frappe.db.exists("Supplier", SUPPLIER):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": SUPPLIER,
				"supplier_type": "Company",
				"tax_id": SUPPLIER_TAX_ID,
			}
		).insert(ignore_permissions=True)
	return SUPPLIER


class ReadingWhatArrived(IntegrationTestCase):
	def test_an_invoice_we_did_not_write_reads_correctly(self):
		from uae_compliance.validation.reader import summarise

		found = summarise(an_example())
		self.assertTrue(found["document_number"])
		self.assertTrue(found["supplier_name"])
		self.assertTrue(found["supplier_tax_id"])
		self.assertEqual(found["currency"], "AED")
		self.assertGreater(found["payable"], 0)
		self.assertGreater(found["line_count"], 0)

	def test_its_lines_read_too(self):
		from uae_compliance.validation.reader import lines

		rows = lines(an_example())
		self.assertTrue(rows)
		for row in rows:
			self.assertIsNotNone(row["quantity"])
			self.assertIsNotNone(row["net_amount"])

	def test_rubbish_does_not_read_as_an_invoice(self):
		from uae_compliance.validation.reader import summarise

		with self.assertRaises(Exception):
			summarise(b"<not-an-invoice>hello</not-an-invoice>\n" * 3)


class LandingWhatArrived(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		a_company()
		self.connection = frappe.get_doc("UAE Peppol ASP", a_connection())

	def land(self, body: bytes, identifier: str):
		from uae_compliance.connectors.registry import ArtifactRef
		from uae_compliance.services import receiving

		artifact = ArtifactRef(kind="inbound", identifier=identifier, media_type="application/xml", body=body)
		stored = receiving._land(self.connection, artifact)
		name = frappe.db.get_value(
			"UAE Peppol Inbound", {"connection": self.connection.name, "document_uuid": identifier}, "name"
		)
		if name:
			self.addCleanup(frappe.db.sql, "delete from `tabUAE Peppol Inbound` where name=%s", name)
		return stored, name

	def test_an_arrived_document_is_kept_with_what_it_says(self):
		stored, name = self.land(an_example(), "landing-1")
		self.assertEqual(stored, 1)
		kept = frappe.db.get_value(
			"UAE Peppol Inbound",
			name,
			["supplier_name", "document_number", "payable", "payload_digest", "environment"],
			as_dict=True,
		)
		self.assertTrue(kept.supplier_name)
		self.assertTrue(kept.document_number)
		self.assertGreater(kept.payable, 0)
		self.assertEqual(len(kept.payload_digest), 64)
		self.assertEqual(kept.environment, "Simulation")

	def test_the_same_document_twice_is_kept_once(self):
		self.land(an_example(), "landing-2")
		stored, _name = self.land(an_example(), "landing-2")
		self.assertEqual(stored, 0)

	def test_the_same_reference_with_different_contents_is_flagged(self):
		# Not a duplicate. Somebody has to look at that rather than us
		# picking which one is real.
		self.land(an_example(), "landing-3")
		altered = an_example().replace(b"<cbc:ID>", b"<cbc:ID>X", 1)
		self.land(altered, "landing-3")
		state = frappe.db.get_value(
			"UAE Peppol Inbound",
			{"connection": self.connection.name, "document_uuid": "landing-3"},
			["state", "match_note"],
			as_dict=True,
		)
		self.assertEqual(state.state, "Unmatched")
		self.assertIn("different contents", state.match_note)

	def test_no_supplier_is_created_from_an_arriving_document(self):
		before = frappe.db.count("Supplier")
		self.land(an_example(), "landing-4")
		self.assertEqual(frappe.db.count("Supplier"), before)

	def test_a_sender_we_do_not_know_lands_unmatched(self):
		# Changed so the sender is definitely nobody, rather than hoping
		# the site has not met them.
		body = an_example().replace(SUPPLIER_TAX_ID.encode(), b"100000000000999")
		_stored, name = self.land(body, "landing-5")
		kept = frappe.db.get_value(
			"UAE Peppol Inbound", name, ["state", "supplier", "match_note"], as_dict=True
		)
		self.assertIsNone(kept.supplier)
		self.assertEqual(kept.state, "Unmatched")
		self.assertIn("No supplier", kept.match_note)

	def test_a_sender_we_know_is_matched_by_tax_number(self):
		a_supplier()
		_stored, name = self.land(an_example(), "landing-6")
		self.assertEqual(frappe.db.get_value("UAE Peppol Inbound", name, "supplier"), SUPPLIER)

	def test_a_document_addressed_to_nobody_lands_against_nobody(self):
		# Frappe fills a company link from the site default when nothing
		# sets it, which would attribute a supplier's invoice by accident.
		# Testing the outcome rather than the guard, because there are two
		# guards and removing either one alone still looks fine.
		body = an_example().replace(b"134567890123003", b"100000000000998")
		_stored, name = self.land(body, "landing-7")
		self.assertIsNone(
			frappe.db.get_value("UAE Peppol Inbound", name, "company"),
			"a document addressed to a tax number nobody has was given a company",
		)

	def test_a_document_addressed_to_us_lands_against_us(self):
		# The other half. Refusing to attribute anything would also pass
		# the test above.
		company = a_company()
		frappe.db.set_value("Company", company, "tax_id", "100000000000997")
		self.addCleanup(frappe.db.set_value, "Company", company, "tax_id", None)
		body = an_example().replace(b"134567890123003", b"100000000000997")
		_stored, name = self.land(body, "landing-8")
		self.assertEqual(frappe.db.get_value("UAE Peppol Inbound", name, "company"), company)


class EnteringWhatArrived(IntegrationTestCase):
	"""Nothing becomes a purchase on its own."""

	def setUp(self):
		super().setUp()
		a_company()
		self.connection = frappe.get_doc("UAE Peppol ASP", a_connection())
		from uae_compliance.connectors.registry import ArtifactRef
		from uae_compliance.services import receiving

		receiving._land(
			self.connection,
			ArtifactRef(
				kind="inbound",
				identifier="entering-1",
				media_type="application/xml",
				body=an_example(),
			),
		)
		self.inbound = frappe.db.get_value("UAE Peppol Inbound", {"document_uuid": "entering-1"}, "name")
		self.addCleanup(frappe.db.sql, "delete from `tabUAE Peppol Inbound` where name=%s", self.inbound)

	def test_a_simulation_document_can_never_become_a_purchase(self):
		from uae_compliance.services import purchasing

		found = purchasing.plan(self.inbound)
		self.assertFalse(found["can_enter"])
		self.assertTrue(
			any("simulation" in block.lower() for block in found["blocks"]),
			f"nothing stopped it for being a simulation: {found['blocks']}",
		)

	def test_entering_it_is_refused_while_anything_blocks(self):
		from uae_compliance.services import purchasing

		with self.assertRaises(frappe.ValidationError):
			purchasing.create_draft(self.inbound)

	def test_nothing_was_posted_by_asking(self):
		from uae_compliance.services import purchasing

		before = frappe.db.count("Purchase Invoice")
		purchasing.plan(self.inbound)
		self.assertEqual(frappe.db.count("Purchase Invoice"), before)

	def test_every_reason_it_cannot_be_entered_is_given_at_once(self):
		# One refusal naming one problem makes somebody fix them one at a
		# time, finding the next each round. Built deliberately broken in
		# two ways rather than relying on what the site happens to hold.
		from uae_compliance.services import purchasing

		frappe.db.set_value("UAE Peppol Inbound", self.inbound, {"supplier": None, "company": None})
		found = purchasing.plan(self.inbound)
		joined = " ".join(found["blocks"]).lower()
		self.assertIn("no supplier", joined)
		self.assertIn("which company", joined)
		self.assertIn("simulation", joined)


class EnteringAgainstAnOrder(IntegrationTestCase):
	"""A document that names our order is entered against the order itself.

	The mapped path carries each row's link back to the order line, so the
	order's billed quantities move. A draft built from the document alone
	left the order untouched, and the same goods could be paid for twice:
	once against the arrived invoice and once against the order.
	"""

	def setUp(self):
		super().setUp()
		self.company = a_company()
		frappe.db.set_value("Company", self.company, "tax_id", "134567890123003")
		self.addCleanup(frappe.db.set_value, "Company", self.company, "tax_id", None)
		a_supplier()
		self.connection = frappe.get_doc("UAE Peppol ASP", a_production_connection())

	def an_order(self) -> str:
		from uae_compliance.development.fixtures import an_item

		order = frappe.get_doc(
			{
				"doctype": "Purchase Order",
				"company": self.company,
				"supplier": SUPPLIER,
				"currency": "AED",
				"conversion_rate": 1,
				"schedule_date": frappe.utils.nowdate(),
				"items": [
					{
						"item_code": an_item(),
						"qty": 2,
						"rate": 100,
						"schedule_date": frappe.utils.nowdate(),
					}
				],
			}
		)
		order.set_missing_values()
		order.insert(ignore_permissions=True)
		order.submit()
		self.addCleanup(frappe.db.sql, "delete from `tabPurchase Order Item` where parent=%s", order.name)
		self.addCleanup(frappe.db.sql, "delete from `tabPurchase Order` where name=%s", order.name)
		return order.name

	def land_with_reference(self, reference: str | None, identifier: str) -> str:
		from uae_compliance.connectors.registry import ArtifactRef
		from uae_compliance.services import receiving

		body = an_example()
		if reference:
			named = f"<cac:OrderReference><cbc:ID>{reference}</cbc:ID></cac:OrderReference>"
			body = body.replace(
				b"<cac:AccountingSupplierParty>", named.encode() + b"<cac:AccountingSupplierParty>", 1
			)
		receiving._land(
			self.connection,
			ArtifactRef(kind="inbound", identifier=identifier, media_type="application/xml", body=body),
		)
		name = frappe.db.get_value("UAE Peppol Inbound", {"document_uuid": identifier}, "name")
		self.addCleanup(frappe.db.sql, "delete from `tabUAE Peppol Inbound` where name=%s", name)
		return name

	def test_a_document_naming_our_order_is_entered_against_it(self):
		from uae_compliance.services import purchasing

		order = self.an_order()
		inbound = self.land_with_reference(order, "entering-order-1")
		found = purchasing.plan(inbound)
		self.assertEqual(found["order"], order)
		self.assertTrue(found["can_enter"], found["blocks"])

		name = purchasing.create_draft(inbound)
		self.addCleanup(frappe.db.sql, "delete from `tabPurchase Invoice Item` where parent=%s", name)
		self.addCleanup(frappe.db.sql, "delete from `tabPurchase Invoice` where name=%s", name)
		invoice = frappe.get_doc("Purchase Invoice", name)
		self.assertEqual(invoice.docstatus, 0)
		self.assertEqual(invoice.items[0].purchase_order, order)
		self.assertTrue(invoice.items[0].po_detail, "the row does not point back at the order line")
		self.assertEqual(
			invoice.bill_no, frappe.db.get_value("UAE Peppol Inbound", inbound, "document_number")
		)

	def test_a_reference_matching_no_order_is_said_plainly(self):
		from uae_compliance.services import purchasing

		inbound = self.land_with_reference("PO-NOBODY-KNOWS", "entering-order-2")
		found = purchasing.plan(inbound)
		self.assertIsNone(found["order"])
		self.assertIn("PO-NOBODY-KNOWS", found["order_note"])

	def test_a_fully_billed_order_blocks_entry(self):
		from uae_compliance.services import purchasing

		order = self.an_order()
		frappe.db.set_value("Purchase Order", order, "per_billed", 100)
		inbound = self.land_with_reference(order, "entering-order-3")
		found = purchasing.plan(inbound)
		self.assertFalse(found["can_enter"])
		self.assertTrue(any("fully billed" in block for block in found["blocks"]), found["blocks"])

	def test_a_document_naming_no_order_lists_the_open_ones(self):
		from uae_compliance.services import purchasing

		order = self.an_order()
		inbound = self.land_with_reference(None, "entering-order-4")
		found = purchasing.plan(inbound)
		self.assertIsNone(found["order"])
		self.assertIn(order, [row.name for row in found["open_orders"]])
