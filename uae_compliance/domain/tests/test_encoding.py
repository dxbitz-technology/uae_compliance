"""Checks on the deterministic encoding.

A submission freezes the hashes this module produces, so these checks are
about one thing: the same meaning always gives the same bytes, and anything
that cannot be written stably is refused rather than guessed at.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from uae_compliance.domain.encoding import (
	NOT_APPLICABLE,
	EncodingError,
	business_hash,
	canonical_bytes,
	canonical_decimal,
	payload_hash,
	read_not_applicable,
	sha256_hex,
	without_paths,
)


class CanonicalDecimal(unittest.TestCase):
	def test_plain_string_without_exponent(self):
		self.assertEqual(canonical_decimal(Decimal("180.00")), "180.00")
		self.assertEqual(canonical_decimal(Decimal("0.05")), "0.05")
		self.assertEqual(canonical_decimal(Decimal("-9.50")), "-9.50")

	def test_scientific_input_is_written_in_full(self):
		self.assertEqual(canonical_decimal(Decimal("1E+3")), "1000")
		self.assertEqual(canonical_decimal(Decimal("3.6725E-2")), "0.036725")

	def test_scale_is_kept_because_the_caller_owns_it(self):
		self.assertNotEqual(canonical_decimal(Decimal("180")), canonical_decimal(Decimal("180.00")))

	def test_negative_zero_loses_its_sign(self):
		self.assertEqual(canonical_decimal(Decimal("-0.00")), "0.00")
		self.assertEqual(canonical_decimal(Decimal("-0")), "0")

	def test_not_a_number_and_infinity_are_refused(self):
		for bad in ("NaN", "Infinity", "-Infinity"):
			with self.assertRaises(EncodingError):
				canonical_decimal(Decimal(bad))

	def test_a_float_is_not_a_decimal(self):
		with self.assertRaises(EncodingError):
			canonical_decimal(1.5)


class CanonicalBytes(unittest.TestCase):
	def test_key_order_does_not_change_the_bytes(self):
		one = {"b": "2", "a": "1", "c": {"z": "26", "y": "25"}}
		two = {"c": {"y": "25", "z": "26"}, "a": "1", "b": "2"}
		self.assertEqual(canonical_bytes(one), canonical_bytes(two))

	def test_repeating_the_call_gives_the_same_bytes(self):
		doc = {"amount": Decimal("189.00"), "lines": [{"id": "1"}, {"id": "2"}]}
		self.assertEqual(canonical_bytes(doc), canonical_bytes(doc))

	def test_array_order_is_meaning_and_is_kept(self):
		first = {"lines": [{"id": "1"}, {"id": "2"}]}
		second = {"lines": [{"id": "2"}, {"id": "1"}]}
		self.assertNotEqual(canonical_bytes(first), canonical_bytes(second))

	def test_output_is_utf8_without_escapes_or_spaces(self):
		raw = canonical_bytes({"name": "شركة", "n": 1})
		self.assertEqual(raw.decode("utf-8"), '{"n":1,"name":"شركة"}')

	def test_a_missing_value_is_left_out(self):
		self.assertEqual(canonical_bytes({"a": "1", "b": None}), b'{"a":"1"}')

	def test_a_missing_value_differs_from_an_empty_one(self):
		absent = canonical_bytes({"reason": None})
		empty = canonical_bytes({"reason": ""})
		self.assertNotEqual(absent, empty)

	def test_zero_is_kept_and_is_not_treated_as_missing(self):
		self.assertEqual(canonical_bytes({"tax": Decimal("0.00")}), b'{"tax":"0.00"}')

	def test_a_decimal_is_written_as_a_string(self):
		self.assertEqual(canonical_bytes({"tax": Decimal("9.00")}), b'{"tax":"9.00"}')

	def test_a_float_anywhere_is_refused(self):
		for doc in ({"rate": 0.05}, {"lines": [{"rate": 0.05}]}, {"a": {"b": [1, 2.5]}}):
			with self.assertRaises(EncodingError) as caught:
				canonical_bytes(doc)
			self.assertIn("float", str(caught.exception))

	def test_the_refusal_names_where_the_float_was(self):
		with self.assertRaises(EncodingError) as caught:
			canonical_bytes({"lines": [{"ok": "1"}, {"rate": 0.05}]})
		self.assertIn("lines[1].rate", str(caught.exception))

	def test_a_set_is_refused_because_it_has_no_order(self):
		with self.assertRaises(EncodingError):
			canonical_bytes({"codes": {"a", "b"}})

	def test_raw_bytes_are_refused(self):
		with self.assertRaises(EncodingError):
			canonical_bytes({"blob": b"\x00\x01"})

	def test_a_non_string_key_is_refused(self):
		with self.assertRaises(EncodingError):
			canonical_bytes({1: "one"})

	def test_the_document_itself_must_be_a_mapping(self):
		with self.assertRaises(EncodingError):
			canonical_bytes([{"a": "1"}])

	def test_not_applicable_has_a_written_form(self):
		self.assertEqual(
			canonical_bytes({"due_date": NOT_APPLICABLE}), b'{"due_date":{"not_applicable":true}}'
		)

	def test_not_applicable_is_none_of_the_other_three(self):
		not_applicable = canonical_bytes({"due_date": NOT_APPLICABLE})
		absent = canonical_bytes({})
		empty = canonical_bytes({"due_date": ""})
		zero = canonical_bytes({"due_date": Decimal("0")})
		self.assertEqual(len({not_applicable, absent, empty, zero}), 4)

	def test_not_applicable_reads_back(self):
		written = {"not_applicable": True}
		self.assertIs(read_not_applicable(written), NOT_APPLICABLE)

	def test_read_back_leaves_an_ordinary_object_alone(self):
		ordinary = {"not_applicable": True, "and": "more"}
		self.assertIs(read_not_applicable(ordinary), ordinary)
		self.assertEqual(read_not_applicable("text"), "text")

	def test_not_applicable_survives_a_hash(self):
		one = {"due_date": NOT_APPLICABLE}
		two = {"due_date": NOT_APPLICABLE}
		self.assertEqual(business_hash(one), business_hash(two))
		self.assertNotEqual(business_hash(one), business_hash({"due_date": ""}))

	def test_booleans_survive_as_booleans(self):
		self.assertEqual(canonical_bytes({"flag": True}), b'{"flag":true}')


class WithoutPaths(unittest.TestCase):
	def test_a_named_path_is_removed(self):
		doc = {"a": "1", "b": {"c": "2", "d": "3"}}
		self.assertEqual(without_paths(doc, ["b.c"]), {"a": "1", "b": {"d": "3"}})

	def test_the_original_is_not_touched(self):
		doc = {"a": "1", "b": {"c": "2"}}
		without_paths(doc, ["b.c"])
		self.assertEqual(doc, {"a": "1", "b": {"c": "2"}})

	def test_one_path_covers_the_same_field_in_every_row(self):
		doc = {"lines": [{"id": "1", "note": "x"}, {"id": "2", "note": "y"}]}
		self.assertEqual(without_paths(doc, ["lines.note"]), {"lines": [{"id": "1"}, {"id": "2"}]})

	def test_a_path_that_matches_nothing_is_an_error(self):
		with self.assertRaises(EncodingError) as caught:
			without_paths({"a": "1"}, ["b.c"])
		self.assertIn("b.c", str(caught.exception))

	def test_a_malformed_path_is_an_error(self):
		for bad in ("", ".a", "a.", "a..b"):
			with self.assertRaises(EncodingError):
				without_paths({"a": {"b": "1"}}, [bad])


class Hashes(unittest.TestCase):
	def test_the_business_hash_ignores_only_what_it_was_told_to(self):
		base = {"doc": {"id": "INV-1", "total": Decimal("189.00")}, "checked_at": "2026-09-17T08:00:00Z"}
		later = {"doc": {"id": "INV-1", "total": Decimal("189.00")}, "checked_at": "2026-09-18T09:30:00Z"}
		volatile = ["checked_at"]
		self.assertEqual(business_hash(base, volatile), business_hash(later, volatile))

	def test_a_real_change_still_changes_the_business_hash(self):
		base = {"doc": {"id": "INV-1", "total": Decimal("189.00")}, "checked_at": "t1"}
		changed = {"doc": {"id": "INV-1", "total": Decimal("189.01")}, "checked_at": "t1"}
		volatile = ["checked_at"]
		self.assertNotEqual(business_hash(base, volatile), business_hash(changed, volatile))

	def test_a_payment_after_submission_does_not_change_the_business_hash(self):
		before = {"doc": {"id": "INV-1"}, "collection": {"outstanding": Decimal("189.00")}}
		after = {"doc": {"id": "INV-1"}, "collection": {"outstanding": Decimal("0.00")}}
		volatile = ["collection.outstanding"]
		self.assertEqual(business_hash(before, volatile), business_hash(after, volatile))

	def test_with_no_volatile_paths_it_hashes_the_whole_document(self):
		doc = {"a": "1"}
		self.assertEqual(business_hash(doc), sha256_hex(canonical_bytes(doc)))

	def test_the_payload_hash_covers_the_exact_bytes(self):
		raw = b'<?xml version="1.0"?><Invoice/>'
		self.assertEqual(payload_hash(raw), sha256_hex(raw))
		self.assertNotEqual(payload_hash(raw), payload_hash(raw + b"\n"))

	def test_the_payload_hash_refuses_text(self):
		with self.assertRaises(EncodingError):
			payload_hash("<Invoice/>")

	def test_a_known_document_keeps_its_hash(self):
		# If this value ever changes, the encoding contract changed with it.
		# Raise ENCODING_VERSION and treat every stored hash as belonging to
		# the older rule, rather than editing this number to match.
		doc = {"id": "INV-1", "lines": [{"n": 1, "net": Decimal("180.00")}], "tax": Decimal("9.00")}
		self.assertEqual(
			canonical_bytes(doc), b'{"id":"INV-1","lines":[{"n":1,"net":"180.00"}],"tax":"9.00"}'
		)
		self.assertEqual(
			sha256_hex(canonical_bytes(doc)),
			"c1e688b3139b81374c74e392536d6e45e6e98bc034a91464ad8804e3674861b3",
		)


if __name__ == "__main__":
	unittest.main(verbosity=2)
