"""Checks on the known upstream defect guard in validate_examples.

The guard lets one published example fail the UBL schema without failing the run.
These checks prove it stays narrow: it applies only to the exact recorded file
failing in the exact recorded way, and it never hides one of our own problems.

Run: python scripts/standards/test_validate_examples.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_examples import (
	KNOWN_UPSTREAM_DEFECTS,
	PINT_ROOT,
	FailedAssert,
	Result,
	known_defect,
)

ENTRY_KEY = ("trn-creditnote", "Volume-discount-credit-note.xml")
XSD_ERROR = "line 185: Element '{...}OrderLineReference': This element is not expected."


def result_for(path: Path, xsd_ok: bool, xsd_errors: list[str], failed=None) -> Result:
	return Result(
		path=path,
		root_name="CreditNote",
		xsd_ok=xsd_ok,
		xsd_errors=xsd_errors,
		failed=failed or [],
		svrl={},
	)


class KnownDefectGuard(unittest.TestCase):
	def setUp(self):
		transaction, name = ENTRY_KEY
		self.path = PINT_ROOT / transaction / "example" / name
		self.transaction = transaction

	def test_recorded_file_failing_the_recorded_way_is_excused(self):
		excused, why = known_defect(self.transaction, self.path, result_for(self.path, False, [XSD_ERROR]))
		self.assertTrue(excused)
		self.assertEqual(why, "D008")

	def test_the_recorded_error_plus_an_unrelated_one_is_not_excused(self):
		# The defect is one known failure. A second failure alongside it is a
		# new problem and must not ride along on the record.
		excused, why = known_defect(
			self.transaction,
			self.path,
			result_for(self.path, False, [XSD_ERROR, "line 999: something else entirely"]),
		)
		self.assertFalse(excused)
		self.assertIn("does not cover", why)

	def test_more_errors_than_recorded_is_not_excused(self):
		excused, why = known_defect(
			self.transaction,
			self.path,
			result_for(self.path, False, [XSD_ERROR, XSD_ERROR]),
		)
		self.assertFalse(excused)
		self.assertIn("schema errors", why)

	def test_a_different_schema_error_is_not_excused(self):
		excused, why = known_defect(
			self.transaction,
			self.path,
			result_for(self.path, False, ["line 12: Element 'cbc:ID': something else"]),
		)
		self.assertFalse(excused)
		self.assertIn("does not cover", why)

	def test_a_schematron_failure_is_never_excused(self):
		failed = [FailedAssert("aligned", "ibr-132-ae", "fatal", "/CreditNote", "bad identifier")]
		excused, why = known_defect(
			self.transaction, self.path, result_for(self.path, False, [XSD_ERROR], failed)
		)
		self.assertFalse(excused)
		self.assertIn("Schematron", why)

	def test_a_file_that_now_passes_fails_the_run(self):
		excused, why = known_defect(self.transaction, self.path, result_for(self.path, True, []))
		self.assertFalse(excused)
		self.assertIn("remove the entry", why)

	def test_changed_file_content_drops_the_excuse(self):
		# A new release keeps the name and changes the bytes. The entry must stop applying.
		other = PINT_ROOT / "trn-creditnote" / "example" / "Standard tax credit Note.xml"
		with tempfile.TemporaryDirectory() as folder:
			stand_in = Path(folder) / ENTRY_KEY[1]
			shutil.copyfile(other, stand_in)
			excused, why = known_defect(self.transaction, stand_in, result_for(stand_in, False, [XSD_ERROR]))
		self.assertFalse(excused)
		self.assertIn("file changed", why)

	def test_a_file_with_no_entry_is_never_excused(self):
		other = PINT_ROOT / "trn-invoice" / "example" / "Standard tax invoice.xml"
		excused, why = known_defect("trn-invoice", other, result_for(other, False, [XSD_ERROR]))
		self.assertFalse(excused)
		self.assertEqual(why, "")

	def test_every_recorded_entry_names_a_decision_and_a_real_file(self):
		self.assertTrue(KNOWN_UPSTREAM_DEFECTS)
		for (transaction, name), entry in KNOWN_UPSTREAM_DEFECTS.items():
			path = PINT_ROOT / transaction / "example" / name
			self.assertTrue(path.exists(), f"{transaction}/{name} is recorded but missing")
			self.assertRegex(entry["decision"], r"^D\d{3}$")
			self.assertEqual(len(entry["sha256"]), 64)
			self.assertTrue(entry["xsd_errors_contain"])
			self.assertEqual(entry["xsd_error_count"], len(entry["xsd_errors_contain"]))
			self.assertTrue(entry["note"])


if __name__ == "__main__":
	unittest.main(verbosity=2)
