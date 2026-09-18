"""Find the official files on disk, and compile them once.

The files are pinned in the repository and never fetched at runtime, so all
this does is locate them and hold the compiled form so a worker does not
rebuild it for every invoice. Compiling the rule layers takes far longer than
checking a document against them.

If anything is missing or will not compile, that is reported as unavailable.
It is never quietly treated as a pass.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STANDARDS_ROOT = PACKAGE_ROOT / "standards"

PINT_VERSION = "1.0.4"
UBL_VERSION = "2.1"

# Which folder and schema each kind of document uses.
TRANSACTIONS = {
	"Invoice": ("trn-invoice", "UBL-Invoice-2.1.xsd"),
	"CreditNote": ("trn-creditnote", "UBL-CreditNote-2.1.xsd"),
}

# The shared layer first, then the jurisdiction layer, as published.
RULE_LAYERS = (
	("Schematron shared", "PINT-UBL-validation-preprocessed.xslt"),
	("Schematron AE", "PINT-jurisdiction-aligned-rules.xslt"),
)


class ArtifactsUnavailable(RuntimeError):
	"""The official files or the engine are not usable, so nothing can be checked."""


@dataclass(frozen=True)
class Paths:
	schema: Path
	rule_layers: tuple[tuple[str, Path], ...]

	def missing(self) -> list[Path]:
		absent = [] if self.schema.is_file() else [self.schema]
		absent += [path for _, path in self.rule_layers if not path.is_file()]
		return absent


def paths_for(root_name: str, *, root: Path | None = None) -> Paths:
	"""Where the files for this kind of document live."""
	if root_name not in TRANSACTIONS:
		raise ArtifactsUnavailable(f"no official rules for a {root_name} document")
	base = root or STANDARDS_ROOT
	folder, schema_name = TRANSACTIONS[root_name]
	return Paths(
		schema=base / "ubl" / UBL_VERSION / "xsd" / "maindoc" / schema_name,
		rule_layers=tuple(
			(label, base / "pint_ae" / PINT_VERSION / folder / "schematron" / name)
			for label, name in RULE_LAYERS
		),
	)


class Compiled:
	"""The compiled schema and rule layers, built once and shared.

	One instance per worker. Building the rule layers is the expensive part,
	so they are kept rather than rebuilt for every invoice.
	"""

	def __init__(self, root: Path | None = None):
		self._root = root
		self._lock = threading.Lock()
		self._schemas: dict[str, object] = {}
		self._layers: dict[str, tuple[tuple[str, object], ...]] = {}
		self._processor = None

	def _engine(self):
		"""The XML engine, started once. Absent or broken means unavailable."""
		if self._processor is None:
			try:
				from saxonche import PySaxonProcessor
			except ImportError as exc:
				raise ArtifactsUnavailable(f"the XML engine is not installed: {exc}") from exc
			self._processor = PySaxonProcessor(license=False)
		return self._processor

	def schema(self, root_name: str):
		with self._lock:
			if root_name not in self._schemas:
				from lxml import etree

				from uae_compliance.validation.safe_xml import parse_local

				path = paths_for(root_name, root=self._root).schema
				if not path.is_file():
					raise ArtifactsUnavailable(f"the schema is missing: {path.name}")
				try:
					self._schemas[root_name] = etree.XMLSchema(parse_local(path))
				except Exception as exc:
					raise ArtifactsUnavailable(f"the schema will not compile: {exc}") from exc
			return self._schemas[root_name]

	def rule_layers(self, root_name: str):
		with self._lock:
			if root_name not in self._layers:
				engine = self._engine()
				compiler = engine.new_xslt30_processor()
				built = []
				for label, path in paths_for(root_name, root=self._root).rule_layers:
					if not path.is_file():
						raise ArtifactsUnavailable(f"a rule layer is missing: {path.name}")
					try:
						built.append((label, compiler.compile_stylesheet(stylesheet_file=str(path))))
					except Exception as exc:
						raise ArtifactsUnavailable(f"{label} will not compile: {exc}") from exc
				self._layers[root_name] = tuple(built)
			return self._layers[root_name]

	def parse(self, text: str):
		return self._engine().parse_xml(xml_text=text)


_shared = Compiled()


def shared() -> Compiled:
	"""The instance this process reuses."""
	return _shared
