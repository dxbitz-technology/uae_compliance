"""Checks on what this installation will run and what it will refuse.

The thread through all of them: an adapter arrives as an object somebody
already trusted, an undeclared capability does not exist, and nothing the
simulator issued can be pointed at Production.
"""

from __future__ import annotations

import unittest

from uae_compliance.connectors.registry import (
	AdapterRegistry,
	BusinessRequest,
	Call,
	Connection,
	ProviderAdapter,
	Session,
	load_hook_adapters,
)
from uae_compliance.domain.connector import (
	Adapter,
	Advice,
	ContractError,
	Disposition,
	Effect,
	Environment,
	Operation,
	Outcome,
)

SENDING = frozenset({Operation.AUTHENTICATE, Operation.SUBMIT, Operation.GET_STATUS})


def a_declaration(**kwargs):
	base = {
		"provider_key": "example",
		"label": "Example Provider",
		"adapter_version": "1.0.0",
		"contract_version": 1,
		"environments": (Environment.SIMULATION, Environment.SANDBOX),
		"operations": SENDING,
		"request_format": "UBL XML",
		"authentication": "OAuth client credentials",
	}
	base.update(kwargs)
	return Adapter(**base)


class Fake:
	def __init__(self, **kwargs):
		self.descriptor = a_declaration(**kwargs)

	def perform(self, call, transport):
		return Outcome(
			operation=call.operation,
			disposition=Disposition.SUCCEEDED,
			effect=Effect.APPLIED,
			advice=Advice.DO_NOT_RETRY,
		)


def a_connection(**kwargs):
	base = {
		"provider_key": "example",
		"connection_id": "Example Sandbox",
		"environment": Environment.SANDBOX,
		"base_url": "https://api.example.test",
	}
	base.update(kwargs)
	return Connection(**base)


class WhatMayBeRegistered(unittest.TestCase):
	def setUp(self):
		self.registry = AdapterRegistry()

	def test_an_import_path_is_refused(self):
		with self.assertRaises(ContractError):
			self.registry.register("other_app.peppol.adapter.build")

	def test_something_with_no_declaration_is_refused(self):
		class Bare:
			def perform(self, call, transport):
				return None

		with self.assertRaises(ContractError):
			self.registry.register(Bare())

	def test_a_declaration_with_nothing_behind_it_is_refused(self):
		class Idle:
			descriptor = a_declaration()

		with self.assertRaises(ContractError):
			self.registry.register(Idle())

	def test_an_adapter_object_is_accepted_and_found_again(self):
		adapter = Fake()
		self.registry.register(adapter)
		self.assertIs(self.registry.get("example"), adapter)
		self.assertEqual(self.registry.keys(), ("example",))

	def test_the_fake_answers_the_adapter_protocol(self):
		self.assertIsInstance(Fake(), ProviderAdapter)


class WhatMayBeAskedOfAnAdapter(unittest.TestCase):
	def setUp(self):
		self.registry = AdapterRegistry()
		self.registry.register(Fake())

	def test_an_undeclared_operation_does_not_exist(self):
		with self.assertRaises(ContractError):
			self.registry.require("example", Operation.WITHDRAW)

	def test_a_declared_operation_is_handed_over(self):
		self.assertIsNotNone(self.registry.require("example", Operation.SUBMIT))

	def test_an_environment_the_adapter_never_declared_is_refused(self):
		connection = a_connection(environment=Environment.PRODUCTION)
		with self.assertRaises(ContractError):
			self.registry.for_connection(connection, Operation.SUBMIT)

	def test_an_adapter_nobody_installed_is_not_reachable(self):
		with self.assertRaises(ContractError):
			self.registry.get("suntech")


class WhatTheAppHookMayAdd(unittest.TestCase):
	def setUp(self):
		self.registry = AdapterRegistry()
		self.registry.register(Fake(), built_in=True)

	def test_another_app_may_add_its_own_adapter(self):
		added = load_hook_adapters(self.registry, [("other_app", Fake(provider_key="other"))])
		self.assertEqual(added, ("other",))
		self.assertIn("other", self.registry.keys())

	def test_a_hook_cannot_replace_an_adapter_we_ship(self):
		with self.assertRaises(ContractError):
			load_hook_adapters(self.registry, [("other_app", Fake())])

	def test_a_named_path_is_not_imported_by_this_module(self):
		with self.assertRaises(ContractError):
			load_hook_adapters(self.registry, [("other_app", "other_app.peppol.build")])

	def test_a_name_is_resolved_by_the_caller_and_not_here(self):
		def resolve(path):
			self.assertEqual(path, "other_app.peppol.build")
			return Fake(provider_key="other")

		added = load_hook_adapters(self.registry, [("other_app", "other_app.peppol.build")], resolve)
		self.assertEqual(added, ("other",))


class WhatAProductionConnectionRefuses(unittest.TestCase):
	def test_a_simulation_credential_cannot_be_used_in_production(self):
		with self.assertRaises(ContractError):
			a_connection(
				environment=Environment.PRODUCTION,
				credentials={"client_secret": "sim_abc123"},
			)

	def test_a_production_connection_cannot_point_at_this_machine(self):
		with self.assertRaises(ContractError):
			a_connection(environment=Environment.PRODUCTION, base_url="http://localhost:8020")

	def test_an_identifier_the_simulator_issued_cannot_be_chased_in_production(self):
		connection = a_connection(environment=Environment.PRODUCTION, base_url="https://api.example.test")
		with self.assertRaises(ContractError):
			Call(
				operation=Operation.GET_STATUS,
				connection=connection,
				provider_ids={"document_id": "SIM-000123"},
			)

	def test_the_same_identifier_is_fine_in_simulation(self):
		call = Call(
			operation=Operation.GET_STATUS,
			connection=a_connection(environment=Environment.SIMULATION),
			provider_ids={"document_id": "SIM-000123"},
		)
		self.assertEqual(call.provider_ids["document_id"], "SIM-000123")


class WhatTheApprovedBytesGuarantee(unittest.TestCase):
	def test_the_digest_is_worked_out_when_it_is_not_given(self):
		request = BusinessRequest(media_type="application/xml", body=b"<Invoice/>")
		self.assertEqual(len(request.digest), 64)

	def test_bytes_that_do_not_match_their_digest_are_refused(self):
		with self.assertRaises(ContractError):
			BusinessRequest(media_type="application/xml", body=b"<Invoice/>", digest="0" * 64)


class WhenATokenCountsAsUsable(unittest.TestCase):
	def test_no_token_is_never_usable(self):
		self.assertFalse(Session().valid(now=0))

	def test_a_token_expiring_during_the_call_is_treated_as_expired(self):
		session = Session()
		session.hold("sim_token", expires_in=10, now=0)
		self.assertFalse(session.valid(now=0))

	def test_a_token_with_room_to_spare_is_usable(self):
		session = Session()
		session.hold("sim_token", expires_in=3600, now=0)
		self.assertTrue(session.valid(now=0))

	def test_the_token_is_one_of_the_values_the_transport_masks(self):
		connection = a_connection(credentials={"client_secret": "shh-this-is-secret"})
		connection.session.hold("sim_token_value", expires_in=60)
		self.assertIn("sim_token_value", connection.secrets())
		self.assertIn("shh-this-is-secret", connection.secrets())


if __name__ == "__main__":
	unittest.main()
