"""Validate the vendored PINT AE Billing 1.0.4 examples.

Each example is parsed with a hardened lxml parser, checked against the
UBL 2.1 XSD, then run through both official Schematron layers using the
compiled XSLT 2.0 stylesheets on saxonche. Plain Python, no frappe.

Usage:
  validate_examples.py                positive run over every example
  validate_examples.py --negative     altered copies must fail the expected rule
  validate_examples.py --determinism  same input twice gives the same findings
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from importlib import metadata
from pathlib import Path

import saxonche
from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[2]
PINT_ROOT = REPO_ROOT / "uae_compliance" / "standards" / "pint_ae" / "1.0.4"
XSD_ROOT = REPO_ROOT / "uae_compliance" / "standards" / "ubl" / "2.1" / "xsd" / "maindoc"

# Transaction folder -> expected root element local name.
TRANSACTIONS = {"trn-invoice": "Invoice", "trn-creditnote": "CreditNote"}
XSD_BY_ROOT = {"Invoice": "UBL-Invoice-2.1.xsd", "CreditNote": "UBL-CreditNote-2.1.xsd"}
# Shared PINT layer first, then the AE aligned layer.
STYLESHEETS = ("PINT-UBL-validation-preprocessed.xslt", "PINT-jurisdiction-aligned-rules.xslt")

# Defects in the published files themselves, recorded one by one so a run stays honest.
# An entry applies only while the file has exactly the recorded content and fails in exactly
# the recorded way. A new release changes the hash, the entry stops applying, and the run
# fails until someone reviews it. An entry whose file now passes also fails the run, so a
# fixed defect cannot sit here unnoticed. Nothing here relaxes a rule for our own output.
KNOWN_UPSTREAM_DEFECTS = {
	("trn-creditnote", "Volume-discount-credit-note.xml"): {
		"sha256": "2da27c48b45605aba947fc09e6f7314ed4caebf6b247b1dedf6961c4979f8e1e",
		"xsd_error_contains": "OrderLineReference",
		"decision": "D008",
		"note": "cac:OrderLineReference follows cac:DiscrepancyResponse inside cac:CreditNoteLine; "
		"UBL 2.1 CreditNoteLineType requires the opposite order. Both Schematron layers pass.",
	},
}

BASE_EXAMPLE = PINT_ROOT / "trn-invoice" / "example" / "Standard tax invoice.xml"
EXTENSIVE_EXAMPLE = PINT_ROOT / "trn-invoice" / "example" / "Standard.invoice.-.Extensive.xml"

# Upper bound for any document this tool will read. Official examples are far smaller.
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

NS = {
	"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
	"cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}
SVRL = "{http://purl.oclc.org/dsdl/svrl}"


def hardened_parser() -> etree.XMLParser:
	return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)


def parse_hardened(path: Path):
	size = path.stat().st_size
	if size > MAX_DOCUMENT_BYTES:
		raise ValueError(f"{path.name}: {size} bytes exceeds the {MAX_DOCUMENT_BYTES} byte limit")
	tree = etree.parse(str(path), hardened_parser())
	# Saxon's own parser expands external entities, so nothing with a DOCTYPE may reach it.
	if tree.docinfo.doctype:
		raise ValueError(f"{path.name}: DOCTYPE is not allowed")
	return tree


@dataclass(frozen=True)
class FailedAssert:
	layer: str
	id: str
	flag: str
	location: str
	text: str


@dataclass
class Result:
	path: Path
	root_name: str
	xsd_ok: bool
	xsd_errors: list[str]
	failed: list[FailedAssert]
	svrl: dict[str, str]

	@property
	def fatal(self) -> list[FailedAssert]:
		# Anything that is not explicitly a warning counts as fatal.
		return [f for f in self.failed if f.flag != "warning"]

	@property
	def warnings(self) -> list[FailedAssert]:
		return [f for f in self.failed if f.flag == "warning"]

	def ids(self, items: list[FailedAssert]) -> list[str]:
		return sorted({f.id for f in items})


class Validator:
	"""Compiles each schema and stylesheet once and reuses it for every document."""

	def __init__(self, proc: saxonche.PySaxonProcessor):
		self.proc = proc
		self.xslt = proc.new_xslt30_processor()
		self._schemas: dict[str, etree.XMLSchema] = {}
		self._executables: dict[tuple[str, str], saxonche.PyXsltExecutable] = {}

	def schema(self, root_name: str) -> etree.XMLSchema:
		if root_name not in self._schemas:
			xsd_name = XSD_BY_ROOT.get(root_name)
			if xsd_name is None:
				raise ValueError(f"no XSD for root element {root_name}")
			xsd_tree = etree.parse(str(XSD_ROOT / xsd_name), hardened_parser())
			self._schemas[root_name] = etree.XMLSchema(xsd_tree)
		return self._schemas[root_name]

	def executable(self, transaction: str, stylesheet: str) -> saxonche.PyXsltExecutable:
		key = (transaction, stylesheet)
		if key not in self._executables:
			path = PINT_ROOT / transaction / "schematron" / stylesheet
			self._executables[key] = self.xslt.compile_stylesheet(stylesheet_file=str(path))
		return self._executables[key]

	def validate(self, path: Path, transaction: str) -> Result:
		tree = parse_hardened(path)
		root_name = etree.QName(tree.getroot()).localname
		schema = self.schema(root_name)
		xsd_ok = schema.validate(tree)
		xsd_errors = [f"line {e.line}: {e.message}" for e in schema.error_log]

		# Saxon receives the bytes lxml accepted, not the file on disk.
		data = etree.tostring(tree, encoding="UTF-8", xml_declaration=True).decode("utf-8")
		node = self.proc.parse_xml(xml_text=data)

		failed: list[FailedAssert] = []
		svrl: dict[str, str] = {}
		for stylesheet in STYLESHEETS:
			output = self.executable(transaction, stylesheet).transform_to_string(xdm_node=node)
			svrl[stylesheet] = output
			report = etree.fromstring(output.encode("utf-8"), hardened_parser())
			for item in report.iter(SVRL + "failed-assert"):
				text = " ".join("".join(item.itertext()).split())
				failed.append(
					FailedAssert(
						layer=stylesheet,
						id=item.get("id", ""),
						flag=item.get("flag", ""),
						location=item.get("location", ""),
						text=text,
					)
				)
		return Result(path, root_name, xsd_ok, xsd_errors, failed, svrl)


def known_defect(transaction: str, path: Path, result: "Result") -> tuple[bool, str]:
	"""Say whether this failure is the recorded upstream defect, and why not when it is not."""
	entry = KNOWN_UPSTREAM_DEFECTS.get((transaction, path.name))
	if entry is None:
		return False, ""
	actual = hashlib.sha256(path.read_bytes()).hexdigest()
	if actual != entry["sha256"]:
		return False, f"file changed since the defect was recorded (sha256 {actual})"
	if result.fatal:
		return False, "the file now fails a Schematron rule, which the record does not cover"
	if result.xsd_ok:
		return False, "the file now passes; remove the entry and its decision"
	if not any(entry["xsd_error_contains"] in err for err in result.xsd_errors):
		return False, "the schema error is not the recorded one"
	return True, entry["decision"]


def run_positive(validator: Validator) -> int:
	count = 0
	failures = 0
	known = 0
	seen_defects = set()
	for transaction, expected_root in TRANSACTIONS.items():
		for path in sorted((PINT_ROOT / transaction / "example").glob("*.xml")):
			count += 1
			result = validator.validate(path, transaction)
			fatal_ids = result.ids(result.fatal)
			warning_ids = result.ids(result.warnings)
			line = (
				f"{transaction}/{path.name}: xsd={'ok' if result.xsd_ok else 'FAIL'} "
				f"fatal={len(result.fatal)} warning={len(result.warnings)}"
			)
			if fatal_ids:
				line += " fatal_ids=" + ",".join(fatal_ids)
			if warning_ids:
				line += " warning_ids=" + ",".join(warning_ids)
			bad = not result.xsd_ok or bool(result.fatal) or result.root_name != expected_root
			if result.root_name != expected_root:
				line += f" root={result.root_name} expected={expected_root}"
			excused = False
			if bad:
				excused, why = known_defect(transaction, path, result)
				if excused:
					seen_defects.add((transaction, path.name))
					line += f" KNOWN UPSTREAM DEFECT ({why})"
				elif why:
					line += f" recorded defect no longer applies: {why}"
			print(line)
			for err in result.xsd_errors:
				print(f"  xsd: {err}")
			for item in result.fatal:
				print(f"  {item.id} [{item.layer}] {item.text}")
			if bad and not excused:
				failures += 1
			elif excused:
				known += 1
	stale = sorted(set(KNOWN_UPSTREAM_DEFECTS) - seen_defects)
	for transaction, name in stale:
		print(f"{transaction}/{name}: recorded as an upstream defect but did not fail that way")
		failures += 1
	print(
		f"positive: {count} examples, {count - failures - known} passed, "
		f"{failures} failed, {known} known upstream defects"
	)
	return 1 if failures else 0


def _one(root, xpath: str):
	nodes = root.xpath(xpath, namespaces=NS)
	if not nodes:
		raise ValueError(f"mutation target not found: {xpath}")
	return nodes[0]


def mutate_remove_root_id(root) -> None:
	node = _one(root, "cbc:ID")
	node.getparent().remove(node)


def mutate_seller_vat_id_14_digits(root) -> None:
	# Keeps the leading 1 and trailing 03 so only the length condition fails.
	_one(
		root, "cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID"
	).text = "19876543210203"


def mutate_tax_category_m(root) -> None:
	_one(root, "cac:InvoiceLine/cac:Item/cac:ClassifiedTaxCategory/cbc:ID").text = "M"


def mutate_invoice_type_999(root) -> None:
	_one(root, "cbc:InvoiceTypeCode").text = "999"


def mutate_remove_customization_id(root) -> None:
	node = _one(root, "cbc:CustomizationID")
	node.getparent().remove(node)


def mutate_tax_inclusive_plus_001(root) -> None:
	node = _one(root, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount")
	node.text = str(Decimal(node.text) + Decimal("0.01"))


def mutate_currency_zzz(root) -> None:
	# XXX is a valid ISO 4217 code and is present in the ibr-cl-04 list, so ZZZ is used instead.
	_one(root, "cbc:DocumentCurrencyCode").text = "ZZZ"


# (label, expected rule id, mutation). Rule ids were read from the .sch files:
# ibr-002      PINT-UBL-validation-preprocessed.sch line 167  normalize-space(cbc:ID) != ''
# ibr-132-ae   PINT-jurisdiction-aligned-rules.sch line 213   TRN is 15 digits, starts 1, ends 03
# ibr-139-ae   PINT-jurisdiction-aligned-rules.sch line 236   category code in ' S E O AE Z N '
# ibr-cl-01    PINT-UBL-validation-preprocessed.sch line 345  InvoiceTypeCode in ' 380 480 '
# ibr-001      PINT-UBL-validation-preprocessed.sch line 164  CustomizationID present
# ibr-co-15    PINT-UBL-validation-preprocessed.sch line 200  TaxInclusive = TaxExclusive + TaxAmount
# ibr-cl-04    PINT-UBL-validation-preprocessed.sch line 351  DocumentCurrencyCode in ISO 4217 list
MUTATIONS: tuple[tuple[str, str, Callable], ...] = (
	("a remove root cbc:ID", "ibr-002", mutate_remove_root_id),
	("b seller VAT CompanyID 14 digits", "ibr-132-ae", mutate_seller_vat_id_14_digits),
	("c ClassifiedTaxCategory/cbc:ID = M", "ibr-139-ae", mutate_tax_category_m),
	("d InvoiceTypeCode = 999", "ibr-cl-01", mutate_invoice_type_999),
	("e remove cbc:CustomizationID", "ibr-001", mutate_remove_customization_id),
	("f TaxInclusiveAmount + 0.01", "ibr-co-15", mutate_tax_inclusive_plus_001),
	("g DocumentCurrencyCode = ZZZ", "ibr-cl-04", mutate_currency_zzz),
)


def write_mutation(mutate: Callable, target: Path) -> None:
	tree = parse_hardened(BASE_EXAMPLE)
	mutate(tree.getroot())
	tree.write(str(target), encoding="UTF-8", xml_declaration=True)


def run_negative(validator: Validator) -> int:
	failures = 0
	print(f"base example: {BASE_EXAMPLE.relative_to(REPO_ROOT)}")
	with tempfile.TemporaryDirectory() as tmp:
		for index, (label, expected, mutate) in enumerate(MUTATIONS):
			target = Path(tmp) / f"mutation-{index}.xml"
			write_mutation(mutate, target)
			result = validator.validate(target, "trn-invoice")
			fired = result.ids(result.failed)
			ok = expected in fired
			print(
				f"{label}: expected={expected} xsd={'ok' if result.xsd_ok else 'FAIL'} "
				f"fired={','.join(fired) or '-'} {'PASS' if ok else 'FAIL'}"
			)
			if not ok:
				failures += 1
	print(f"negative: {len(MUTATIONS)} cases, {len(MUTATIONS) - failures} passed, {failures} failed")
	return 1 if failures else 0


def _signature(result: Result) -> list[tuple[str, str, str, str]]:
	return [(f.layer, f.id, f.location, f.text) for f in result.failed]


def run_determinism(proc: saxonche.PySaxonProcessor) -> int:
	# A fresh Validator so the first run includes schema load and stylesheet compilation.
	validator = Validator(proc)
	name = EXTENSIVE_EXAMPLE.name

	start = time.perf_counter()
	first = validator.validate(EXTENSIVE_EXAMPLE, "trn-invoice")
	cold = time.perf_counter() - start
	start = time.perf_counter()
	second = validator.validate(EXTENSIVE_EXAMPLE, "trn-invoice")
	warm = time.perf_counter() - start

	same = _signature(first) == _signature(second)
	print(f"determinism {name}: {'identical' if same else 'different'} (failed asserts: {len(first.failed)})")
	print(f"svrl text {name}: {'identical' if first.svrl == second.svrl else 'different'}")
	print(f"timing {name}: cold={cold:.3f}s (includes XSD load and XSLT compile) warm={warm:.3f}s")

	# The positive example has no findings, so also compare a copy that fails several rules.
	label, _expected, mutate = MUTATIONS[5]
	with tempfile.TemporaryDirectory() as tmp:
		target = Path(tmp) / "mutation.xml"
		write_mutation(mutate, target)
		first_neg = validator.validate(target, "trn-invoice")
		second_neg = validator.validate(target, "trn-invoice")
	same_neg = _signature(first_neg) == _signature(second_neg)
	print(
		f"determinism mutation {label}: {'identical' if same_neg else 'different'} "
		f"(failed asserts: {len(first_neg.failed)}, ids: {','.join(first_neg.ids(first_neg.failed))})"
	)
	return 0 if same and same_neg else 1


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description="Validate the vendored PINT AE 1.0.4 examples.")
	parser.add_argument("--negative", action="store_true", help="run the altered-copy checks")
	parser.add_argument("--determinism", action="store_true", help="run the repeat-validation check")
	args = parser.parse_args(argv)

	with saxonche.PySaxonProcessor(license=False) as proc:
		print(
			f"runtime: python {platform.python_version()} lxml {metadata.version('lxml')} "
			f"saxonche {metadata.version('saxonche')} ({proc.version})"
		)
		status = 0
		if args.negative:
			status |= run_negative(Validator(proc))
		if args.determinism:
			status |= run_determinism(proc)
		if not (args.negative or args.determinism):
			status |= run_positive(Validator(proc))
		return status


if __name__ == "__main__":
	raise SystemExit(main())
