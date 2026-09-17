"""Checks on the schema machinery.

The point of these is that a document cannot slip through with something
wrong in it, and that a reader can always tell absent from zero from does
not apply.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from uae_compliance.domain.encoding import business_hash, canonical_bytes
from uae_compliance.domain.findings import Severity, Stage
from uae_compliance.domain.schema import (
	CODE_EMPTY,
	CODE_MISSING,
	CODE_NOT_APPLICABLE,
	CODE_SCALE,
	CODE_SHAPE,
	CODE_TYPE,
	CODE_UNKNOWN,
	CODE_VALUE,
	NOT_APPLICABLE,
	Field,
	Kind,
	Schema,
	SchemaError,
	check,
)

MONEY = Field(Kind.DECIMAL, required=True, scale=2)

LINE = Field(
	Kind.OBJECT,
	fields={
		"id": Field(Kind.TEXT, required=True),
		"net": MONEY,
		"quantity": Field(Kind.DECIMAL, scale=4, signed=True),
	},
)

INVOICE = Schema(
	name="test-invoice",
	version=1,
	fields={
		"number": Field(Kind.TEXT, required=True),
		"issued_on": Field(Kind.DATE, required=True),
		"currency": Field(Kind.CURRENCY, required=True),
		"country": Field(Kind.COUNTRY),
		"type_code": Field(Kind.CODE, allowed=("380", "381")),
		"is_credit": Field(Kind.BOOLEAN),
		"seller_id": Field(Kind.IDENTIFIER),
		"total": MONEY,
		"due_on": Field(Kind.DATE, may_be_not_applicable=True),
		"lines": Field(Kind.ARRAY, of=LINE),
	},
)


def good():
	return {
		"number": "INV-1",
		"issued_on": "2026-09-17",
		"currency": "AED",
		"total": Decimal("189.00"),
		"lines": [{"id": "1", "net": Decimal("180.00")}],
	}


def codes(findings):
	return sorted(f.code for f in findings)


def paths(findings):
	return sorted(f.path for f in findings)


class BuildingASchema(unittest.TestCase):
	def test_a_decimal_must_state_its_scale(self):
		with self.assertRaises(SchemaError):
			Field(Kind.DECIMAL)

	def test_only_a_decimal_has_a_scale(self):
		with self.assertRaises(SchemaError):
			Field(Kind.TEXT, scale=2)

	def test_a_code_must_list_what_is_allowed(self):
		with self.assertRaises(SchemaError):
			Field(Kind.CODE)

	def test_an_object_must_list_its_fields(self):
		with self.assertRaises(SchemaError):
			Field(Kind.OBJECT)

	def test_an_array_must_say_what_it_holds(self):
		with self.assertRaises(SchemaError):
			Field(Kind.ARRAY)

	def test_an_extension_cannot_reuse_a_core_name(self):
		with self.assertRaises(SchemaError):
			Schema(
				name="x",
				version=1,
				fields={"a": Field(Kind.TEXT)},
				extensions={"a": Field(Kind.TEXT)},
			)


class AGoodDocument(unittest.TestCase):
	def test_passes_with_nothing_reported(self):
		self.assertEqual(check(good(), INVOICE), [])

	def test_optional_fields_may_be_left_out(self):
		document = good()
		self.assertNotIn("country", document)
		self.assertEqual(check(document, INVOICE), [])

	def test_an_extension_field_is_accepted_when_declared(self):
		schema = Schema(
			name="test-invoice",
			version=1,
			fields=INVOICE.fields,
			extensions={"local_note": Field(Kind.TEXT)},
		)
		document = good() | {"local_note": "for the branch"}
		self.assertEqual(check(document, schema), [])


class UnknownFields(unittest.TestCase):
	def test_an_unknown_field_is_refused_rather_than_ignored(self):
		found = check(good() | {"surprise": "x"}, INVOICE)
		self.assertEqual(codes(found), [CODE_UNKNOWN])
		self.assertEqual(paths(found), ["surprise"])

	def test_an_unknown_field_inside_a_line_is_found(self):
		document = good()
		document["lines"][0]["surprise"] = "x"
		found = check(document, INVOICE)
		self.assertEqual(paths(found), ["lines[0].surprise"])

	def test_an_unknown_part_of_an_identifier_is_found(self):
		document = good() | {"seller_id": {"scheme": "0235", "value": "1", "extra": "x"}}
		found = check(document, INVOICE)
		self.assertEqual(codes(found), [CODE_UNKNOWN])


class RequiredValues(unittest.TestCase):
	def test_a_missing_required_field_is_reported_with_its_path(self):
		document = good()
		del document["currency"]
		found = check(document, INVOICE)
		self.assertEqual(codes(found), [CODE_MISSING])
		self.assertEqual(paths(found), ["currency"])

	def test_a_missing_required_field_inside_a_line_is_reported(self):
		document = good()
		del document["lines"][0]["net"]
		found = check(document, INVOICE)
		self.assertEqual(paths(found), ["lines[0].net"])

	def test_every_problem_comes_back_in_one_pass(self):
		document = good()
		del document["currency"]
		del document["number"]
		document["surprise"] = "x"
		found = check(document, INVOICE)
		self.assertEqual(len(found), 3)
		self.assertEqual(paths(found), ["currency", "number", "surprise"])


class AbsentZeroAndNotApplicable(unittest.TestCase):
	def test_zero_is_a_real_value_and_passes(self):
		self.assertEqual(check(good() | {"total": Decimal("0.00")}, INVOICE), [])

	def test_a_field_left_out_is_simply_absent(self):
		document = good()
		self.assertNotIn("due_on", document)
		self.assertEqual(check(document, INVOICE), [])

	def test_not_applicable_is_allowed_only_where_the_schema_says_so(self):
		self.assertEqual(check(good() | {"due_on": NOT_APPLICABLE}, INVOICE), [])
		found = check(good() | {"country": NOT_APPLICABLE}, INVOICE)
		self.assertEqual(codes(found), [CODE_NOT_APPLICABLE])

	def test_a_document_marked_not_applicable_can_also_be_stored(self):
		# Accepting a document the encoder then refuses would leave a valid
		# invoice that cannot be hashed or saved.
		document = good() | {"due_on": NOT_APPLICABLE}
		self.assertEqual(check(document, INVOICE), [])
		self.assertIn(b'"due_on":{"not_applicable":true}', canonical_bytes(document))
		self.assertEqual(business_hash(document), business_hash(good() | {"due_on": NOT_APPLICABLE}))

	def test_a_none_is_refused_because_it_reads_three_ways(self):
		found = check(good() | {"country": None}, INVOICE)
		self.assertEqual(codes(found), [CODE_EMPTY])

	def test_blank_text_is_refused(self):
		found = check(good() | {"number": "   "}, INVOICE)
		self.assertEqual(codes(found), [CODE_EMPTY])


class Types(unittest.TestCase):
	def test_a_float_is_not_a_decimal(self):
		found = check(good() | {"total": 189.0}, INVOICE)
		self.assertEqual(codes(found), [CODE_TYPE])

	def test_a_numeric_string_is_not_a_decimal(self):
		found = check(good() | {"total": "189.00"}, INVOICE)
		self.assertEqual(codes(found), [CODE_TYPE])

	def test_a_boolean_is_not_a_decimal(self):
		found = check(good() | {"total": True}, INVOICE)
		self.assertEqual(codes(found), [CODE_TYPE])

	def test_a_string_is_not_a_list(self):
		found = check(good() | {"lines": "one"}, INVOICE)
		self.assertEqual(codes(found), [CODE_TYPE])

	def test_a_boolean_field_takes_only_true_or_false(self):
		self.assertEqual(check(good() | {"is_credit": False}, INVOICE), [])
		found = check(good() | {"is_credit": "no"}, INVOICE)
		self.assertEqual(codes(found), [CODE_TYPE])


class Shapes(unittest.TestCase):
	def test_a_date_must_look_like_a_date(self):
		self.assertEqual(codes(check(good() | {"issued_on": "17-09-2026"}, INVOICE)), [CODE_SHAPE])
		self.assertEqual(check(good() | {"issued_on": "2026-09-17"}, INVOICE), [])

	def test_a_currency_is_three_capitals(self):
		self.assertEqual(codes(check(good() | {"currency": "aed"}, INVOICE)), [CODE_SHAPE])
		self.assertEqual(codes(check(good() | {"currency": "AEDX"}, INVOICE)), [CODE_SHAPE])

	def test_a_country_is_two_capitals(self):
		self.assertEqual(codes(check(good() | {"country": "UAE"}, INVOICE)), [CODE_SHAPE])
		self.assertEqual(check(good() | {"country": "AE"}, INVOICE), [])

	def test_an_identifier_needs_both_halves(self):
		found = check(good() | {"seller_id": {"scheme": "0235"}}, INVOICE)
		self.assertEqual(codes(found), [CODE_MISSING])
		self.assertEqual(paths(found), ["seller_id.value"])

	def test_an_identifier_is_not_a_plain_string(self):
		found = check(good() | {"seller_id": "0235:1"}, INVOICE)
		self.assertEqual(codes(found), [CODE_TYPE])


class DecimalScale(unittest.TestCase):
	def test_more_places_than_declared_are_refused_rather_than_rounded(self):
		found = check(good() | {"total": Decimal("189.005")}, INVOICE)
		self.assertEqual(codes(found), [CODE_SCALE])

	def test_fewer_places_are_fine(self):
		self.assertEqual(check(good() | {"total": Decimal("189.0")}, INVOICE), [])

	def test_a_wider_scale_is_allowed_where_declared(self):
		document = good()
		document["lines"][0]["quantity"] = Decimal("1.2345")
		self.assertEqual(check(document, INVOICE), [])

	def test_the_refusal_says_how_many_places_were_seen(self):
		found = check(good() | {"total": Decimal("189.005")}, INVOICE)
		self.assertEqual(found[0].params["places"], "3")
		self.assertEqual(found[0].params["allowed"], "2")


class Values(unittest.TestCase):
	def test_a_code_outside_the_list_is_refused(self):
		found = check(good() | {"type_code": "999"}, INVOICE)
		self.assertEqual(codes(found), [CODE_VALUE])
		self.assertEqual(check(good() | {"type_code": "380"}, INVOICE), [])

	def test_an_unsigned_field_refuses_a_negative(self):
		schema = Schema(
			name="x",
			version=1,
			fields={"qty": Field(Kind.DECIMAL, scale=2, signed=False)},
		)
		self.assertEqual(codes(check({"qty": Decimal("-1.00")}, schema)), [CODE_VALUE])
		self.assertEqual(check({"qty": Decimal("1.00")}, schema), [])

	def test_a_signed_field_accepts_a_negative(self):
		document = good()
		document["lines"][0]["quantity"] = Decimal("-2.0000")
		self.assertEqual(check(document, INVOICE), [])


class FindingsProduced(unittest.TestCase):
	def test_each_problem_arrives_as_a_canonical_stage_error_with_a_repair(self):
		found = check({"surprise": "x"}, INVOICE)
		self.assertTrue(found)
		for item in found:
			self.assertIs(item.stage, Stage.CANONICAL)
			self.assertIs(item.severity, Severity.ERROR)
			self.assertTrue(item.repair)
			self.assertTrue(item.path)

	def test_a_document_that_is_not_a_set_of_fields_is_reported(self):
		found = check(["not", "a", "document"], INVOICE)
		self.assertEqual(codes(found), [CODE_TYPE])


if __name__ == "__main__":
	unittest.main(verbosity=2)
