"""Read XML without letting the document decide what else gets read.

An XML file can ask the parser to pull in other files or fetch a URL. On a
document arriving from outside that is a way to read a server's private files
or make it call somewhere it should not.

So every document goes through one hardened parse here first. It refuses a
doctype outright, which is what carries those instructions, and it refuses
anything oversized. Only then do the bytes go anywhere else. In particular
the rule engine has its own parser that does expand entities, so it never
sees a file from disk and only ever gets what came back out of this one.
"""

from __future__ import annotations

from lxml import etree

# Far larger than any real invoice, small enough that nothing can exhaust
# memory by handing us a document.
MAX_BYTES = 10 * 1024 * 1024


class UnsafeDocument(ValueError):
	"""The document cannot be read safely, so it is not read at all."""


def parser() -> etree.XMLParser:
	return etree.XMLParser(
		resolve_entities=False,
		no_network=True,
		load_dtd=False,
		huge_tree=False,
	)


def parse_bytes(data: bytes):
	"""Parse bytes, refusing anything that could reach outside the document."""
	if not isinstance(data, (bytes, bytearray)):
		raise UnsafeDocument("expected bytes")
	if len(data) > MAX_BYTES:
		raise UnsafeDocument(f"{len(data)} bytes is larger than the {MAX_BYTES} byte limit")
	try:
		tree = etree.fromstring(bytes(data), parser()).getroottree()
	except etree.XMLSyntaxError as exc:
		raise UnsafeDocument(f"this is not well formed XML: {exc}") from exc
	if tree.docinfo.doctype:
		raise UnsafeDocument("a document type declaration is not allowed")
	return tree


def parse_local(path) -> object:
	"""Parse one of our own pinned files, from its path.

	The schema is split across files that refer to each other by relative
	path, so it has to be read from disk rather than from bytes, or those
	references have nothing to resolve against. That is safe here and only
	here: these files ship with the app and their checksums are recorded, so
	they are not something a document brought with it. The parser still
	refuses to reach the network.
	"""
	try:
		return etree.parse(str(path), parser())
	except etree.XMLSyntaxError as exc:
		raise UnsafeDocument(f"{path}: {exc}") from exc


def reserialize(tree) -> str:
	"""The document as text, from what the hardened parse accepted.

	The engine that runs the rules gets this rather than the original bytes,
	so whatever its own parser would have done with a doctype never arises.
	"""
	return etree.tostring(tree, encoding="UTF-8", xml_declaration=True).decode("utf-8")


def root_name(tree) -> str:
	return etree.QName(tree.getroot()).localname
