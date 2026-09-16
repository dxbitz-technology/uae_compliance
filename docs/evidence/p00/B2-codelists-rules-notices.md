# B2: PINT AE 1.0.4 code lists, rules, examples, and NOTICES

Date: 16-09-2026. Phase P00 Baseline. Spec sections read: 1.2, 1.4, 6.1, 6.2, 6.3.

Base path `P` = `/Users/aslam/frappe-local/loc16/apps/uae_compliance/uae_compliance/standards/pint_ae/1.0.4`. Line numbers refer to the vendored files. All `.gc` files shared by both transaction folders are byte-identical (cmp), so invoice-folder paths are cited for shared lists. Both `.sch` files are byte-identical across `trn-invoice` and `trn-creditnote`.

Vendored tree integrity: 75 vendored files, 75 identical (sha256) to the extraction of `resources.zip` (sha256 `1e8b0bd595c672ac9d6fc886ddd0eb8027cb39a1d26bebdcb1ada37b7eee491f`, recomputed from the scratchpad copy). The zip holds 78 files; the three not vendored are `common/docs/bis.pdf`, `compliance.pdf`, `specialized-release-notes.pdf`. Status: Verified.

## 1. UNCL1001-inv.gc (`P/trn-invoice/codelist/UNCL1001-inv.gc`)

ShortName "Document name code", Version D.17A (lines 4 to 6). Two rows only.

| Code | Name | Description | Lines |
| --- | --- | --- | --- |
| 380 | Commercial invoice | (1334) Document/message claiming payment for goods or services supplied under conditions agreed between seller and buyer. | 36, 39, 42 |
| 480 | Invoice out of scope of tax | An invoice issued by a party who is out of the scope of tax regulations and shall not collect tax on the invoice. The invoice should not contain tax details or information about the party tax registrations. | 47, 50, 53 |

Verified: 380 and 480 are the only permitted invoice type codes in the list, and `ibr-cl-01` enforces exactly `' 380 480 '` (`PINT-UBL-validation-preprocessed.sch:345`). Note on names: the UNTDID name of 380 is "Commercial invoice"; the BIS text calls 380 the tax invoice and 480 the "commercial invoice" ("A UAE commercial invoice is associated with code 480 'Invoice out of scope of tax'", bis.pdf text line 461). The spec wording "tax invoice 380; commercial invoice 480" follows BIS usage, not the UNTDID name. Verified.

## 2. UNCL1001-cn.gc (`P/trn-creditnote/codelist/UNCL1001-cn.gc`)

| Code | Name | Description | Lines |
| --- | --- | --- | --- |
| 381 | Credit note | (1113) Document/message for providing credit information to the relevant party. | 36, 39, 42 |
| 81 | Credit note related to goods or services | Document message used to provide credit information related to a transaction for goods or services to the relevant party. | 47, 50, 53 |

Verified: 381 and 81 are the only credit note codes; `ibr-cl-01` enforces `' 81 381 '` (same line 345). BIS 1.5.4 (bis text lines 596 to 600): 381 for tax credit notes, 81 for out-of-scope transactions.

Self-billing codes: the BIS text (bis text lines 436 to 458) says a UAE self-billing invoice uses 389 and a self-billing credit note uses 261. Neither code is in the vendored lists, and `ibr-cl-01` rejects them. `ibr-127-ae` and `ibr-191-ae` still mention `cbc:CreditNoteTypeCode = "261"` in their tests (aligned sch lines 108, 120). Verified: the vendored billing package cannot validate self-billing documents. The self-billing family is a separate specialization (CustomizationID prefix `urn:peppol:pint:selfbilling-1@ae-1`, see section 9). Unresolved: whether the self-billing package is needed for P-phases that touch self-billing; owner: spec owner; consequence: self-billing rows stay disabled; affected phase: any phase enabling self-billing.

## 3. Aligned-TaxCategoryCodes.gc (`P/trn-invoice/codelist/Aligned-TaxCategoryCodes.gc`)

ShortName "AE VAT category codes", Version D.16B (lines 4 to 5). Six rows.

| Code (as stored) | Code points | Name | Lines |
| --- | --- | --- | --- |
| S | U+0053 | Standard rate | 27, 30 |
| E | U+0045 | Exempt from tax | 38, 41 |
| O | U+004F | Services outside scope of tax / Not subject to tax | 49, 52 |
| AE | U+0041 U+0045 | VAT Reverse Charge | 60, 63 |
| Z | U+005A | Zero rated | 71, 74 |
| Ν | U+039D (Greek capital Nu, bytes CE 9D) | Standard rate additional VAT | 82, 85 |

Findings:
- No code `M` exists in the list (grep for `<gc:SimpleValue>[NM]</gc:SimpleValue>` returns nothing). Verified.
- The sixth code is stored as Greek capital Nu (U+039D), not ASCII N (U+004E), in both folder copies and in the zip copy. Verified (xxd of line 82).
- Every Schematron rule uses ASCII `N`: `ibr-139-ae` code list test `' S E O AE Z N '` (aligned sch line 236); `ibr-116-ae` (line 109); `ibr-105-ae` (line 105); rule context at line 153 (`normalize-space(cbc:ID) = 'N'`); `ibr-111-ae` (line 81); `ibr-115-ae` and `ibr-114-ae` (lines 66, 73). Verified (grep for `"N"` and `'N'`).
- The official example `Margin scheme.xml` uses ASCII N (`<cbc:ID>N</cbc:ID>` at lines 107 and 130; code point 0x4e per parse). Verified.
- The name of the code is "Standard rate additional VAT", not "margin scheme". The margin scheme link is only through `ibr-116-ae` (transaction flag XX1XXXXX requires all tax categories to be N). Verified.
- Release notes 1.0.4 state "Code Lists: No change" (release notes text line 98). Verified.

Spec 6.2 check: "Margin uses ASCII N, not M" is correct for the wire format and the rules. Proposed: the app's own tax category enumeration must hold ASCII `N`; a loader that reads the `.gc` id byte for byte would carry U+039D into documents and fail `ibr-139-ae`. Treat the `.gc` entry as an upstream typo and record it in decisions.

## 4. Aligned-TaxExemptionCodes.gc (`P/trn-invoice/codelist/Aligned-TaxExemptionCodes.gc`)

ShortName "Reasons for exemption from tax", Version 2022 (lines 4 to 5). Four rows, no description column values.

| Code | Name | Lines |
| --- | --- | --- |
| DL8.46.1 | Cetrain financial services (sic, upstream spelling) | 27, 30 |
| DL8.46.2 | Supply of residential units (lease or sale) | 35, 38 |
| DL8.46.3 | Bare land | 43, 46 |
| DL8.46.4 | Local passenger transport | 51, 54 |

Verified. Note: no Schematron rule in either `.sch` file restricts `cbc:TaxExemptionReasonCode` to this list (the Codesmodelaligned pattern has six rules: ibr-001-ae, ibr-011-ae, ibr-013-ae, ibr-005-ae, ibr-139-ae, ibr-006-ae; none targets exemption reason codes). Presence is enforced by `ibr-167-ae`, `ibr-168-ae`, `ibr-169-ae`. Verified.

## 5. transactiontype.gc (`P/trn-invoice/codelist/transactiontype.gc`)

ShortName "Transaction type", Version 1 (lines 4 to 5). Eight rows. Each id is an 8-character positional mask; `1` marks the position, `X` means any other position.

| Position | Id | Name | Description | Line |
| --- | --- | --- | --- | --- |
| 1 | 1XXXXXXX | Free trade zone (position 1) | Supply of goods or services in Free trade zone | 25 |
| 2 | X1XXXXXX | Deemed supply (position 2) | Supply of goods or services without consideration | 36 |
| 3 | XX1XXXXX | Profit Margin Scheme (position 3) | Supply of goods under the profit margin scheme | 47 |
| 4 | XXX1XXXX | Summary invoice (position 4) | Taxable person makes more than one supply of Goods or Services to the same person in the same calendar month | 58 |
| 5 | XXXX1XXX | Continuous Supply (position 5) | Supply of goods and/or services made on recurrent basis | 69 |
| 6 | XXXXX1XX | Agent billing (position 6) | Agent who is a registrant makes a supply on behalf of the principal | 80 |
| 7 | XXXXXX1X | Supply through E-commerce (position 7) | Supply of goods or services via E-commerce | 91 |
| 8 | XXXXXXX1 | Exports (position 8) | Supply of goods or services outside the country | 102 |

Allowed values per position: `0` or `1`. `ibr-154-ae` (aligned sch line 121) test `matches(cbc:ProfileExecutionID, "^[01]{8}$")`; message: "It should be a string consisting of no more than 8 characters, exclusively comprising of 0 and 1. The value in this field should be based on the sequence of transaction present in the invoice (as per list order), If applicable '1', and if not applicable '0'." Verified.

Carrier element: `cbc:ProfileExecutionID` at document root (all rules test `cbc:ProfileExecutionID`; BIS 1.5.2 examples at bis text lines 532 to 562). Example value: `Margin scheme.xml` line 8 `<cbc:ProfileExecutionID>00100000</cbc:ProfileExecutionID>`; `Standard.invoice.-.Extensive.xml` uses `10001010` (three flags set: free zone, continuous supply, e-commerce). Verified. Combination rules: `ibr-157-ae` forbids positions 2, 3, 4 with type 480 or 81 (line 113). No rule forbids other combinations. Spec 6.3 "Represent the official transaction flags by named booleans" maps one boolean per position. Verified.

## 6. eas.gc and ICD.gc

eas.gc (`P/trn-invoice/codelist/eas.gc`): ShortName "Electronic Address Scheme (EAS)", Version 2020-11; 90 rows. UAE entry: id `0235`, name `UAE Tax Identification Number (TIN)` (lines 363, 366). No other AE-related scheme (search on "Emirat", "UAE", "AE" in name or description returned only 0235). Verified. `ibr-cl-25` (shared sch line 393) includes 0235 in the permitted endpoint scheme list. Verified.

ICD.gc (`P/trn-invoice/codelist/ICD.gc`): ShortName "ISO 6523 ICD list", Version 20210630; 243 rows. Entry `0235`: name `UAE Tax Identification Number (TIN)`, description `Intended Purpose/App. Area: A unique number issued to a range of persons required to be identified for tax purposes. Issuing agency: UAE Federal Tax Authority` (lines 2546, 2549, 2552). Verified. `ibr-cl-10` (shared sch line 360) includes 0235 in the PartyIdentification scheme list. Verified.

## 7. ItemType.gc, GoodsType.gc, CreditReason.gc, FreqBilling.gc

ItemType.gc (`P/trn-invoice/codelist/ItemType.gc`, ShortName "Item type", Version 1, 3 rows):

| Code | Name | Line |
| --- | --- | --- |
| G | Goods | 25 |
| S | Services | 33 |
| B | Both | 41 |

Used by `ibr-184-ae`, `ibr-185-ae`, `ibr-186-ae` on `cac:CommodityClassification/cbc:CommodityCode` (aligned sch lines 128 to 130). No code list rule restricts CommodityCode to this list. Verified.

GoodsType.gc (`P/trn-invoice/codelist/GoodsType.gc`, ShortName "Type of goods or services subject to RCM", Version 1, 5 rows):

| Code | Name | Line |
| --- | --- | --- |
| DL8.48.8.2 | Electronic Devices | 25 |
| DL8.48.8.1 | Gold and Diamonds | 33 |
| DL8.48.3.1 | Crude or refined oil | 41 |
| DL8.48.3.2 | Unprocessed or processed natural gas | 49 |
| DL8.48.3.3 | Pure hydrocarbons | 57 |

Enforced by `ibr-006-ae` on `cbc:NatureCode` (aligned sch line 239) and required by `ibr-166-ae` when category AE (line 127). Verified.

CreditReason.gc (`P/trn-creditnote/codelist/CreditReason.gc`, ShortName "Reasons for credit note", Version 1, 6 rows):

| Code | Name | Line |
| --- | --- | --- |
| DL8.61.1.A | If the supply was cancelled. | 25 |
| DL8.61.1.B | If the tax treatment of the supply has changed due to a change in the nature of the supply. | 33 |
| DL8.61.1.C | If the previously agreed consideration for the supply was altered for any reason (i.e. bad debt relief). | 41 |
| DL8.61.1.D | If the recipient of goods or recipient of services returned them to the registrant in full or in part and the Consideration was returned in full or in part. | 49 |
| DL8.61.1.E | If the tax was charged or tax treatment was applied in error. | 57 |
| VD | Volume Discount. | 65 |

Enforced by `ibr-001-ae` on `cac:DiscrepancyResponse/cbc:ResponseCode` (aligned sch line 224). Verified.

FreqBilling.gc (`P/trn-invoice/codelist/FreqBilling.gc`, ShortName "Frequency of billing codes", Version 1, 10 rows):

| Code | Name | Line |
| --- | --- | --- |
| DLY | Daily | 25 |
| WKY | Weekly | 33 |
| Q15 | Once in 15 days | 41 |
| MTH | Monthly | 49 |
| Q45 | Once in 45 days | 57 |
| Q60 | Once in 60 days | 65 |
| QTR | Quarterly | 73 |
| YRL | Yearly | 81 |
| HYR | Half-Yearly | 89 |
| OTH | Others | 97 |

Enforced by `ibr-005-ae` on `cac:InvoicePeriod/cbc:DescriptionCode` (aligned sch line 233); `ibr-160-ae` requires `cbc:Note` when OTH (line 116). Verified.

## 8. Row counts (lxml parse of `gc:SimpleCodeList/gc:Row`)

| File | Rows | ShortName | Version |
| --- | --- | --- | --- |
| UNECERec20.gc | 2162 | Recommendation 20, including Recommendation 21 codes - prefixed with X (UN/ECE) | 11e |
| UNCL1153.gc | 818 | Invoiced object identifier scheme | D.16B |
| UNCL4461.gc | 9 | Payment means codes used in AE | D.16B |
| UNCL5189.gc | 19 | Allowance or charge identification code | D.16B |
| UNCL7143.gc | 185 | Item type identification code | D.19A |
| UNCL7161.gc | 178 | Charge reason code | D.16B |
| ISO3166.gc | 251 | Country codes | 2013 |
| ISO4217.gc | 177 | Currency codes | 2015 |
| MimeCode.gc | 7 | Media Types | 20210921 |
| eas.gc | 90 | Electronic Address Scheme (EAS) | 2020-11 |
| ICD.gc | 243 | ISO 6523 ICD list | 20210630 |

Verified. sha256 of each vendored code list and sch file is in the shell log; the trn-invoice `.sch` hashes: `PINT-UBL-validation-preprocessed.sch` c073dd645db0401a3276cfa31f381750d35f7fde8381b19b92b8bceee236f534, `PINT-jurisdiction-aligned-rules.sch` d0e767f246fa8e90749060a51fea5a22e03659ae83ec66aff9cfd3b932168a3e.

## 9. Schematron rules

Both files declare `queryBinding="xslt2"` (line 1 of each). Counts are identical in both transaction folders (files are byte-identical).

| File | Patterns (asserts) | Total asserts | fatal | warning | sch:report |
| --- | --- | --- | --- | --- | --- |
| PINT-UBL-validation-preprocessed.sch | UBL-model (152), Codesmodel (18) | 170 | 170 | 0 | 0 |
| PINT-jurisdiction-aligned-rules.sch | UBL-modelaligned (126), Codesmodelaligned (6) | 132 | 132 | 0 | 0 |

All 302 asserts per folder carry `flag="fatal"`. There are no warnings. Ids are unique within each file. Aligned file id prefixes: 88 `ibr-*-ae`, 44 `aligned-*`. Verified.

Quoted rules (file `A` = `P/trn-invoice/schematron/PINT-jurisdiction-aligned-rules.sch`, file `U` = `P/trn-invoice/schematron/PINT-UBL-validation-preprocessed.sch`; tests are exact with whitespace collapsed):

### IBR-116-AE (A:109, fatal)
context: `/ubl:Invoice | /cn:CreditNote`
test: `not(matches(cbc:ProfileExecutionID, "^[01]{2}1[01]{5}$")) or not((//cac:TaxCategory/cbc:ID | //cac:ClassifiedTaxCategory/cbc:ID)[normalize-space(.) != "N"])`
msg: When Invoice transaction-type code (BTAE-02) has value XX1XXXXX (Margin scheme), then the tax category code (IBT-151) should have 'Standard rate additional VAT'.

Related N rules: `ibr-105-ae` (A:105) exactly one TaxSubtotal with category N when any N used; `ibr-102-ae` (A:154) N breakdown taxable amount equals sum of N line net amounts per rate; `ibr-108-ae` (A:155) `../cbc:TaxAmount = 0` for N breakdown; `ibr-111-ae` (A:81) N line must have `cbc:Percent > 0`; `ibr-115-ae` (A:66) and `ibr-114-ae` (A:73) document allowance or charge category cannot be N. Verified. Spec 6.2 "implement its full rules before enabling it" maps to these seven rules.

### IBR-132-AE (A:213, fatal)
context: `cac:Party[cac:PostalAddress/cac:Country/cbc:IdentificationCode = 'AE']/cac:PartyTaxScheme[cac:TaxScheme/normalize-space(upper-case(cbc:ID)) = 'VAT']/cbc:CompanyID`
test: `string-length(.) = 15 and starts-with(., "1") and ends-with(., "03") and matches(., "^[0-9]+$")`
msg: VAT identifier [IBT-031, IBT-048, IBT-063, BTAE-14] should be TRN [VAT registration number] and must be 15 digits, starting with 1, ending with 03.

Verified: the context limits the rule to parties whose postal address country is AE and to the VAT tax scheme. Spec 6.2 "Do not apply the AE rule to all foreign tax IDs" matches.

### IBR-007-AE (A:97, fatal)
context: `/ubl:Invoice | /cn:CreditNote`
test: `not(matches(cbc:ProfileExecutionID, "^1[01]{7}$")) or cac:BuyerCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID`
msg: When Invoice Transaction-type code (BTAE-02) has value 1XXXXXXX (Free trade zone), then Beneficiary ID (BTAE-01) MUST be provided.

Verified: the beneficiary is carried in `cac:BuyerCustomerParty` and the rule requires `cac:PartyIdentification/cbc:ID`, not a name. Spec 6.2 free-zone row matches.

### Credit note references and reason
- `ibr-055-ae` (A:103, fatal), context `/ubl:Invoice | /cn:CreditNote`, test: `(((cbc:InvoiceTypeCode | cbc:CreditNoteTypeCode) = "381" or (cbc:InvoiceTypeCode | cbc:CreditNoteTypeCode) = "81") and (((cac:BillingReference) and (cac:DiscrepancyResponse/cbc:ResponseCode != "VD")) or (not(cac:BillingReference) and (cac:DiscrepancyResponse/cbc:ResponseCode = "VD")))) or not((cbc:InvoiceTypeCode | cbc:CreditNoteTypeCode) = "381" or (cbc:InvoiceTypeCode | cbc:CreditNoteTypeCode) = "81")`; msg: Preceding invoice reference (IBG-03) is must when invoice type code (IBT-003) is 381 (Credit note) or 81 (Credit note related to goods or services) except when the [BTAE-03] Credit note reason code is 'VD'. This is the Volume Discount exception. Verified. Note the test is an exclusive pairing: with reason VD the BillingReference must be absent; with any other reason it must be present.
- `ibr-158-ae` (A:114, fatal), same context, test: `not((cbc:InvoiceTypeCode | cbc:CreditNoteTypeCode) = "381" and not(exists(cac:DiscrepancyResponse/cbc:ResponseCode)))`; msg: Where the Invoice type code [IBT-003] is 'Credit note', Credit note reason code [BTAE-03] MUST be there. Verified. It covers 381 only, not 81.
- `ibr-001-ae` (A:224, fatal), context `cac:DiscrepancyResponse/cbc:ResponseCode`, test: `( ( not(contains(normalize-space(.),' ')) and contains( ' DL8.61.1.A DL8.61.1.B DL8.61.1.C DL8.61.1.D DL8.61.1.E VD ',concat(' ',normalize-space(.),' ') ) ) )`. Verified.
- Shared: `ibr-055` (U:274) each BillingReference must contain `cac:InvoiceDocumentReference/cbc:ID`; `ibr-sr-06` (U:276) `count(cac:InvoiceDocumentReference) <= 1`. Verified.
- `ibr-124-ae` (A:107) forbids `cbc:TaxPointDate` on 381 or 81. `ibr-127-ae` (A:108) and `ibr-191-ae` (A:120) exempt 381, 81, 261 and deemed supply from DueDate and PaymentMeansCode. Verified.

BIS 1.5.4 text (bis text lines 601 to 606): "it is compulsory to specify the reason for issuing the credit note in the field Credit note reason code (BTAE-03). The preceding invoice reference should be specified in section ibg-03, except in the case of volume discounts." The BIS example shows BillingReference as optional with VD; the Schematron test forbids it with VD. Verified discrepancy between prose and rule; the rule governs.

### TIN versus VAT registration prefix
No rule compares `cbc:EndpointID` or `cac:PartyIdentification/cbc:ID` to the TRN (`cac:PartyTaxScheme/cbc:CompanyID`) prefix. Search of all 302 tests for `substring`, `starts-with`, `ends-with`, `EndpointID`, `PartyIdentification`, `CompanyID` found only these format rules:
- `ibr-148-ae` (A:216), context `cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme[cac:TaxScheme/normalize-space(upper-case(cbc:ID)) != 'VAT']/cbc:CompanyID`, test `matches(., "^1[0-9]{9}$")`; msg: The Seller VAT registration identifier (IBT-032) should be TIN (tax identification number) and must be 10 numeric digits and should be of the format 1XXXXXXXXX.
- `ibr-133-ae` (A:219), context `cac:TaxScheme/cbc:ID`, test `. = "VAT" or exists(//cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID[ string-length(normalize-space(.)) = 10 and starts-with(normalize-space(.), "1") and translate(normalize-space(.), "0123456789", "") = ""])`.
- `ibr-178-ae` (A:46), seller may have two PartyTaxScheme entries, exactly one with scheme VAT.
- `ibr-177-ae` (A:45), seller must have a `cac:PartyTaxScheme/cbc:CompanyID` when agent billing flag set.
- Buyer rules keyed on scheme 0235 and endpoint prefix: `ibr-149-ae` (A:27) `cbc:EndpointID/@schemeID != "0235" or matches(normalize-space(cbc:EndpointID), "^[19]") or exists(cac:PartyTaxScheme/cbc:CompanyID)`; `ibr-135-ae` (A:29) buyer id or buyer VAT id required unless exports flag, when scheme 0235 and endpoint not `^1\d{9}$`; `ibr-180-ae` (A:30), `ibr-183-ae` (A:31) legal registration type constraints. Seller: `ibr-150-ae` (A:47) legal registration id required when endpoint scheme 0235; `ibr-173-ae` (A:48), `ibr-181-ae` (A:49).
Verified: spec 6.2 "Do not enforce an unconditional TIN/TRN prefix equality" is consistent with the rules; no such rule exists. The examples happen to share prefixes (Seller TIN 1987654321, TRN 198765432102003) but `Margin scheme.xml` uses the 15-digit TRN as EndpointID (line 25 area; parsed `0235:112345678900003`), which no rule rejects.

### Self-billing mentions
Only two rules mention self-billing; both are the profile rules below. `ibr-cl-01` matched a text search on "self" only through the XPath axis `self::`. Verified.

### CustomizationID and ProfileID
- `ibr-001` (U:164) `normalize-space(cbc:CustomizationID) != ''`; `ibr-sr-63` (U:166) no `*`; `ibr-076` (U:183) `exists(cbc:ProfileID)`.
- `aligned-ibrp-001-ae` (A:89, fatal), context `/ubl:Invoice | /cn:CreditNote`, test: `starts-with(normalize-space(cbc:CustomizationID/text()), 'urn:peppol:pint:billing-1@ae-1') or starts-with(normalize-space(cbc:CustomizationID/text()), 'urn:peppol:pint:selfbilling-1@ae-1')`; msg: Specification identifier (ibt-024) MUST start with the value 'urn:peppol:pint:billing-1@ae-1' or 'urn:peppol:pint:selfbilling-1@ae-1'.
- `aligned-ibrp-002-ae` (A:90, fatal), test: `/*/cbc:ProfileID and (matches(normalize-space(/*/cbc:ProfileID), '^urn:peppol:bis:billing') or matches(normalize-space(/*/cbc:ProfileID), '^urn:peppol:bis:selfbilling'))`; msg: Business process (ibt-023) MUST be in the format 'urn:peppol:bis:billing' or 'urn:peppol:bis:selfbilling'.
- BIS 5.1.1 table: Invoice and credit note, `cbc:CustomizationID` = `urn:peppol:pint:billing-1@ae-1`, `cbc:ProfileID` = `urn:peppol:bis:billing`. All 30 examples use exactly these two values. Verified.

### InvoiceTypeCode and CreditNoteTypeCode
- `ibr-004` (U:171) type code present. `ibr-cl-01` (U:345, quoted in section 1). 
- `ibr-123-ae` (A:85) line ClassifiedTaxCategory exactly once except 81 or 480. `ibr-134-ae` (A:98) seller VAT id required except 480 or 81. `ibr-136-ae` (A:99) buyer legal registration id required when 480 or 81. `ibr-122-ae` (A:106) with 480 or 81 every category must be E, O or Z. `ibr-151-ae` (A:110) with 380 or 381 the lines must not contain only E and O. `ibr-157-ae` (A:113) 480 or 81 cannot carry flags at positions 2, 3, 4. `ibr-124-ae`, `ibr-127-ae`, `ibr-158-ae`, `ibr-191-ae` as above. Verified. This is the "verified category matrix" spec 6.2 asks for: the document code depends on tax categories present, not on `is_return` alone.

### Disclosed agent (principal or beneficiary)
- `ibr-137-ae` (A:100, fatal), test: `(matches(cbc:ProfileExecutionID, "^[01]{5}1[01]{2}$") and cac:SellerSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID) or not(matches(cbc:ProfileExecutionID, "^[01]{5}1[01]{2}$"))`; msg: Principal ID (BTAE-14) is MUST, where Invoice transaction type code [BTAE-02] is XXXXX1XX (Disclosed Agent billing).
- `ibr-176-ae` (A:118, fatal), test: `(matches(cbc:ProfileExecutionID, "^[01]{5}1[01]{2}$") and cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID != cac:SellerSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID) or not(matches(cbc:ProfileExecutionID, "^[01]{5}1[01]{2}$"))`; msg: Seller VAT Identifier [IBT-031] and Principal ID [BTAE-14] should not be the same.
- `ibr-177-ae` (A:45, fatal), context `cac:AccountingSupplierParty/cac:Party`, test: `not(matches((ancestor::*[local-name()='Invoice' or local-name()='CreditNote'][1]/cbc:ProfileExecutionID)[1], '^[01]{5}1[01]{2}$')) or exists(cac:PartyTaxScheme/cbc:CompanyID)`.
- Beneficiary: `ibr-007-ae` (A:97) quoted above; carrier `cac:BuyerCustomerParty`.
Verified: principal is `cac:SellerSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID`; beneficiary is `cac:BuyerCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID`. Spec 6.2 "Agency needs principal identity" matches. Note: `ibr-132-ae` message lists BTAE-14 but its context only reaches `PartyTaxScheme/CompanyID`, so the principal id in `PartyIdentification` is not TRN-format checked.

### Other scenario rules relevant to spec 6.2
- Summary: `ibr-138-ae` (A:101) `cac:InvoicePeriod` required with XXX1XXXX. Verified.
- E-commerce: `ibr-142-ae` (A:104) Delivery address StreetName, CityName, CountrySubentity required with XXXXXX1X. Verified.
- Export: `ibr-152-ae` (A:111) same three delivery fields required with XXXXXXX1 unless delivery country is AE. Verified. Export does not force a tax category; `Exports.xml` uses Z, USD document currency, AED tax currency. Verified.
- Price base quantity: `ibr-126-ae` (A:54) `boolean(cbc:BaseQuantity) and boolean(cac:AllowanceCharge/cbc:BaseAmount)` on every `cac:Price`. Verified. This is stricter than the spec wording: gross price is mandatory too.
- Deemed supply: `ibr-127-ae` and `ibr-191-ae` waive DueDate and PaymentMeans with X1XXXXXX. Verified.
- Currency: `ibr-140-ae` (A:122) TaxCurrencyCode, if present, must be AED; `ibr-159-ae` (A:115) exchange rate required when document currency is not AED; `ibr-175-ae` (A:117) AED tax total and `AdditionalDocumentReference[cbc:DocumentTypeCode = "aedtotal-incl-vat"]` required; `ibr-153-ae` (A:112). Verified.
- Address: `ibr-128-ae` (A:60) AE country subdivision must be one of AUH, DXB, SHJ, UAQ, FUJ, AJM, RAK. `ibr-143-ae`, `ibr-144-ae` street, city, subdivision required for seller and buyer. Verified.
- Standard rate: `ibr-190-ae` (A:119) every S rate must be 5.00. Verified.
- Line: `ibr-104-ae`, `ibr-194-ae` require `cac:ItemPriceExtension/cbc:Amount` (BTAE-10) and, unless E, the VAT line amount (BTAE-08). `ibr-193-ae` requires `cbc:UUID`. `ibr-125-ae` requires item description. `ibr-184-ae` to `ibr-189-ae` item type G, S, B with HS and SAC schemes. Verified.

## 10. Example files

Root namespace for `Invoice` is `urn:oasis:names:specification:ubl:schema:xsd:Invoice-2`; for `CreditNote` it is `urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2`. All 30 files: CustomizationID `urn:peppol:pint:billing-1@ae-1`, ProfileID `urn:peppol:bis:billing`. Flag = `cbc:ProfileExecutionID`. Presence columns test direct children of the root. "Doc A/C" = document-level `cac:AllowanceCharge`.

| Folder | Scenario (file) | Root | Type | Currency | TaxCurrency | Tax categories | BuyerRef | OrderRef | PaymentMeans | Delivery | InvoicePeriod | BillingRef | Doc A/C | Flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| inv | Buyer-PAS-identifier | Invoice | 380 | AED | absent | S | no | no | yes | no | no | no | no | 00000000 |
| inv | Commercial invoice | Invoice | 480 | AED | absent | O | no | no | yes | no | no | no | no | 00000000 |
| inv | Continuous.supplies | Invoice | 380 | AED | absent | E, S | no | no | yes | no | yes | no | yes | 00001000 |
| inv | Deemed.supply.-.predefined.endpoint | Invoice | 380 | AED | absent | S | no | no | yes | no | no | no | yes | 01000000 |
| inv | Disclosed.agent.billing | Invoice | 380 | AED | absent | S | no | no | yes | no | no | no | yes | 00000100 |
| inv | Doc-level-allowance-AE-category | Invoice | 380 | AED | absent | AE | no | no | yes | no | no | no | yes | 00000000 |
| inv | Doc-level-allowance-E-category | Invoice | 480 | AED | absent | E | no | no | yes | no | no | no | yes | 00000000 |
| inv | Doc-level-allowance-O-category | Invoice | 480 | AED | absent | O | no | no | yes | no | no | no | yes | 00000000 |
| inv | Doc-level-allowance-Z-category | Invoice | 380 | AED | absent | Z | no | no | yes | no | no | no | yes | 00000000 |
| inv | Doc-level-charge-AE-category | Invoice | 380 | AED | absent | AE | no | no | yes | no | no | no | yes | 00000000 |
| inv | Doc-level-charge-E-category | Invoice | 480 | AED | absent | E | no | no | yes | no | no | no | yes | 00000000 |
| inv | Doc-level-charge-O-category | Invoice | 480 | AED | absent | O | no | no | yes | no | no | no | yes | 00000000 |
| inv | Doc-level-charge-Z-category | Invoice | 380 | AED | absent | Z | no | no | yes | no | no | no | yes | 00000000 |
| inv | Exports.-.predefined.endpoint | Invoice | 380 | USD | AED | Z | no | yes | yes | yes | no | no | no | 00000001 |
| inv | Exports | Invoice | 380 | USD | AED | Z | no | yes | yes | yes | no | no | no | 00000001 |
| inv | Margin scheme | Invoice | 380 | AED | absent | N (U+004E) | no | no | yes | no | no | no | no | 00100000 |
| inv | Seller-PAS-identifier | Invoice | 380 | AED | absent | S | no | no | yes | no | no | no | no | 00000000 |
| inv | Seller-TIN-identifier | Invoice | 380 | AED | absent | S | no | no | yes | no | no | no | no | 00000000 |
| inv | Standard invoice Mandatory fields | Invoice | 380 | AED | absent | S | no | no | yes | no | no | no | no | 00000000 |
| inv | Standard tax invoice | Invoice | 380 | AED | absent | S | yes | yes | yes | no | yes | yes | yes | 00000000 |
| inv | Standard.invoice.-.Extensive | Invoice | 380 | AED | absent | AE, E, O, S, Z | yes | yes | yes | yes | yes | yes | yes | 10001010 |
| inv | Standard.tax.invoice.-.predefined.endpoint | Invoice | 380 | AED | absent | S | yes | yes | yes | no | yes | yes | yes | 00000000 |
| inv | Summary tax invoice | Invoice | 380 | AED | absent | AE, S | no | no | yes | no | yes | no | yes | 00010000 |
| inv | Supply involving free trade zone | Invoice | 380 | AED | absent | S | no | no | yes | no | no | no | yes | 10000000 |
| inv | Supply through e-commerce | Invoice | 380 | AED | absent | S | no | no | yes | yes | no | no | yes | 00000001 |
| inv | Supply under Reverse charge mechanism | Invoice | 380 | AED | absent | AE | no | no | yes | no | no | no | no | 00000000 |
| inv | Zero rated supplies | Invoice | 380 | AED | absent | Z | no | yes | yes | no | no | no | no | 00000000 |
| cn | Disclosed agent billing tax credit note | CreditNote | 381 | AED | absent | S | yes | yes | no | no | yes | yes | yes | 00000000 |
| cn | Standard tax credit Note | CreditNote | 381 | AED | absent | S | yes | yes | no | no | yes | yes | yes | 00000000 |
| cn | Volume-discount-credit-note | CreditNote | 381 | AED | absent | S | yes | yes | no | no | yes | no | yes | 00000000 |

Identity and reference details:

| Scenario | Seller EndpointID | Buyer EndpointID | Seller TRN (VAT CompanyID) | Buyer TRN | Seller / Buyer country | Extra parties | BillingReference ID / date | Credit reason (ResponseCode) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Buyer-PAS-identifier | 0235:1987654321 | 0235:1345678901 | 198765432102003 | 134567890123003 | AE / AE | none | | |
| Commercial invoice | 0235:1987654321 | 0235:1345678901 | 198765432112303 | 134567890123003 | AE / AE | PayeeParty | | |
| Continuous.supplies | 0235:1987654321 | 0235:1456789456 | 132654987101003 | 145678945601003 | AE / AE | none | | |
| Deemed.supply.-.predefined.endpoint | 0235:1246801357 | 0235:1012345678 | 124680135701003 | 178901234501003 | AE / AE | none | | |
| Disclosed.agent.billing | 0235:1239874562 | 0235:1456789456 | 124680135701003 | 145678945601003 | AE / AE | SellerSupplierParty | | |
| Doc-level-* (8 files) | 0235:1987654321 | 0235:1345678901 | 198765432102003 | 134567890123003 | AE / AE | none | | |
| Exports.-.predefined.endpoint | 0235:1987654321 | 0235:9900000099 | 132654987101003 | none | AE / AU | none | | |
| Exports | 0235:1987654321 | 0151:51824753556 | 132654987101003 | none | AE / AU | none | | |
| Margin scheme | 0235:112345678900003 | 0235:112345679000003 | 112345678900003 | 112345679000003 | AE / AE | none | | |
| Seller-PAS-identifier | 0235:1987654321 | 0235:1345678901 | 198765432102003 | 134567890123003 | AE / AE | none | | |
| Seller-TIN-identifier | 0235:1987654321 | 0235:1345678901 | 198765432102003 plus second PartyTaxScheme 1234567890 (TIN) | 134567890123003 | AE / AE | none | | |
| Standard invoice Mandatory fields | 0235:1357902468 | 0235:1345678901 | 135790246801003 | 134567890123003 | AE / AE | none | | |
| Standard tax invoice | 0235:1987654321 | 0235:1345678901 | 198765432102003 | 134567890123003 | AE / AE | PayeeParty | INV-234-2025 / 2025-02-06 | |
| Standard.invoice.-.Extensive | 0235:112345678900003 | 0235:112345679000003 | 112345678900003 | 112345679000003 | AE / AE | BuyerCustomerParty (PartyIdentification 189098765401003), TaxRepresentativeParty, PayeeParty; InvoicePeriod DescriptionCode OTH; 5 lines | INV-1001/2022 / 2025-01-30 | |
| Standard.tax.invoice.-.predefined.endpoint | 0235:1987654321 | 0235:9900000098 | 198765432102003 | 134567890123003 | AE / AE | PayeeParty | INV-234-2025 / 2025-02-06 | |
| Summary tax invoice | 0235:1278906543 | 0235:1347809543 | 127890654301003 | 134780954301003 | AE / AE | none; 4 lines | | |
| Supply involving free trade zone | 0235:1246801357 | 0235:1789012345 | 124680135701003 | 178901234501003 | AE / AE | BuyerCustomerParty (PartyIdentification 189098765401003) | | |
| Supply through e-commerce | 0235:112345678900003 | 0235:112345679000003 | 112345678900003 | 112345679000003 | AE / AE | PayeeParty | | |
| Supply under Reverse charge mechanism | 0235:1278906543 | 0235:1347809543 | 127890654301003 | 134780954301003 | AE / AE | none | | |
| Zero rated supplies | 0235:1987654321 | 0235:1347809543 | 132654987101003 | none | AE / AE | none | | |
| Disclosed agent billing tax credit note | 0235:1987654321 | 0235:1345678901 | 198765432102003 | 134567890123003 | AE / AE | SellerSupplierParty, PayeeParty | Sample-02 / 2025-02-07 | DL8.61.1.E |
| Standard tax credit Note | 0235:1987654321 | 0235:1345678901 | 198765432102003 | 134567890123003 | AE / AE | PayeeParty | Sample-02 / 2025-02-07 | DL8.61.1.E |
| Volume-discount-credit-note | 0235:1987654321 | 0235:1345678901 | 198765432102003 | 134567890123003 | AE / AE | PayeeParty | none | VD and DL8.61.1.E (two document-level DiscrepancyResponse, lines 21 to 27) plus VD at line level (line 181) |

Observations (all Verified against the files):
- Predefined endpoints in examples: `9900000099` (exports, receiver not in Peppol) and `9900000098` (buyer not subject to UAE e-invoicing) with scheme 0235, matching BIS 1.5.3 (bis text lines 573 to 585; deemed supply is `9900000097`). The `Deemed.supply.-.predefined.endpoint.xml` example does not use 9900000097; its buyer endpoint is `0235:1012345678`. Spec 6.3 "Special deemed/not-onboarded/export endpoint values come from the locked official source": the values are 9900000097 (deemed), 9900000098 (buyer not subject), 9900000099 (exports without Peppol receiver), scheme 0235, from BIS 1.5.3. Verified from the BIS text; the deemed example does not exercise it.
- `Exports.xml` uses buyer endpoint scheme `0151` (Australian ABN) and no buyer TRN: confirms spec 6.3 "Keep recipient endpoint scheme and value explicit, including foreign schemes".
- `Volume-discount-credit-note.xml` line 13 `cbc:Note` reads `Volume discount credit note — VD reason, no BillingReference required per ibr-055-ae` (contains U+2014). The file is identical to the zip copy; release notes 1.0.4 list it as "Added new credit note example covering the VD (Volume Discount)" (release notes text lines 395 to 396). It is upstream content and stays verbatim. Verified.
- Only the invoice examples carry `cac:PaymentMeans`; all three credit notes omit it (consistent with `ibr-191-ae`). Verified.
- No example uses TaxCurrencyCode other than the two export files (AED). Verified.
- Whether every example passes both Schematron files on the chosen runtime is not established in this task. Unresolved; owner: P00 runtime task; resolved by running the compiled XSLT over all 30 files.

## 11. Redistribution terms

Search of pdftotext output (`/private/tmp/.../scratchpad/p00/b2txt/{bis,compliance,specialized-release-notes}.txt`) for `license`, `licence`, `copyright`, `OpenPeppol`, `Creative Commons`, `reproduc`:

- bis.pdf, "Statement of copyright" (text lines 62 to 72), verbatim: "This Peppol Business Interoperability Specification (Peppol BIS) document is a Country Specification based on the PINT. The restrictions on PINT implemented in this Peppol BIS are identified in the conformance statement provided in appendix A. The copyright of PINT is owned by OpenPEPPOL and its members. OpenPEPPOL AISBL holds the copyright of this Peppol BIS. This Peppol BIS document may not be modified, re-distribute, sold or repackaged in any other way without the prior consent of OpenPEPPOL AISBL."
- bis.pdf footer (line 38): "OpenPeppol AISBL, Post-Award Coordinating Community v1.1.3". Line 125: "For further information on Peppol/OpenPEPPOL see http://peppol.org".
- compliance.pdf: no match for any term.
- specialized-release-notes.pdf: no license or copyright match. "Maintained by United Arab Emirates (UAE) Peppol Authority", "Release Date 2026-06-02", "Status Final" (lines 44 to 46). "For support and clarification: OpenPeppol UAE Peppol Authority support." (line 430).
- "Creative Commons" and "reproduc": no match in any of the three files.
- The `.gc`, `.sch`, `.xslt` and example files carry no license or copyright text (grep over the vendored tree).
- `pint-ae-landing.html` in the scratchpad (title "PINT AE Billing version 1.0.4 | United Arab Emirates electronic document specifications") contains no license, copyright, or terms text.

Result: the only statement found covers the BIS document itself and restricts modification and redistribution of that document. Terms for redistributing the code lists, Schematron, and examples are not stated in the downloaded artifacts. Unresolved; owner: spec owner (decisions.md D006); consequence: vendoring the technical artifacts in a public AGPL repository rests on no written permission; resolved by the OpenPeppol website terms page or written confirmation from OpenPeppol or the UAE Peppol Authority; affected phase: P00 release gate.

OASIS notice from `/Users/aslam/frappe-local/loc16/apps/uae_compliance/uae_compliance/standards/ubl/2.1/xsd/maindoc/UBL-Invoice-2.1.xsd` lines 957 to 1001 (header line 8 "Copyright (c) OASIS Open 2013. All Rights Reserved.", line 4 source "http://docs.oasis-open.org/ubl/os-UBL-2.1/"). The notice is reproduced verbatim in NOTICES.md and was checked equal to the XSD text after whitespace normalization. Verified.

## 12. NOTICES.md

Written: `/Users/aslam/frappe-local/loc16/apps/uae_compliance/uae_compliance/standards/NOTICES.md` (53 lines). Sections: PINT AE Billing 1.0.4 (publisher, source URL, resources.zip sha256, date 16-09-2026, 75 files unchanged, PDFs not vendored, BIS copyright statement quoted, terms for technical artifacts not stated, see docs/decisions.md); OASIS UBL 2.1 XSD (copyright line, source URL, UBL-2.1.zip sha256, date, verbatim notice); SaxonC-HE runtime (saxonche 13.0.0, Saxonica, MPL 2.0, terms URL, not vendored). No U+2014 or U+2013 in the file (grep). The BIS quote and OASIS quote are verbatim.

## 13. Spec 6.2 and 6.3 check summary

| Spec row | Result |
| --- | --- |
| Document codes 380/381/480/81 | Verified. Only these four codes exist and are enforced (`ibr-cl-01`). Category matrix rules: ibr-122-ae, ibr-123-ae, ibr-134-ae, ibr-136-ae, ibr-151-ae, ibr-157-ae. |
| Tax categories, N not M | Verified for rules and examples (ASCII N). Code list file stores Greek Nu (U+039D); Proposed: treat as upstream typo, keep ASCII N in the app list, record in decisions. Full N rule set: ibr-116-ae, ibr-105-ae, ibr-102-ae, ibr-108-ae, ibr-111-ae, ibr-114-ae, ibr-115-ae. |
| VAT identifiers AE format | Verified. ibr-132-ae applies only to parties with country AE and scheme VAT. |
| Participant versus VAT identity | Verified. No TIN/TRN prefix equality rule exists. TIN format rule ibr-148-ae (`^1[0-9]{9}$`) applies to the seller non-VAT PartyTaxScheme only. |
| Credit notes | Verified. ibr-158-ae (reason, 381 only), ibr-055-ae (BillingReference required unless VD; forbidden with VD), ibr-001-ae (reason list). |
| Free-zone beneficiary ID | Verified. ibr-007-ae requires BuyerCustomerParty PartyIdentification ID. |
| Export | Verified. No rule forces a category or endpoint; ibr-152-ae needs delivery address unless AE; ibr-135-ae relaxes buyer ids for exports. Predefined endpoints per BIS 1.5.3. |
| Scenario structure | Verified. ibr-137-ae (principal), ibr-138-ae (period), ibr-142-ae and ibr-152-ae (delivery), ibr-126-ae (base quantity and gross price). |
| Advance/retention | Not covered by any vendored rule or example. Unresolved as in the spec. |
| Self-billing | Verified: billing package rejects 389 and 261 via ibr-cl-01 while profile rules accept selfbilling identifiers. Separate specialization not vendored. |
