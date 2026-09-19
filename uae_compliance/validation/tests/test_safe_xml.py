"""What a document somebody else wrote is allowed to make us do.

This is the one place a file we did not write reaches a parser, so these are
the checks that matter most in the app. Each one is an attack somebody would
actually try: read a file off the server, make the server fetch a URL, fill
its memory, or make one invoice cost us a hundred thousand queries.
"""

from __future__ import annotations

import unittest

from uae_compliance.validation import reader
from uae_compliance.validation.safe_xml import (
	MAX_BYTES,
	UnsafeDocument,
	parse_bytes,
	reserialize,
	root_name,
)

CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"


def an_invoice(lines: str = "", credit_note: bool = False) -> bytes:
	kind = "CreditNote" if credit_note else "Invoice"
	return f"""<?xml version="1.0" encoding="UTF-8"?>
<{kind} xmlns="urn:oasis:names:specification:ubl:schema:xsd:{kind}-2"
	xmlns:cbc="{CBC}" xmlns:cac="{CAC}">
	<cbc:ID>THEIRS-1</cbc:ID>
	<cbc:IssueDate>2026-01-31</cbc:IssueDate>
	<cbc:DocumentCurrencyCode>AED</cbc:DocumentCurrencyCode>
	<cac:AccountingSupplierParty><cac:Party>
		<cbc:EndpointID>0235:100000000000003</cbc:EndpointID>
		<cac:PartyLegalEntity><cbc:RegistrationName>Their Company</cbc:RegistrationName></cac:PartyLegalEntity>
	</cac:Party></cac:AccountingSupplierParty>
	{lines}
</{kind}>""".encode()


def a_line(number: int, credit_note: bool = False) -> str:
	kind = "CreditNote" if credit_note else "Invoice"
	quantity = "CreditedQuantity" if credit_note else "InvoicedQuantity"
	return (
		f"<cac:{kind}Line><cbc:ID>{number}</cbc:ID>"
		f'<cbc:{quantity} unitCode="C62">1</cbc:{quantity}>'
		f"<cac:Item><cbc:Name>Thing</cbc:Name></cac:Item>"
		f"</cac:{kind}Line>"
	)


class WhatTheParserRefuses(unittest.TestCase):
	def test_a_document_type_declaration_is_refused_outright(self):
		with self.assertRaises(UnsafeDocument):
			parse_bytes(b'<?xml version="1.0"?><!DOCTYPE r><r/>')

	def test_an_external_entity_never_reads_a_file_off_the_server(self):
		attack = (
			b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY secret SYSTEM "file:///etc/passwd">]><r>&secret;</r>'
		)
		with self.assertRaises(UnsafeDocument):
			parse_bytes(attack)

	def test_an_external_entity_never_makes_the_server_fetch_a_url(self):
		attack = (
			b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY out SYSTEM "http://127.0.0.1:1/x">]><r>&out;</r>'
		)
		with self.assertRaises(UnsafeDocument):
			parse_bytes(attack)

	def test_a_nested_entity_cannot_expand_into_memory(self):
		attack = b"""<?xml version="1.0"?><!DOCTYPE lolz [
<!ENTITY lol "lol">
<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
<!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]><lolz>&lol3;</lolz>"""
		with self.assertRaises(UnsafeDocument):
			parse_bytes(attack)

	def test_an_entity_nobody_declared_is_not_quietly_dropped(self):
		with self.assertRaises(UnsafeDocument):
			parse_bytes(b'<?xml version="1.0"?><r>&whatever;</r>')

	def test_a_document_past_the_size_limit_is_refused_before_it_is_parsed(self):
		too_big = b"<r>" + b"x" * MAX_BYTES + b"</r>"
		with self.assertRaises(UnsafeDocument) as caught:
			parse_bytes(too_big)
		self.assertIn("larger than", str(caught.exception))

	def test_deep_nesting_is_refused(self):
		body = b"<a>" * 5000 + b"</a>" * 5000
		with self.assertRaises(UnsafeDocument):
			parse_bytes(b"<r>" + body + b"</r>")

	def test_nesting_a_real_invoice_needs_is_still_accepted(self):
		body = b"<a>" * 40 + b"</a>" * 40
		self.assertEqual(root_name(parse_bytes(b"<r>" + body + b"</r>")), "r")

	def test_text_is_not_bytes(self):
		with self.assertRaises(UnsafeDocument):
			parse_bytes('<?xml version="1.0"?><r/>')

	def test_something_that_is_not_xml_at_all(self):
		with self.assertRaises(UnsafeDocument):
			parse_bytes(b"not xml, just a sentence")

	def test_nothing_at_all(self):
		with self.assertRaises(UnsafeDocument):
			parse_bytes(b"")


class WhatComesBackOut(unittest.TestCase):
	def test_what_is_handed_on_carries_no_document_type_declaration(self):
		text = reserialize(parse_bytes(an_invoice()))
		self.assertNotIn("<!DOCTYPE", text)
		self.assertIn("THEIRS-1", text)

	def test_an_ordinary_invoice_still_reads(self):
		found = reader.summarise(an_invoice(a_line(1)))
		self.assertEqual(found["document_number"], "THEIRS-1")
		self.assertEqual(found["supplier_name"], "Their Company")
		self.assertEqual(found["line_count"], 1)
		self.assertFalse(found["is_credit_note"])


class HowMuchWorkOneDocumentMayCause(unittest.TestCase):
	def test_more_lines_than_any_real_invoice_is_refused(self):
		lines = "".join(a_line(n) for n in range(reader.MAX_LINES + 1))
		with self.assertRaises(UnsafeDocument) as caught:
			reader.lines(an_invoice(lines))
		self.assertIn("line limit", str(caught.exception))

	def test_a_credit_note_is_counted_the_same_way(self):
		lines = "".join(a_line(n, credit_note=True) for n in range(reader.MAX_LINES + 1))
		with self.assertRaises(UnsafeDocument):
			reader.lines(an_invoice(lines, credit_note=True))

	def test_an_invoice_with_ordinary_lines_reads_all_of_them(self):
		lines = "".join(a_line(n) for n in range(25))
		found = reader.lines(an_invoice(lines))
		self.assertEqual(len(found), 25)
		self.assertEqual(found[0]["uom_code"], "C62")


if __name__ == "__main__":
	unittest.main()
