# B1: P00 standards evidence tooling and lock file

Date: 16-09-2026. Repository: /Users/aslam/frappe-local/loc16/apps/uae_compliance (branch main, local only).
Python: /Users/aslam/frappe-local/loc16/env/bin/python (3.14.5). No bench, site, or core file was touched.

## Files written

- /Users/aslam/frappe-local/loc16/apps/uae_compliance/scripts/standards/validate_examples.py (new)
- /Users/aslam/frappe-local/loc16/apps/uae_compliance/scripts/standards/check_lock.py (new)
- /Users/aslam/frappe-local/loc16/apps/uae_compliance/docs/standards-lock.json (new, 44037 bytes, sha256 43af038a857ede65d27b6b687133e3a40d5456706a42975c1fe886626fc16ab0)

Scratch only (not in the repository): build_lock.py (lock generator, byte deterministic on repeat), schq.py (Schematron rule query helper), positive_run.txt.

`git status --short --untracked-files=all` shows only docs/standards-lock.json, scripts/standards/*.py, and the vendored uae_compliance/standards tree (plus uae_compliance/standards/NOTICES.md written by another agent) as untracked. No tracked file was modified.

## Verified facts

| # | Fact | Evidence | Status |
| --- | --- | --- | --- |
| F1 | All four .sch files declare queryBinding="xslt2" | trn-invoice/schematron/PINT-UBL-validation-preprocessed.sch:1, trn-invoice/schematron/PINT-jurisdiction-aligned-rules.sch:1, trn-creditnote/schematron/PINT-UBL-validation-preprocessed.sch:1, trn-creditnote/schematron/PINT-jurisdiction-aligned-rules.sch:1 (all under uae_compliance/standards/pint_ae/1.0.4) | Verified |
| F2 | All four compiled .xslt files are xsl:stylesheet version="2.0" | same folders, *.xslt:2 (xsl:stylesheet open tag) and *.xslt:17 (version="2.0") | Verified |
| F3 | lxml 6.1.1 bundles libxslt 1.1.43 (XSLT 1.0); unsuitable for F2 | etree.LIBXSLT_VERSION == (1, 1, 43), etree.LIBXML_VERSION == (2, 14, 6) from /Users/aslam/frappe-local/loc16/env/lib/python3.14/site-packages/lxml/etree.cpython-314-darwin.so | Verified |
| F4 | saxonche 13.0.0 reports edition HE, version "SaxonC-HE 13.0 from Saxonica"; wheel tag cp314-cp314-macosx_11_0_arm64 | PySaxonProcessor.edition / .version at runtime; /Users/aslam/frappe-local/loc16/env/lib/python3.14/site-packages/saxonche-13.0.0.dist-info/WHEEL line "Tag: cp314-cp314-macosx_11_0_arm64"; module file site-packages/saxonche.cpython-314-darwin.so | Verified |
| F5 | Saxon-HE license is Mozilla Public License 2.0 | https://www.saxonica.com/license/terms.xml (fetched 16-09-2026) states the open-source Saxon-HE product is offered under MPL 2.0. The wheel METADATA (dist-info/METADATA:25-29) only links to that page and does not name the license itself | Verified (page), METADATA silent |
| F6 | lxml license BSD-3-Clause | site-packages/lxml-6.1.1.dist-info/METADATA "License: BSD-3-Clause" | Verified |
| F7 | PINT AE publication page shows version 1.0.4 dated 29 July 2026 with a resources.zip download | https://docs.peppol.eu/poac/ae/pint-ae/ fetched 16-09-2026 | Verified |
| F8 | All 30 examples carry CustomizationID urn:peppol:pint:billing-1@ae-1 and ProfileID urn:peppol:bis:billing | grep over */example/*.xml: 30 of each, one distinct value each; e.g. "Standard tax invoice.xml":6-7 | Verified |
| F9 | Saxon's own parser expands external entities | proc.parse_xml(xml_text=...) with an internal DTD declaring SYSTEM entity to a scratch file returned the file content as string value. lxml with resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False left the entity unexpanded. Hence validate_examples.py rejects any document whose docinfo.doctype is non-empty before handing bytes to Saxon, and passes the lxml serialisation, not the disk file | Verified |
| F10 | lxml XMLParser accepts resolve_entities, no_network, load_dtd, huge_tree keywords; DocInfo exposes doctype, internalDTD, externalDTD | etree.XMLParser.__doc__ signature; dir(etree.DocInfo) | Verified |
| F11 | UBL-Invoice-2.1.xsd: cbc:ID minOccurs="1" (line 120); cbc:CustomizationID minOccurs="0" (line 69); InvoiceTypeCode minOccurs="0" (219); DocumentCurrencyCode minOccurs="0" (267). Imports use relative ../common paths (lines 22, 24, 26) so XSD loading needs no network | uae_compliance/standards/ubl/2.1/xsd/maindoc/UBL-Invoice-2.1.xsd | Verified |
| F12 | Volume-discount-credit-note.xml places cac:DiscrepancyResponse (lines 181-184) before cac:OrderLineReference (line 185) inside cac:CreditNoteLine; UBL 2.1 CreditNoteLineType sequence has OrderLineReference (UBL-CommonAggregateComponents-2.1.xsd:9600) before DiscrepancyResponse (:9616), type starts at :9409 | files named | Verified |
| F13 | ISO 4217 list in ibr-cl-04 contains XXX, so a currency mutation to XXX would not fire; ZZZ is absent | trn-invoice/schematron/PINT-UBL-validation-preprocessed.sch:351 | Verified |
| F14 | Code list row counts (gc:SimpleCodeList/gc:Row): Aligned-TaxCategoryCodes 6, Aligned-TaxExemptionCodes 4, CreditReason 6 (credit note only), FreqBilling 10, GoodsType 5, ICD 243, ISO3166 251, ISO4217 177, ItemType 3, MimeCode 7, UNCL1001-inv 2, UNCL1001-cn 2, UNCL1153 818, UNCL4461 9, UNCL5189 19, UNCL7143 185, UNCL7161 178, UNECERec20 2162, eas 90, transactiontype 8 | parsed by build_lock.py, recorded in docs/standards-lock.json | Verified |
| F15 | Not-vendored PDFs: bis.pdf sha256 16d043ed4827aebe25e3499d49d3fceeb4c46cdc8542a46cc230c3931beb02b1 (1269827 bytes); compliance.pdf 03769afb140165a827ecd537d82b7d6552ff586bb2257f42b5fae7f0c8ef65b1 (79529); specialized-release-notes.pdf c69789bfe7cc1e1a5f33826090e35b8e2f9be3c7e3ed19f335d02dd42d8e98f7 (384642) | shasum -a 256 in scratchpad/pint/common/docs | Verified |

## Negative rule ids read from the .sch files (trn-invoice)

| Mutation | Expected id | Source | Rule test (abridged) |
| --- | --- | --- | --- |
| a remove root cbc:ID | ibr-002 | PINT-UBL-validation-preprocessed.sch:167 | normalize-space(cbc:ID) != '' |
| b seller PartyTaxScheme/cbc:CompanyID 14 digits | ibr-132-ae | PINT-jurisdiction-aligned-rules.sch:213 | string-length(.) = 15 and starts-with(., "1") and ends-with(., "03") and digits only; context is AE party VAT CompanyID |
| c ClassifiedTaxCategory/cbc:ID = M | ibr-139-ae | PINT-jurisdiction-aligned-rules.sch:236 (credit note copy same id at :236) | contains(' S E O AE Z N ', ...) |
| d InvoiceTypeCode = 999 | ibr-cl-01 | PINT-UBL-validation-preprocessed.sch:345 | contains(' 380 480 ', ...) for InvoiceTypeCode |
| e remove cbc:CustomizationID | ibr-001 | PINT-UBL-validation-preprocessed.sch:164 | normalize-space(cbc:CustomizationID) != '' |
| f TaxInclusiveAmount + 0.01 | ibr-co-15 | PINT-UBL-validation-preprocessed.sch:200 | TaxInclusiveAmount = round(TaxExclusiveAmount + TaxAmount) unless TaxIncludedIndicator |
| g DocumentCurrencyCode = ZZZ | ibr-cl-04 | PINT-UBL-validation-preprocessed.sch:351 | ISO 4217 alpha-3 list |

The mutation value for (b) is 19876543210203 (14 digits, keeps leading 1 and trailing 03) so only the length condition fails.

## Commands and outcomes

All run from /Users/aslam/frappe-local/loc16/apps/uae_compliance.

1. `/Users/aslam/frappe-local/loc16/env/bin/python scripts/standards/validate_examples.py`
   Exit 1. Header: `runtime: python 3.14.5 lxml 6.1.1 saxonche 13.0.0 (SaxonC-HE 13.0 from Saxonica)`.
   29 of 30 examples: `xsd=ok fatal=0 warning=0`. No example produced any Schematron warning or fatal failed assert in either layer.
   One failure: `trn-creditnote/Volume-discount-credit-note.xml: xsd=FAIL fatal=0 warning=0` with
   `xsd: line 185: Element '{...CommonAggregateComponents-2}OrderLineReference': This element is not expected. Expected is one of ( DiscrepancyResponse, DespatchLineReference, ReceiptLineReference, BillingReference, DocumentReference, PricingReference, OriginatorParty, Delivery, PaymentTerms, TaxTotal ).`
   Summary line: `positive: 30 examples, 29 passed, 1 failed`. Re-run after ruff format gave identical output and exit 1.

2. `/Users/aslam/frappe-local/loc16/env/bin/python scripts/standards/validate_examples.py --negative`
   Exit 0. Output:
   ```
   base example: uae_compliance/standards/pint_ae/1.0.4/trn-invoice/example/Standard tax invoice.xml
   a remove root cbc:ID: expected=ibr-002 xsd=FAIL fired=ibr-002 PASS
   b seller VAT CompanyID 14 digits: expected=ibr-132-ae xsd=ok fired=ibr-132-ae PASS
   c ClassifiedTaxCategory/cbc:ID = M: expected=ibr-139-ae xsd=ok fired=aligned-ibrp-s-08,ibr-139-ae PASS
   d InvoiceTypeCode = 999: expected=ibr-cl-01 xsd=ok fired=ibr-cl-01 PASS
   e remove cbc:CustomizationID: expected=ibr-001 xsd=ok fired=aligned-ibrp-001-ae,ibr-001 PASS
   f TaxInclusiveAmount + 0.01: expected=ibr-co-15 xsd=ok fired=ibr-co-15,ibr-co-16 PASS
   g DocumentCurrencyCode = ZZZ: expected=ibr-cl-04 xsd=ok fired=ibr-126,ibr-159-ae,ibr-175-ae,ibr-cl-04,ibr-co-15 PASS
   negative: 7 cases, 7 passed, 0 failed
   ```
   Note: (a) also fails XSD because cbc:ID is minOccurs="1" (F11). Extra fired ids are side effects of the mutation, not defects.

3. `/Users/aslam/frappe-local/loc16/env/bin/python scripts/standards/validate_examples.py --determinism`
   Exit 0. Output:
   ```
   determinism Standard.invoice.-.Extensive.xml: identical (failed asserts: 0)
   svrl text Standard.invoice.-.Extensive.xml: identical
   timing Standard.invoice.-.Extensive.xml: cold=0.100s (includes XSD load and XSLT compile) warm=0.006s
   determinism mutation f TaxInclusiveAmount + 0.01: identical (failed asserts: 2, ids: ibr-co-15,ibr-co-16)
   ```
   The positive example has no findings, so the tool also repeats mutation (f) to compare a non-empty list. Timing is a data point on the macOS arm64 development host only.

4. `/Users/aslam/frappe-local/loc16/env/bin/python scripts/standards/check_lock.py`
   Exit 0. Output: `checked 91 listed files, 0 problems`. It also reports any file under uae_compliance/standards that the lock does not list (suffixes .md and .txt excluded so NOTICES.md is allowed).

5. `/Users/aslam/frappe-local/loc16/env/bin/ruff check scripts/standards` exit 0 (`All checks passed!`). `ruff format --check scripts/standards` exit 0 after one `ruff format` pass that re-wrapped a single long call in validate_examples.py. ruff 0.15.22 from the env.

6. Lock regeneration: running the scratch generator twice produced byte-identical output (`cmp` silent). JSON has sorted keys, 2-space indent, trailing newline (last byte 0x0a). Top-level keys: canonical_version, files, generated_on, mof_guidelines, notes, pint_ae, runtime, schema_version, serializer_version, ubl, validation_evidence.

7. Dash check: `grep -c` for U+2014 and U+2013 over the three written files returned 0 each.

## Findings

FINDING 1 (Unresolved, official artifact). `trn-creditnote/example/Volume-discount-credit-note.xml` fails UBL 2.1 XSD validation because cac:OrderLineReference (line 185) follows cac:DiscrepancyResponse (lines 181-184) inside cac:CreditNoteLine, while CreditNoteLineType (UBL-CommonAggregateComponents-2.1.xsd:9409, refs at :9600 and :9616) requires the opposite order. Both Schematron layers report zero failed asserts for the same file, so the defect is in the example's element order, not in a PINT rule. The artifact was left unchanged and the check was not weakened; the positive run therefore exits 1 by design. Owner: maintainer (report upstream to the Peppol AE publisher or confirm against a later release). Consequence: this example cannot serve as an XSD positive case; the other 29 can. Affected phase: P01 (validator wrapper fixtures). Recorded in docs/standards-lock.json validation_evidence.positive_examples.failures.

FINDING 2 (Verified, security). SaxonC's parser expands external entities declared in an internal DTD subset (F9). The harness therefore gates on the hardened lxml parse and rejects any DOCTYPE before Saxon sees the bytes. The P01 validator wrapper must keep this order: lxml hardened parse, DOCTYPE and size rejection, then Saxon on the lxml serialisation. Do not pass user files to Saxon by path.

FINDING 3 (Verified). XXX is a member of the ibr-cl-04 ISO 4217 list, so mutation (g) uses ZZZ. Any P01 negative fixture must not rely on XXX to trigger ibr-cl-04.

FINDING 4 (Verified). Compile cost: both invoice stylesheets compile in about 0.14 s combined on this host; a single full validation of the extensive example is about 6 ms warm. Cache compiled PyXsltExecutable per worker as spec 3 requires; do not recompile per document.

## Unresolved items

- Effective applicability (mandate dates) is not established in P00; lock records status Unresolved with owner maintainer, consequence no applicability claim, affected phase P02.
- Saxon license: the wheel METADATA only links to the Saxonica terms page; the page states MPL 2.0 for HE. NOTICES.md (other agent) should cite the page and date. Status Verified from the page, not from the wheel.
- Volume-discount-credit-note.xml XSD failure (Finding 1).

## Notes for the orchestrator

- docs/standards-lock.json lists 91 vendored files: 75 PINT AE files (37 code lists: 18 invoice + 19 credit note; 30 examples: 27 invoice + 3 credit note; 8 schematron: 4 .sch + 4 .xslt) and 16 UBL 2.1 XSD files. NOTICES.md is excluded by suffix so the other agent may write it freely.
- The lock's `pint_ae.license` is the literal "see uae_compliance/standards/NOTICES.md" as instructed.
- canonical_version and serializer_version are null; notes say "defined in P01".
- validate_examples.py positive mode exits 1 while Finding 1 stands. The P00 gate needs a decision: accept 29/30 with the finding recorded, or wait for a corrected upstream example. The tool must not be changed to skip the file.
