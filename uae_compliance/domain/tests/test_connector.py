"""Checks on the adapter contract.

Most of these are about one thing: an invoice that may already be with the
provider must not be sent again on a guess. A late invoice is a nuisance. A
duplicate legal invoice is a problem for the client.
"""

from __future__ import annotations

import unittest

from uae_compliance.domain.connector import (
	Acknowledgements,
	Adapter,
	Advice,
	ArtifactRef,
	AspReceipt,
	ContractError,
	Disposition,
	Effect,
	Environment,
	Evidence,
	Exchange,
	Idempotency,
	Operation,
	Outcome,
	Registry,
	Reporting,
	Route,
	advise,
)
from uae_compliance.domain.findings import Finding, Severity, Stage

ALL_SENDING = frozenset(
	{
		Operation.AUTHENTICATE,
		Operation.SUBMIT,
		Operation.GET_STATUS,
	}
)


def an_adapter(**kwargs):
	base = {
		"provider_key": "example",
		"label": "Example Provider",
		"adapter_version": "1.0.0",
		"contract_version": 1,
		"environments": (Environment.SIMULATION,),
		"operations": ALL_SENDING,
		"request_format": "UBL XML",
		"authentication": "OAuth client credentials",
	}
	base.update(kwargs)
	return Adapter(**base)


def an_outcome(**kwargs):
	base = {
		"operation": Operation.SUBMIT,
		"disposition": Disposition.SUCCEEDED,
		"effect": Effect.APPLIED,
		"advice": Advice.DO_NOT_RETRY,
	}
	base.update(kwargs)
	return Outcome(**base)


class DeclaringAnAdapter(unittest.TestCase):
	def test_an_adapter_built_against_another_contract_is_refused(self):
		with self.assertRaises(ContractError):
			an_adapter(contract_version=2)

	def test_an_adapter_that_cannot_authenticate_or_send_is_refused(self):
		with self.assertRaises(ContractError):
			an_adapter(operations=frozenset({Operation.GET_STATUS}))

	def test_an_adapter_must_support_an_environment(self):
		with self.assertRaises(ContractError):
			an_adapter(environments=())

	def test_a_capability_not_declared_does_not_exist(self):
		adapter = an_adapter()
		self.assertTrue(adapter.supports(Operation.SUBMIT))
		self.assertFalse(adapter.supports(Operation.WITHDRAW))
		self.assertFalse(adapter.supports(Operation.FETCH_INBOUND))

	def test_an_idempotency_promise_must_be_real(self):
		with self.assertRaises(ContractError):
			Idempotency(scope="", expiry_seconds=3600)
		with self.assertRaises(ContractError):
			Idempotency(scope="per key", expiry_seconds=0)


class TheRegistry(unittest.TestCase):
	def test_an_import_path_is_refused(self):
		registry = Registry()
		with self.assertRaises(ContractError) as caught:
			registry.register("uae_compliance.adapters.example")
		self.assertIn("never a name or an import path", str(caught.exception))

	def test_an_unknown_provider_is_refused(self):
		with self.assertRaises(ContractError):
			Registry().get("nobody")

	def test_the_same_provider_cannot_be_registered_twice(self):
		registry = Registry()
		registry.register(an_adapter())
		with self.assertRaises(ContractError):
			registry.register(an_adapter())

	def test_requiring_an_undeclared_operation_is_refused(self):
		registry = Registry()
		registry.register(an_adapter())
		self.assertIs(registry.require("example", Operation.SUBMIT).provider_key, "example")
		with self.assertRaises(ContractError) as caught:
			registry.require("example", Operation.WITHDRAW)
		self.assertIn("withdraw", str(caught.exception))

	def test_it_lists_what_is_installed(self):
		registry = Registry()
		registry.register(an_adapter())
		registry.register(an_adapter(provider_key="another"))
		self.assertEqual(registry.keys(), ("another", "example"))


class EffectMustMatchWhatHappened(unittest.TestCase):
	def test_success_means_it_was_applied(self):
		with self.assertRaises(ContractError):
			an_outcome(disposition=Disposition.SUCCEEDED, effect=Effect.UNKNOWN)

	def test_a_rejection_means_nothing_was_applied(self):
		with self.assertRaises(ContractError):
			an_outcome(
				disposition=Disposition.BUSINESS_REJECTED,
				effect=Effect.APPLIED,
				advice=Advice.DO_NOT_RETRY,
			)

	def test_a_timeout_can_only_be_unknown(self):
		with self.assertRaises(ContractError):
			an_outcome(
				disposition=Disposition.TIMED_OUT,
				effect=Effect.NOT_APPLIED,
				advice=Advice.RECONCILE_FIRST,
			)

	def test_a_transport_failure_may_be_either_and_must_say_which(self):
		refused = an_outcome(
			disposition=Disposition.TRANSPORT_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.RETRY_SAME_PAYLOAD,
		)
		self.assertIs(refused.effect, Effect.NOT_APPLIED)
		lost = an_outcome(
			disposition=Disposition.TRANSPORT_FAILED,
			effect=Effect.UNKNOWN,
			advice=Advice.RECONCILE_FIRST,
		)
		self.assertIs(lost.effect, Effect.UNKNOWN)


class NeverResendOnAGuess(unittest.TestCase):
	def test_an_unknown_outcome_cannot_advise_sending_it_again(self):
		with self.assertRaises(ContractError) as caught:
			an_outcome(
				disposition=Disposition.TIMED_OUT,
				effect=Effect.UNKNOWN,
				advice=Advice.RETRY_SAME_PAYLOAD,
			)
		self.assertIn("reconcile first or hold it", str(caught.exception))

	def test_a_provider_with_no_way_to_settle_it_holds_for_a_person(self):
		outcome = an_outcome(
			disposition=Disposition.TIMED_OUT,
			effect=Effect.UNKNOWN,
			advice=Advice.RECONCILE_FIRST,
		)
		adapter = an_adapter(idempotency=None, can_search_by_key=False)
		self.assertIs(advise(outcome, adapter), Advice.HOLD_FOR_PERSON)

	def test_a_provider_that_can_be_searched_reconciles_instead(self):
		outcome = an_outcome(
			disposition=Disposition.TIMED_OUT,
			effect=Effect.UNKNOWN,
			advice=Advice.HOLD_FOR_PERSON,
		)
		adapter = an_adapter(can_search_by_key=True)
		self.assertIs(advise(outcome, adapter), Advice.RECONCILE_FIRST)

	def test_a_promised_idempotency_also_allows_reconciling(self):
		outcome = an_outcome(
			disposition=Disposition.UNKNOWN,
			effect=Effect.UNKNOWN,
			advice=Advice.HOLD_FOR_PERSON,
		)
		adapter = an_adapter(idempotency=Idempotency("per idempotency key", 86400))
		self.assertIs(advise(outcome, adapter), Advice.RECONCILE_FIRST)

	def test_a_known_outcome_keeps_the_advice_it_came_with(self):
		outcome = an_outcome(
			disposition=Disposition.TRANSPORT_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.RETRY_SAME_PAYLOAD,
		)
		self.assertIs(advise(outcome, an_adapter()), Advice.RETRY_SAME_PAYLOAD)

	def test_an_adapter_says_whether_it_can_settle_an_ambiguous_send(self):
		self.assertFalse(an_adapter().can_resolve_an_ambiguous_send())
		self.assertTrue(an_adapter(can_search_by_key=True).can_resolve_an_ambiguous_send())
		self.assertTrue(an_adapter(idempotency=Idempotency("per key", 3600)).can_resolve_an_ambiguous_send())


class RejectionsAndLimits(unittest.TestCase):
	def test_a_rejected_document_needs_a_correction_not_another_attempt(self):
		for advice in (Advice.RETRY_SAME_PAYLOAD, Advice.RECONCILE_FIRST):
			with self.assertRaises(ContractError):
				an_outcome(
					disposition=Disposition.BUSINESS_REJECTED,
					effect=Effect.NOT_APPLIED,
					advice=advice,
				)

	def test_a_rejection_may_carry_what_the_provider_objected_to(self):
		finding = Finding(
			code="PROV-0001",
			severity=Severity.ERROR,
			stage=Stage.PROVIDER_RESPONSE,
			message="Buyer identifier not recognised.",
			path="parties.buyer.participant",
			repair="open_party_profile",
		)
		outcome = an_outcome(
			disposition=Disposition.BUSINESS_REJECTED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.DO_NOT_RETRY,
			findings=(finding,),
		)
		self.assertEqual(outcome.findings[0].code, "PROV-0001")

	def test_a_local_finding_cannot_be_passed_off_as_the_providers(self):
		local = Finding(
			code="CANON-0001",
			severity=Severity.ERROR,
			stage=Stage.CANONICAL,
			message="This value is required.",
			path="document.number",
			repair="supply_value",
		)
		with self.assertRaises(ContractError):
			an_outcome(
				disposition=Disposition.BUSINESS_REJECTED,
				effect=Effect.NOT_APPLIED,
				advice=Advice.DO_NOT_RETRY,
				findings=(local,),
			)

	def test_a_rate_limit_must_say_how_long_to_wait(self):
		with self.assertRaises(ContractError):
			an_outcome(
				disposition=Disposition.RATE_LIMITED,
				effect=Effect.NOT_APPLIED,
				advice=Advice.RETRY_SAME_PAYLOAD,
			)
		ok = an_outcome(
			disposition=Disposition.RATE_LIMITED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.RETRY_SAME_PAYLOAD,
			retry_after_seconds=120,
		)
		self.assertEqual(ok.retry_after_seconds, 120)

	def test_a_rate_limit_is_waited_out_not_corrected(self):
		with self.assertRaises(ContractError):
			an_outcome(
				disposition=Disposition.RATE_LIMITED,
				effect=Effect.NOT_APPLIED,
				advice=Advice.DO_NOT_RETRY,
				retry_after_seconds=60,
			)

	def test_stale_credentials_are_not_a_rejected_document(self):
		outcome = an_outcome(
			disposition=Disposition.AUTHENTICATION_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.REFRESH_AUTHENTICATION,
		)
		self.assertIsNot(outcome.disposition, Disposition.BUSINESS_REJECTED)


class NeverResendWhatTheProviderAlreadyHas(unittest.TestCase):
	def test_an_applied_submit_cannot_advise_sending_it_again(self):
		with self.assertRaises(ContractError) as caught:
			an_outcome(
				operation=Operation.SUBMIT,
				disposition=Disposition.SUCCEEDED,
				effect=Effect.APPLIED,
				advice=Advice.RETRY_SAME_PAYLOAD,
			)
		self.assertIn("already took this", str(caught.exception))

	def test_that_holds_even_when_the_provider_promises_idempotency(self):
		# The promise makes a repeat safe, not useful. The document is already
		# there; whatever is missing is fetched by its own operation.
		with self.assertRaises(ContractError):
			an_outcome(effect=Effect.APPLIED, advice=Advice.RETRY_SAME_PAYLOAD)

	def test_nor_can_it_ask_for_a_credential_refresh(self):
		# A refresh ends in the same bytes going out again, so it is a retry
		# under another name. The worker schedules one without looking at the
		# effect, which is why the contract has to refuse the pairing here.
		with self.assertRaises(ContractError) as caught:
			an_outcome(
				operation=Operation.SUBMIT,
				disposition=Disposition.SUCCEEDED,
				effect=Effect.APPLIED,
				advice=Advice.REFRESH_AUTHENTICATION,
			)
		self.assertIn("applied nothing", str(caught.exception))

	def test_and_neither_can_an_outcome_nobody_could_read(self):
		with self.assertRaises(ContractError):
			an_outcome(
				operation=Operation.SUBMIT,
				disposition=Disposition.TIMED_OUT,
				effect=Effect.UNKNOWN,
				advice=Advice.REFRESH_AUTHENTICATION,
			)

	def test_stale_credentials_that_sent_nothing_may_still_refresh(self):
		outcome = an_outcome(
			operation=Operation.SUBMIT,
			disposition=Disposition.AUTHENTICATION_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.REFRESH_AUTHENTICATION,
		)
		self.assertIs(outcome.advice, Advice.REFRESH_AUTHENTICATION)

	def test_a_missing_artifact_is_fetched_not_resubmitted(self):
		outcome = an_outcome(
			operation=Operation.FETCH_ARTIFACT,
			disposition=Disposition.TRANSPORT_FAILED,
			effect=Effect.NOT_APPLIED,
			advice=Advice.RETRY_SAME_PAYLOAD,
		)
		self.assertIs(outcome.operation, Operation.FETCH_ARTIFACT)


class TheFourOutcomesStayApart(unittest.TestCase):
	def test_nothing_is_acknowledged_until_it_is(self):
		acks = Acknowledgements()
		self.assertIs(acks.asp_receipt, AspReceipt.NOT_SENT)
		self.assertFalse(acks.complete(Route()))

	def test_the_provider_receiving_it_is_not_delivery(self):
		acks = Acknowledgements(asp_receipt=AspReceipt.RECEIVED)
		self.assertIs(acks.exchange, Exchange.NOT_STARTED)
		self.assertFalse(acks.complete(Route()))

	def test_delivery_is_not_reporting(self):
		acks = Acknowledgements(
			asp_receipt=AspReceipt.RECEIVED,
			exchange=Exchange.DELIVERED,
			evidence=Evidence.COMPLETE,
		)
		self.assertFalse(acks.complete(Route()))

	def test_reporting_accepted_without_the_evidence_is_not_complete(self):
		acks = Acknowledgements(
			asp_receipt=AspReceipt.RECEIVED,
			exchange=Exchange.DELIVERED,
			reporting=Reporting.ACCEPTED,
			evidence=Evidence.PENDING,
		)
		self.assertFalse(acks.complete(Route()))

	def test_complete_needs_all_four(self):
		acks = Acknowledgements(
			asp_receipt=AspReceipt.RECEIVED,
			exchange=Exchange.DELIVERED,
			reporting=Reporting.ACCEPTED,
			evidence=Evidence.COMPLETE,
		)
		self.assertTrue(acks.complete(Route()))

	def test_a_step_may_be_skipped_only_where_the_route_says_so(self):
		acks = Acknowledgements(
			asp_receipt=AspReceipt.RECEIVED,
			exchange=Exchange.NOT_APPLICABLE,
			reporting=Reporting.ACCEPTED,
			evidence=Evidence.COMPLETE,
		)
		self.assertTrue(acks.complete(Route(exchange_required=False)))
		self.assertFalse(acks.complete(Route()))

	def test_reporting_cannot_be_waved_away_on_a_route_that_requires_it(self):
		# Otherwise an invoice could read as complete having never been
		# reported, which is the worst thing this table could get wrong.
		acks = Acknowledgements(
			asp_receipt=AspReceipt.RECEIVED,
			exchange=Exchange.DELIVERED,
			reporting=Reporting.NOT_APPLICABLE,
			evidence=Evidence.COMPLETE,
		)
		self.assertFalse(acks.complete(Route()))
		self.assertTrue(acks.complete(Route(reporting_required=False)))

	def test_a_rejection_downstream_is_not_complete(self):
		acks = Acknowledgements(
			asp_receipt=AspReceipt.RECEIVED,
			exchange=Exchange.DELIVERED,
			reporting=Reporting.REJECTED,
			evidence=Evidence.COMPLETE,
		)
		self.assertFalse(acks.complete(Route()))


class WhatTheProviderSaidIsKeptButNeverDecides(unittest.TestCase):
	def test_a_provider_code_rides_along_without_changing_anything(self):
		outcome = an_outcome(provider_code="ACCEPTED_200", provider_ids={"submission": "abc"})
		self.assertEqual(outcome.provider_code, "ACCEPTED_200")
		self.assertIs(outcome.advice, Advice.DO_NOT_RETRY)

	def test_two_providers_saying_it_differently_give_the_same_decision(self):
		one = an_outcome(
			disposition=Disposition.TIMED_OUT,
			effect=Effect.UNKNOWN,
			advice=Advice.RECONCILE_FIRST,
			provider_code="ETIMEDOUT",
		)
		two = an_outcome(
			disposition=Disposition.TIMED_OUT,
			effect=Effect.UNKNOWN,
			advice=Advice.RECONCILE_FIRST,
			provider_code="504_UPSTREAM",
		)
		adapter = an_adapter()
		self.assertEqual(advise(one, adapter), advise(two, adapter))

	def test_an_artifact_is_carried_by_reference(self):
		ref = ArtifactRef(kind="returned_xml", identifier="doc-1", media_type="application/xml")
		outcome = an_outcome(artifacts=(ref,))
		self.assertEqual(outcome.artifacts[0].kind, "returned_xml")
		with self.assertRaises(ContractError):
			ArtifactRef(kind="", identifier="doc-1")


if __name__ == "__main__":
	unittest.main(verbosity=2)
