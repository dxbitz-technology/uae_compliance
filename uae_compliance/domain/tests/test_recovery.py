"""The rules about claiming, letting go, stopping, and correcting.

The cases here are the ones that end in two legal invoices if they are got
wrong, so each one is written as the sequence that produces it rather than as
a table of inputs.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from uae_compliance.domain.recovery import (
	ABANDONED_AFTER_SECONDS,
	CLAIMABLE,
	CORRECTABLE,
	IN_FLIGHT,
	LEASE_SECONDS,
	SETTLED,
	STOPPABLE,
	lease_is_live,
	may_overwrite,
	why_it_may_be_out_there,
)

NOW = datetime(2026, 9, 19, 12, 0, 0)


def out_there(state="Ready", receipt="Not sent", exchange="Not started", reporting="Not started", **kwargs):
	return why_it_may_be_out_there(state, receipt, exchange, reporting, **kwargs)


class TheFencingToken(unittest.TestCase):
	def test_the_worker_that_still_holds_the_claim_may_write(self):
		self.assertTrue(may_overwrite(7, 7))

	def test_a_worker_whose_claim_was_taken_over_may_not(self):
		# Its reply describes a world that has already moved on.
		self.assertFalse(may_overwrite(7, 8))

	def test_a_token_from_the_future_is_allowed_through(self):
		# It cannot happen from a claim, and refusing it would lose a result
		# that is newer than anything written down.
		self.assertTrue(may_overwrite(9, 8))

	def test_a_submission_that_is_gone_does_not_block_the_record(self):
		self.assertTrue(may_overwrite(3, None))


class TheLease(unittest.TestCase):
	def test_nobody_holds_a_submission_with_no_claim_on_it(self):
		self.assertFalse(lease_is_live(None, NOW))

	def test_a_claim_that_has_run_out_is_not_a_claim(self):
		self.assertFalse(lease_is_live(NOW - timedelta(seconds=1), NOW))

	def test_a_claim_still_in_date_is_held(self):
		self.assertTrue(lease_is_live(NOW + timedelta(seconds=1), NOW))

	def test_an_attempt_is_only_abandoned_after_the_claim_covering_it(self):
		# Recovering one earlier takes the work off a worker that is still
		# talking to the provider, and then two writers race for the row.
		self.assertGreater(ABANDONED_AFTER_SECONDS, LEASE_SECONDS)


class WhetherItMayAlreadyBeOutThere(unittest.TestCase):
	def test_frozen_and_never_picked_up_is_free(self):
		self.assertIsNone(out_there(state="Ready"))

	def test_so_is_one_the_provider_refused_on_its_merits(self):
		self.assertIsNone(out_there(state="Attention required", receipt="Rejected"))

	def test_anything_in_flight_is_not(self):
		for state in IN_FLIGHT:
			self.assertIsNotNone(out_there(state=state), state)

	def test_nor_is_anything_already_settled(self):
		for state in SETTLED:
			self.assertIsNotNone(out_there(state=state), state)

	def test_a_request_that_never_came_back_blocks_it(self):
		self.assertIsNotNone(out_there(state="Ready", pending_attempt=True))

	def test_a_worker_holding_it_blocks_it(self):
		self.assertIsNotNone(out_there(state="Ready", lease_live=True))

	def test_the_provider_having_received_it_blocks_it(self):
		# Reachable: the send succeeds, then asking is impossible, so the
		# state falls back to Attention required while the receipt still says
		# the provider has the document.
		self.assertIsNotNone(out_there(state="Attention required", receipt="Received"))

	def test_and_so_does_a_receipt_nobody_could_settle(self):
		# Unknown means the provider may be holding it. Making a second
		# revision here is how the same invoice goes out twice.
		self.assertIsNotNone(out_there(state="Attention required", receipt="Unknown"))

	def test_delivery_blocks_it_even_where_the_state_looks_free(self):
		self.assertIsNotNone(out_there(state="Attention required", exchange="Delivered"))

	def test_and_so_does_reporting(self):
		self.assertIsNotNone(out_there(state="Attention required", reporting="Accepted"))


class TheStateSetsDoNotOverlap(unittest.TestCase):
	def test_nothing_a_worker_may_claim_is_also_something_to_stop(self):
		# They do overlap, on purpose, and that is exactly why stopping has
		# to be one atomic update rather than a read and then a write.
		self.assertTrue(set(CLAIMABLE) & set(STOPPABLE))

	def test_nothing_in_flight_can_be_claimed(self):
		self.assertFalse(set(CLAIMABLE) & set(IN_FLIGHT))

	def test_nothing_in_flight_can_be_stopped_or_corrected(self):
		self.assertFalse(set(IN_FLIGHT) & set(STOPPABLE))
		self.assertFalse(set(IN_FLIGHT) & set(CORRECTABLE))

	def test_a_refused_document_can_be_corrected_but_not_cancelled(self):
		# Correcting a rejection is the normal path. Cancelling the invoice
		# underneath it is a different act and has its own rules.
		self.assertIn("Attention required", CORRECTABLE)
		self.assertNotIn("Attention required", STOPPABLE)


if __name__ == "__main__":
	unittest.main()
