"""The acceptance cases that need a database.

Named for the cases in spec 13, so a reader can go from the matrix to the
test and back. Everything here builds its own company and its own masters,
because a test that leans on whatever the site happens to hold is not a test
of anything.

These were deliberately left until the end. The maintainer asked for the
phases to be built through first and the testing done in one pass at P09,
which is what this is. So they are written to find defects rather than to
confirm what the code already does: where a test and the code disagree, the
spec decides which is wrong.
"""

import frappe
from frappe.tests import IntegrationTestCase

from uae_compliance.development.fixtures import (
	a_company,
	a_customer,
	a_seller,
	an_address,
	an_invoice,
	an_item,
)


class A08DraftAndPreview(IntegrationTestCase):
	"""Missing information still saves, and one save makes one working row."""

	def setUp(self):
		super().setUp()
		a_seller("Preparation")

	def test_an_invoice_missing_everything_still_saves(self):
		# The invariant that matters most. A compliance gap is never a reason
		# an invoice cannot be saved.
		invoice = an_invoice()
		self.assertEqual(invoice.docstatus, 0)
		self.assertTrue(frappe.db.exists("Sales Invoice", invoice.name))

	def test_saving_twice_makes_one_working_record(self):
		invoice = an_invoice()
		invoice.save(ignore_permissions=True)
		invoice.save(ignore_permissions=True)
		self.assertEqual(frappe.db.count("UAE Peppol Invoice", {"sales_invoice": invoice.name}), 1)

	def test_a_preview_writes_nothing(self):
		from uae_compliance.domain.findings import Level
		from uae_compliance.services import validation

		invoice = an_invoice()
		before = frappe.db.get_value("UAE Peppol Invoice", invoice.name, "modified")
		validation.check(invoice, Level.FULL)
		after = frappe.db.get_value("UAE Peppol Invoice", invoice.name, "modified")
		self.assertEqual(before, after)

	def test_a_check_does_not_move_the_input_revision(self):
		# Otherwise every check would look to the browser like somebody
		# else's edit and the concurrency guard would fire constantly.
		from uae_compliance.domain.findings import Level
		from uae_compliance.services import validation

		invoice = an_invoice()
		before = frappe.db.get_value("UAE Peppol Invoice", invoice.name, "input_revision")
		result = validation.check(invoice, Level.FULL)
		validation.record_result(invoice.name, result)
		after = frappe.db.get_value("UAE Peppol Invoice", invoice.name, "input_revision")
		self.assertEqual(before, after)


class A09ScopeEnforcement(IntegrationTestCase):
	"""Off leaves no trace, Preparation advises, Live blocks."""

	def test_a_company_nobody_configured_gets_no_record(self):
		# An app nobody asked for should be invisible.
		if frappe.db.exists("Company", "Unconfigured Acceptance Co"):
			company = "Unconfigured Acceptance Co"
		else:
			company = (
				frappe.get_doc(
					{
						"doctype": "Company",
						"company_name": "Unconfigured Acceptance Co",
						"abbr": "UAC",
						"default_currency": "AED",
						"country": "United Arab Emirates",
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
			frappe.db.commit()

		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": company,
				"customer": a_customer(),
				"currency": "AED",
				"conversion_rate": 1,
				"posting_date": "2026-09-19",
				"due_date": "2026-10-19",
				"items": [
					{
						"item_code": an_item(),
						"qty": 1,
						"uom": "Nos",
						"rate": 50,
						"income_account": frappe.db.get_value(
							"Account",
							{"company": company, "account_type": "Income Account", "is_group": 0},
							"name",
						),
						"cost_center": frappe.db.get_value(
							"Cost Center", {"company": company, "is_group": 0}, "name"
						),
					}
				],
			}
		)
		invoice.set_missing_values()
		invoice.calculate_taxes_and_totals()
		invoice.insert(ignore_permissions=True)
		self.assertFalse(frappe.db.exists("UAE Peppol Invoice", {"sales_invoice": invoice.name}))

	def test_preparation_lets_an_incomplete_invoice_submit(self):
		# The whole point of Preparation is seeing what would be wrong
		# without being stopped by it.
		a_seller("Preparation")
		invoice = an_invoice()
		invoice.submit()
		self.assertEqual(invoice.docstatus, 1)

	def test_live_refuses_an_incomplete_invoice(self):
		a_seller("Live")
		invoice = an_invoice()
		with self.assertRaises(frappe.ValidationError):
			invoice.submit()
		invoice.reload()
		self.assertEqual(invoice.docstatus, 0)

	def test_live_still_lets_the_draft_save(self):
		a_seller("Live")
		invoice = an_invoice()
		invoice.save(ignore_permissions=True)
		self.assertEqual(invoice.docstatus, 0)


class A12ApprovalAndImmutability(IntegrationTestCase):
	"""An approval names the content it agreed to, and nothing frozen moves."""

	def a_submission(self):
		a_seller("Preparation")
		invoice = an_invoice()
		control = frappe.db.get_value("UAE Peppol Invoice", {"sales_invoice": invoice.name}, "name")
		doc = frappe.new_doc("UAE Peppol Submission")
		doc.control = control
		doc.company = a_company()
		doc.revision = 1
		doc.document_number = invoice.name
		doc.document_uuid = "acceptance-uuid"
		doc.type_code = "380"
		doc.idempotency_key = f"acceptance-{invoice.name}"
		doc.canonical_hash = "a" * 64
		doc.payload_hash = "b" * 64
		doc.evidence_state = "Complete"
		doc.route_scheme = "0235"
		doc.route_value = "100000000000003"
		doc.processing_state = "Awaiting review"
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.db.sql, "delete from `tabUAE Peppol Submission` where name=%s", doc.name)
		return doc

	def test_a_frozen_field_cannot_change(self):
		doc = self.a_submission()
		doc.canonical_hash = "c" * 64
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_approving_the_wrong_hash_is_refused(self):
		from uae_compliance.services import approval

		doc = self.a_submission()
		with self.assertRaises(frappe.ValidationError):
			approval.approve(doc.name, "not the hash they saw")

	def test_approving_the_right_hash_makes_it_ready(self):
		from uae_compliance.services import approval

		doc = self.a_submission()
		approval.approve(doc.name, doc.canonical_hash)
		doc.reload()
		self.assertTrue(doc.approved)
		self.assertEqual(doc.processing_state, "Ready")
		self.assertEqual(doc.approved_canonical_hash, doc.canonical_hash)

	def test_an_approval_cannot_outlive_the_content_it_agreed_to(self):
		doc = self.a_submission()
		doc.approved = 1
		doc.approved_by = "Administrator"
		doc.approved_at = frappe.utils.now_datetime()
		doc.approved_canonical_hash = "something else entirely"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_approving_without_the_bytes_stored_is_refused(self):
		from uae_compliance.services import approval

		doc = self.a_submission()
		frappe.db.set_value("UAE Peppol Submission", doc.name, "evidence_state", "Pending")
		with self.assertRaises(frappe.ValidationError):
			approval.approve(doc.name, doc.canonical_hash)

	def test_approving_with_nowhere_to_send_it_is_refused(self):
		from uae_compliance.services import approval

		doc = self.a_submission()
		frappe.db.set_value("UAE Peppol Submission", doc.name, "route_value", None)
		with self.assertRaises(frappe.ValidationError):
			approval.approve(doc.name, doc.canonical_hash)


class A13ClaimingWork(IntegrationTestCase):
	"""Two workers reaching for the same submission means one of them gets it."""

	def a_ready_submission(self):
		a_seller("Preparation")
		invoice = an_invoice()
		control = frappe.db.get_value("UAE Peppol Invoice", {"sales_invoice": invoice.name}, "name")
		doc = frappe.new_doc("UAE Peppol Submission")
		doc.control = control
		doc.company = a_company()
		doc.revision = 1
		doc.document_number = invoice.name
		doc.document_uuid = "claim-uuid"
		doc.idempotency_key = f"claim-{invoice.name}"
		doc.canonical_hash = "d" * 64
		doc.approved_canonical_hash = "d" * 64
		doc.payload_hash = "e" * 64
		doc.approved = 1
		doc.approved_by = "Administrator"
		doc.approved_at = frappe.utils.now_datetime()
		doc.processing_state = "Ready"
		doc.next_attempt_at = frappe.utils.now_datetime()
		doc.evidence_state = "Complete"
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.db.sql, "delete from `tabUAE Peppol Submission` where name=%s", doc.name)
		return doc

	def test_only_one_worker_gets_it(self):
		from uae_compliance.services import outbox

		doc = self.a_ready_submission()
		first = outbox.claim(doc.name)
		second = outbox.claim(doc.name)
		self.assertIsNotNone(first)
		self.assertIsNone(second)

	def test_the_token_counts_up_on_every_claim(self):
		from uae_compliance.services import outbox

		doc = self.a_ready_submission()
		first = outbox.claim(doc.name)
		outbox.release(doc.name, "Ready")
		second = outbox.claim(doc.name)
		self.assertGreater(second["token"], first["token"])

	def test_an_older_worker_cannot_write_a_result(self):
		from uae_compliance.services import outbox

		doc = self.a_ready_submission()
		claim = outbox.claim(doc.name)
		attempt = outbox.start_attempt(doc.name, "submit", claim["token"], "digest")
		self.addCleanup(
			frappe.db.sql, "delete from `tabUAE Peppol Transmission Log` where attempt_id=%s", attempt
		)
		self.assertFalse(outbox.finish_attempt(attempt, claim["token"] - 1, transport_status="200"))
		self.assertTrue(outbox.finish_attempt(attempt, claim["token"], transport_status="200"))

	def test_work_that_is_finished_is_never_claimed_again(self):
		# The lease alone does not cover this. A settled submission whose
		# lease has run out must still not be picked up, which is what the
		# state test in the claim is for.
		from uae_compliance.services import outbox

		doc = self.a_ready_submission()
		for state in ("Complete", "Stopped", "Superseded", "Awaiting outcome"):
			frappe.db.set_value(
				"UAE Peppol Submission",
				doc.name,
				{"processing_state": state, "lease_owner": None, "lease_expires_at": None},
			)
			self.assertIsNone(outbox.claim(doc.name), f"{state} was claimed and should not be")

	def test_an_unapproved_submission_is_never_claimed(self):
		from uae_compliance.services import outbox

		doc = self.a_ready_submission()
		frappe.db.set_value("UAE Peppol Submission", doc.name, "approved", 0)
		self.assertIsNone(outbox.claim(doc.name))

	def test_a_pause_hands_out_nothing(self):
		from uae_compliance.services import outbox

		self.a_ready_submission()
		settings = frappe.get_single("UAE Peppol Settings")
		settings.pause_outbound = 1
		settings.pause_reason = "Acceptance test"
		settings.flags.ignore_permissions = True
		settings.save()
		self.addCleanup(self._resume)
		self.assertEqual(outbox.due(), [])

	def _resume(self):
		settings = frappe.get_single("UAE Peppol Settings")
		settings.pause_outbound = 0
		settings.pause_reason = None
		settings.flags.ignore_permissions = True
		settings.save()


class A18Cancellation(IntegrationTestCase):
	"""What may be stopped, and what has gone too far to stop."""

	def an_invoice_with_a_submission(self, **submission):
		a_seller("Preparation")
		invoice = an_invoice()
		invoice.submit()
		control = frappe.db.get_value("UAE Peppol Invoice", {"sales_invoice": invoice.name}, "name")
		doc = frappe.new_doc("UAE Peppol Submission")
		doc.control = control
		doc.company = a_company()
		doc.revision = 1
		doc.document_number = invoice.name
		doc.document_uuid = f"cancel-{invoice.name}"
		doc.idempotency_key = f"cancel-{invoice.name}"
		doc.canonical_hash = "f" * 64
		doc.payload_hash = "0" * 64
		doc.processing_state = "Ready"
		doc.update(submission)
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.db.sql, "delete from `tabUAE Peppol Submission` where name=%s", doc.name)
		return invoice, doc

	def test_nothing_sent_can_still_be_cancelled(self):
		invoice, submission = self.an_invoice_with_a_submission()
		invoice.cancel()
		self.assertEqual(invoice.docstatus, 2)
		self.assertEqual(
			frappe.db.get_value("UAE Peppol Submission", submission.name, "processing_state"),
			"Stopped",
		)

	def test_the_snapshot_survives_the_cancellation(self):
		# Stopping the intent is not the same as erasing what happened.
		invoice, submission = self.an_invoice_with_a_submission()
		invoice.cancel()
		kept = frappe.db.get_value(
			"UAE Peppol Submission", submission.name, ["canonical_hash", "payload_hash"], as_dict=True
		)
		self.assertEqual(kept.canonical_hash, "f" * 64)
		self.assertEqual(kept.payload_hash, "0" * 64)

	def test_something_in_flight_cannot_be_cancelled(self):
		invoice, _submission = self.an_invoice_with_a_submission(processing_state="Sending")
		with self.assertRaises(frappe.ValidationError) as refused:
			invoice.cancel()
		# The message matters as much as the refusal. A later guard would
		# also stop this one, and it would say something less useful.
		self.assertIn("waiting to hear", str(refused.exception))

	def test_an_unknown_outcome_cannot_be_cancelled(self):
		# The dangerous one. Something may be sitting at the provider.
		invoice, _submission = self.an_invoice_with_a_submission(processing_state="Unknown")
		with self.assertRaises(frappe.ValidationError) as refused:
			invoice.cancel()
		self.assertIn("waiting to hear", str(refused.exception))

	def test_something_delivered_cannot_be_cancelled(self):
		invoice, _submission = self.an_invoice_with_a_submission(exchange_state="Delivered")
		with self.assertRaises(frappe.ValidationError):
			invoice.cancel()

	def test_a_corrected_invoice_that_never_left_can_still_be_cancelled(self):
		# Correcting used to make an invoice permanently uncancellable.
		# Superseded says a revision was replaced, not that it went
		# anywhere, and one that went nowhere is not in the way.
		invoice, superseded = self.an_invoice_with_a_submission(
			processing_state="Superseded", asp_receipt="Not sent"
		)
		invoice.cancel()
		self.assertEqual(invoice.docstatus, 2)
		self.assertEqual(
			frappe.db.get_value("UAE Peppol Submission", superseded.name, "processing_state"),
			"Superseded",
			"the replaced revision should keep saying it was replaced",
		)

	def test_a_corrected_invoice_the_provider_took_cannot_be_cancelled(self):
		# The other half. If the replaced revision reached the other side,
		# a credit note is the way and not a cancellation.
		invoice, _superseded = self.an_invoice_with_a_submission(
			processing_state="Superseded", asp_receipt="Received"
		)
		with self.assertRaises(frappe.ValidationError) as refused:
			invoice.cancel()
		self.assertIn("reached the other side", str(refused.exception))

	def test_a_corrected_invoice_with_a_request_still_out_cannot_be_cancelled(self):
		from uae_compliance.services import outbox

		invoice, superseded = self.an_invoice_with_a_submission(processing_state="Superseded")
		attempt = outbox.start_attempt(superseded.name, "submit", 1, "digest")
		self.addCleanup(
			frappe.db.sql, "delete from `tabUAE Peppol Transmission Log` where attempt_id=%s", attempt
		)
		with self.assertRaises(frappe.ValidationError):
			invoice.cancel()

	def test_a_request_with_no_answer_blocks_cancellation(self):
		from uae_compliance.services import outbox

		invoice, submission = self.an_invoice_with_a_submission()
		attempt = outbox.start_attempt(submission.name, "submit", 1, "digest")
		self.addCleanup(
			frappe.db.sql, "delete from `tabUAE Peppol Transmission Log` where attempt_id=%s", attempt
		)
		with self.assertRaises(frappe.ValidationError):
			invoice.cancel()
