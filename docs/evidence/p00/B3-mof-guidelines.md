# B3: Fact extraction from MoF UAE Electronic Invoicing Guidelines v1.1 (spec source S02)

Phase: P00 Baseline. Task B3.
Supports spec sections 2.1, 2.3, 4.1, 6.2, 6.3, 8.1, 10.2.
Nothing was written into the repository.

## 0. Source and method

| Item | Value | Status |
| --- | --- | --- |
| File | scratch/mof-guidelines-v1.1.pdf | Verified |
| SHA-256 | f84f452ae1fe9db6cf7af9bb894e5652c72f08fff44018208f9e9874f5b061bf (matches task) | Verified (shasum -a 256) |
| Title | "UAE Electronic Invoicing Guidelines" (p1) | Verified |
| Version | "Version V 1.1" (p1) | Verified |
| Date | "01 June 2026" (p1) | Verified |
| Page count | 51. Footer on every page reads "Page N of 51"; pdfinfo reports Pages: 51 | Verified |
| Issuing body | Body text calls the publisher "the Ministry", defined as Ministry of Finance (p6), and points to www.mof.gov.ae/eInvoicing (p41). The title page carries no extractable issuer text (logo is likely an image). PDF metadata: Creator Microsoft Word for Microsoft 365, CreationDate 2026-06-01 10:03:49 +04 | Verified from body text; title page issuer line Unresolved (image only) |
| Extraction | pdftotext (poppler, /opt/homebrew/bin/pdftotext) with -layout, one file per page: scratchpad/mof_pages/pNN.txt. Page numbers below are PDF page numbers and match the printed footer | Verified |

Extraction limits: the corner-model diagram (p10) and the EmaraTax screenshots (p39) are images with no extractable text. The responsibilities table on p11 contains a broken Word cross-reference ("Error! Bookmark not defined.") in the Buyer column of row 2; the source PDF itself carries this artifact.

Legend for statuses: Verified = seen in the PDF text at the cited page. Unresolved = the guideline does not establish it; the note says what would resolve it. Proposed = a recommendation from this extraction, not a claim about the guideline.

## 1. Definitions and identity

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F1.1 | TIN is "a unique 10-digit identifier and the first 10 digits of the 15-digit TRN" issued to all entities registered with FTA | p7 | Verified |
| F1.2 | TRN: a unique number issued by FTA for each Person registered for Tax purposes. No format is given beyond the 15-digit reference in the TIN definition | p7 | Verified |
| F1.3 | Participant Identifier (also called End Point ID): a unique reference issued by FTA during onboarding, used to identify a Person or Government Entity on the Peppol network; it is 0235 followed by the 10-digit TIN | p6 | Verified |
| F1.4 | The Participant Identifier for Electronic Invoicing is the Person's TIN. Anyone registered with FTA for any tax type already has a TIN | p3 | Verified |
| F1.5 | A Person in scope but not required to register for any tax type must register with FTA to obtain a TIN (generate a TIN through EmaraTax) | p3, p40 | Verified |
| F1.6 | Tax Group: two or more Persons registered with FTA as a single Taxable Person under the VAT Decree-Law | p7 | Verified |
| F1.7 | A Tax Group member's TIN is the first 10 digits of its own TRN, not the first 10 digits of the Tax Group representative's TRN | p3 | Verified |
| F1.8 | Each member of a Tax Group must be onboarded separately. Each member has its own TIN, which generates its individual Peppol participant identifier. Members may onboard with different ASPs | p38 | Verified |
| F1.9 | Sample invoice shows seller and buyer each identified by TRN (15 digits ending 03, for example 123456789012003), a legal registration number and type (Trade License), an Authority name, and an Electronic address of the form 0235:<10 digits>. In the sample the 10 digits equal the first 10 digits of the TRN | p34 | Verified (sample data only) |
| F1.10 | The guideline does not state which TRN (member's own or Tax Group's) appears in the TRN field of an e-invoice issued by a Tax Group member, nor whether the TIN must equal the first 10 digits of the TRN shown on that invoice | none | Unresolved. Resolve from the PINT-AE Data Dictionary and business rules (S03/S04/S05 sources) or FTA guidance on Tax Group invoicing. Affects spec 4.1 (Seller Profile, no VAT-group identity merging) and 6.2 (no unconditional TIN/TRN prefix equality) |
| F1.11 | Endpoint scheme is 0235 for UAE participants. The guideline gives no other scheme for foreign buyers; for exports it gives a predefined fallback endpoint instead (see F6.11) | p6, p28 | Verified |
| F1.12 | Central Register: the Ministry's repository listing ASPs and the End Users onboarded by those ASPs | p4 | Verified |
| F1.13 | UUID: a 128-bit identifier that the Electronic Invoicing System creates for each Tax Invoice, in addition to the invoice sequential number. Creating the UUID is the ASP's responsibility | p8, p11 | Verified |
| F1.14 | Other defined terms: Business, Business Transaction, Person (natural or juridical), Taxable Person (VAT registered or obliged, or subject to Corporate Tax), Revenue (gross income in the most recent Accounting Period), Issuer, Recipient, End User, Commercial Invoice (an invoice that is not a Tax Invoice), Provisional Invoice, PINT-AE (UAE requirements defined in a Data Dictionary), Electronic Invoice Data (mandatory data transmitted to the ASP) | p4 to p8 | Verified |

## 2. Roles and model

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F2.1 | Five corner model: C1 Supplier, C2 Supplier's ASP, C3 Recipient's (buyer's) ASP, C4 Recipient (buyer), C5 Federal Tax Authority | p4 | Verified |
| F2.2 | Flow: C1 submits invoice data to C2 in an agreed format; C2 validates and converts to the UAE standard XML if needed; C2 transmits XML to C3; in parallel C2 reports Tax Data to C5; C3 validates and confirms to C2; C3 delivers to C4 in an agreed format; on successful validation C3 also reports Tax Data to C5; on failed validation C3 confirms electronically to C2 and C5 and does not report Tax Data; C5 confirms to C2 and to C3 once Tax Data is reported; C2 forwards confirmations to C1; C3 forwards confirmations to C4 | p10, p11 | Verified |
| F2.3 | Corner 5 (FTA) receives "Tax Data" reported by C2 and by C3, not the exchanged document delivery itself. The p10 text names the C2 to C3 step as transmission of the Electronic Invoice and the C2/C3 to C5 steps as reporting of Tax Data. Appendix 4 also uses the phrase "Electronic Invoices / Tax Data Documents" for what is transmitted to the Authority | p10, p11, p48 | Verified |
| F2.4 | Exchange versus reporting: the guideline treats them as separate outcomes with separate confirmations. Testing must cover exchange success or failure confirmations (step iii) and Tax Data reporting success or failure confirmations (step vi) separately | p40, p41 | Verified |
| F2.5 | Deemed supply case: where no invoice is issued to the recipient there is no exchange, only reporting to FTA by the supplier's ASP | p26 | Verified |
| F2.6 | Accreditation: official approval issued by the Ministry to a Service Provider under MD No. 64 of 2025. ASP: a Service Provider granted Accreditation | p4 | Verified |
| F2.7 | A Person must appoint only one ASP for both sending and receiving Electronic Invoices | p14, p39 | Verified |
| F2.8 | Onboarding is initiated by the Person (not the ASP) through EmaraTax, by the Account admin of the Taxable Person: E-INVOICING tile, select ASP, "Proceed to ASP", redirected to the ASP portal. Contract and commercial obligations with the ASP must be complete before onboarding | p21, p38, p39 | Verified |
| F2.9 | On completion of onboarding the ASP shares the Participant Identifier with the Person | p45 | Verified |
| F2.10 | Changes in circumstances (registering for VAT, joining or leaving a Tax Group, deregistering, closing) must be updated with the ASP through the EmaraTax reverification/offboarding process | p21, p41, p45 | Verified |
| F2.11 | Responsibilities table: exchange and reporting including receiving confirmations rests with Supplier (and Buyer for self-billed only); calculating all invoice values rests with Supplier (and Buyer, self-billed); secure transmission using encryption rests with ASP; agreeing business-specific data security requirements rests with Supplier and Buyer; contacting the buyer to gather its participant identifier rests with Supplier; looking up the participant identifier rests with ASP; generating a UUID rests with ASP. Footnote 2: ASPs perform these activities but the compliance obligation stays with the supplier (or buyer for self-billed) | p11 | Verified |
| F2.12 | ASP obligations listed: maintain accreditation criteria and renewals; onboard clients; provide the Participant Identifier; facilitate document exchange; report Tax Data for each individual Electronic Invoice in a timely manner; use the latest specification version; comply with Peppol standards; technical support; security monitoring and data protection; notify the Person and FTA (e-invoicingsupport@tax.gov.ae) of service disruptions; exchange and report delayed invoices after resumption | p45, p46 | Verified |
| F2.13 | Persons must ensure receipt of confirmation messages from the ASP for all Tax Data that must be reported to FTA, and ensure the ASP exchanges and reports pending invoices after a disruption | p45 | Verified |
| F2.14 | Ministry role: regulatory framework, standards, ASP accreditation, compliance monitoring, coordination with Peppol. FTA role: registration and TIN/TRN generation, onboarding through EmaraTax, infrastructure, compliance monitoring, data analysis, support. Peppol role: standards, access point requirements, testing and certification, participant identifier creation with ASPs, ASP compliance monitoring | p44, p46 | Verified |
| F2.15 | Framework supports Arabic and English | p11 | Verified |

## 3. Scope

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F3.1 | Electronic Invoicing is mandatory for any Person conducting Business in the UAE, for every Business Transaction, regardless of VAT registration status and regardless of whether the Person is established in the UAE, unless specifically excluded (Article 4 of MD No. 243 of 2025; Chapter 7) | p3, p14 | Verified |
| F3.2 | Transaction matrix: in scope B2B, B2G, G2B, G2G. Out of scope: B2C, G2C, C2B, C2G, C2C | p14 | Verified |
| F3.3 | Supplies to or from natural persons not in Business are out of scope, including where a billing agent invoices or collects for such a supply; neither supplier nor agent must issue an Electronic Invoice for a consumer supply | p14 | Verified |
| F3.4 | Supplies to Government Entities (for example through government procurement portals) are in scope | p14 | Verified |
| F3.5 | A customer's onboarding status or tax registration status does not affect the supplier's Electronic Invoicing obligation for a Business Transaction | p14 | Verified |
| F3.6 | Non-VAT-registered Persons in scope issue Commercial Invoices (and Electronic Credit Notes) as Electronic Invoices; traditional pdf or paper Commercial Invoices must be replaced | p22, p23 | Verified |
| F3.7 | Investment holding companies with only passive income and no Business Transactions are out of scope; recharges of costs to third or related parties are Business Transactions and bring them in scope | p15 | Verified |
| F3.8 | Intra-VAT-group Business Transactions are in scope and not excluded for being intra-group (with a grace period, see F4.6) | p15, p16 | Verified |
| F3.9 | A Person without a place of residence in the UAE that must issue Tax Invoices under the VAT Decree-Law must issue them as Electronic Invoices | p16 | Verified |
| F3.10 | Exclusions: (a) Government Entity transactions in a sovereign capacity not in competition with the private sector; (b) international passenger transport by an Airline with an Electronic Ticket, and ancillary services with an Electronic Miscellaneous Document; (c) temporary exclusion for international goods transport by an Airline with an Airway Bill, for 24 months from the date in Article 5 of MD No. 244 of 2025; (d) financial services exempt under Article 42 of the VAT Executive Regulation, and exempt financial services to non-residents that qualify as zero-rated exports under Article 31; standard-rated financial services are not excluded even when zero-rated as exports; (e) other exclusions the Minister may add by Ministerial Decision | p17, p18 | Verified |
| F3.11 | FTA administrative exceptions for Tax Invoices and Tax Credit Notes under the VAT Executive Regulation do not apply to Electronic Invoices or Electronic Credit Notes | p17 | Verified |
| F3.12 | Import of Concerned Goods and Concerned Services (Article 48 reverse charge on imports) is not subject to any Electronic Invoicing requirement | p30 | Verified |
| F3.13 | Revenue threshold used for phasing: AED 50,000,000 annual Revenue (see F4.3, F4.4) | p19 | Verified |
| F3.14 | Self-billing of electronic Tax Invoices requires the buyer to be on the Electronic Invoicing System; once the supplier is in mandatory scope this extends to all its Business Transactions including self-billed ones | p23 | Verified |

## 4. Rollout dates, phases, and thresholds (record only; the app must not hardcode these)

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F4.1 | Pilot Programme starts 1 July 2026; participation is by written agreement after the Ministry contacts the Person; participants must meet all technical requirements | p19 | Verified |
| F4.2 | Voluntary implementation open to all Persons regardless of Revenue from 1 July 2026; penalties apply only from the Person's mandatory date | p19 | Verified |
| F4.3 | Mandatory: Person with annual Revenue of AED 50,000,000 or more: appoint an ASP by 31 July 2026; implement by 1 January 2027 | p19 | Verified |
| F4.4 | Mandatory: Person with annual Revenue below AED 50,000,000: appoint an ASP by 31 March 2027; implement by 1 July 2027 | p19 | Verified |
| F4.5 | Mandatory: Government Entity (no Revenue threshold): appoint an ASP by 31 March 2027; implement by 1 October 2027 | p20 | Verified |
| F4.6 | Intra-VAT-group grace period: 24 months from 01 January 2027, during which MD No. 243 of 2025 obligations need not be implemented for transactions between members of the same VAT group. Timing only; scope unchanged; after expiry full application per the member's mandatory phase | p16 | Verified |
| F4.7 | Airline Airway Bill exclusion lasts 24 months from the date in Article 5 of MD No. 244 of 2025 (the date itself is not stated in the guideline) | p17 | Verified; the underlying date is Unresolved here, resolve from MD No. 244 of 2025 |
| F4.8 | HSN codes are currently optional; a mandatory timeline will be announced later | p37 | Verified |
| F4.9 | Summary text: mandatory for Persons from January 2027 onwards and for Government Entities from October 2027 onwards | p20 | Verified |
| F4.10 | The detailed phase rules are stated to come from MD No. 244 of 2025 | p3, p19 | Verified |

## 5. Timing

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F5.1 | The guideline states no numeric issuance deadline (no day count after supply or payment) for Electronic Invoices. Keyword sweep for "days", "deadline", "14", "within N" across all 51 pages found no such rule | none | Unresolved. Resolve from VAT Decree-Law (Tax Invoice timing) and MD No. 243 of 2025. Affects spec 2.1 issuance/date policy |
| F5.2 | The guideline states no numeric reporting deadline. ASPs must report Tax Data "in a timely manner" and inform Persons of successful transmission to the Authority "on an event-driven basis and without undue delay" | p45, p48 | Verified (qualitative only); numeric deadline Unresolved, resolve from PASR or MD No. 243 |
| F5.3 | Advance payments: a tax invoice must be issued "at the time of receipt" of the advance | p49 | Verified |
| F5.4 | Retention: a separate Electronic Invoice for the retained amount is issued when the Buyer becomes liable to release and settle it | p51 | Verified |
| F5.5 | Electronic Invoicing requirements differ from VAT Tax Invoice requirements. Electronic Invoicing does not remove the obligation to issue a Tax Invoice or Tax Credit Note; under Article 65(5) of the VAT Decree-Law a Person subject to the system must issue them in the form of an Electronic Invoice or Electronic Credit Note | p15 | Verified |
| F5.6 | The revised VAT definition of Tax Invoice includes an Electronic Invoice, so a separate Tax Invoice may not be needed when the buyer has implemented Electronic Invoicing and the Electronic Invoice meets Article 65 VAT Decree-Law and Article 59 VAT Executive Regulation | p23 | Verified |
| F5.7 | Where the buyer has not implemented Electronic Invoicing, a regular Tax Invoice (for example pdf) is required in addition to the electronic Tax Invoice | p15, p23 | Verified |
| F5.8 | Date of supply, if different from the issue date, goes in the "VAT Point Date" field | p37 | Verified |
| F5.9 | Voluntary and pilot participants must meet all technical requirements once they start | p19 | Verified |

## 6. Documents and scenarios

### 6a. Document categories

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F6.1 | Six categories: Electronic Tax Invoice; Electronic Tax Credit Note; Commercial Invoice; Electronic Credit Note; Self-billed electronic Tax Invoice; Self-billed electronic Tax Credit Note. Self-billing is not applicable to Commercial Invoices or Electronic Credit Notes | p22 | Verified |
| F6.2 | No category for provisional invoices; every provisional invoice must be an Electronic Invoice; adjustments are made by an Electronic Credit Note or an additional Electronic Invoice | p22 | Verified |
| F6.3 | Commercial Invoice covers sales not requiring a Tax Invoice under the VAT Decree-Law (exempt, out of scope, or supplier not VAT registered) | p22, p23 | Verified |
| F6.4 | An electronic Tax Invoice may include non-Taxable Supplies alongside Taxable Supplies; no separate invoice is needed | p23 | Verified |
| F6.5 | An electronic Tax Credit Note is issued by a Taxable Person when a reduction of Output Tax occurs (footnote to Articles 62 and 70 of the VAT Decree-Law) | p23 | Verified |
| F6.6 | Sample header values: Business Process type urn:peppol:bis:billing; Specification Identifier urn:peppol:pint:billing-1@ae-1; Invoice Type Code 380; Invoice transaction type code shown as an 8-character string "00000000"; Invoice Currency Code AED; VAT Currency Code AED; UUID present; Frequency of Billing and Billing Period present; Paid Amount deducted to reach Total Payable Amount | p34 | Verified (sample only; codes for other categories are not given in this guideline) |
| F6.7 | The guideline gives no document type code for credit notes or commercial invoices; it refers to Peppol PINT-AE billing specifications for content by document type and scenario, and to a separately published Ministry mandatory-fields document | p12, p22, p33 | Verified that it defers; codes Unresolved here, resolve from S03 sources |

### 6b. Scenarios (Chapter 10.4: eight scenarios)

| ID | Scenario | Instruction in the guideline | Applies to Commercial Invoices | Page | Status |
| --- | --- | --- | --- | --- | --- |
| F6.8 | Free Zone | Where the customer is a Free Zone entity the invoice requires beneficiary details in addition to the customer. Customer is the PO issuer or contracting party; if the ultimate beneficiary differs, record the beneficiary; if the customer declares another Person as end user, record that Person as beneficiary. If beneficiary equals customer, Beneficiary Name and Beneficiary ID may mirror the customer. For an individual consumer end customer, use name and available ID or note that no registered ID exists | Yes | p25, p26, p37 | Verified |
| F6.9 | Deemed supply | Buyer electronic address is always 0235:9900000097 regardless of supplier identity. Where no invoice is issued to the recipient, no exchange, only reporting by the supplier's ASP | No | p26 | Verified |
| F6.10 | Margin scheme | VAT amount is not displayed; the amount shown should be "0" even though PINT-AE mandates VAT information | No | p26, p27 | Verified |
| F6.11 | Exports | The VAT Tax Invoice for an export is issued as an Electronic Invoice and may be given to Customs. If the buyer has no Peppol ID, the predefined endpoint 0235:9900000099 is mandatory. Customs Reference Number and Incoterms fields are available | No | p28, p36 | Verified |
| F6.12 | Summary invoice | Some document-level fields may be zero or positive to pass Peppol validation. A negative total payable must be documented as an electronic Credit Note, also for summary invoices | Yes | p27 | Verified |
| F6.13 | Continuous supply | Retention: a separate commercial document details the milestone calculation and retention deduction; those calculations must not appear on the Electronic Invoice; when the retention becomes payable an electronic Tax Invoice with applicable VAT is issued | Yes | p27 | Verified |
| F6.14 | Agent billing (disclosed agent) | Responsibility to issue remains with the supplier even if the agent issues on its behalf. Not applicable to undisclosed agents | Yes | p27, p28 | Verified |
| F6.15 | Supply through e-Commerce | Defined by Ministerial Decision No. 26 of 2023. Responsibility remains with the supplier even if the platform issues on its behalf | Yes | p28 | Verified |
| F6.16 | Multiple scenarios may apply to one invoice; each applicable scenario's requirements must all be included | all | p29 | Verified |

### 6c. Tax categories (Chapter 10.5)

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F6.17 | Six tax categories, applicable at supply level for Tax Invoices and Commercial Invoices: Standard Rate; Exempt from VAT (Article 46); Goods and services outside the scope of VAT; Reverse Charge (domestic, certain goods); Zero rated (Article 45); Margin scheme (Article 43). The guideline gives descriptions only, no category code letters | p30 | Verified; code letters Unresolved here, resolve from S04 |
| F6.18 | Domestic reverse charge category is used only for supplies of certain goods between two VAT Registrants. The invoice excludes VAT, includes a narrative giving the reason, and must include the type of goods as a reference. Goods: electronic devices (CD 91/2023, MD 262/2023); precious metals and stones (CD 127/2024); crude or refined oil, natural gas, pure hydrocarbons (Article 48); metal scrap (CD 153/2025) | p30, p31 | Verified |

### 6d. Other documented cases (Chapter 12.2 constraints and considerations, items 1 to 28)

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F6.19 | TRN is required on electronic Tax Invoices and Tax Credit Notes; not mandatory for Commercial Invoices or for out-of-scope and exempt transactions | p35 | Verified |
| F6.20 | No limit on the number of lines | p35 | Verified |
| F6.21 | One electronic Tax Credit Note may reference multiple preceding electronic Tax Invoices; a credit note may be partial | p35 | Verified |
| F6.22 | Rounding applies only at invoice total level, up to 2 decimals; not at tax category or line level. "Rounding Amount" field is optional and issuer-provided | p35, p37 | Verified |
| F6.23 | Item type field: 'G' goods, 'S' services, 'B' both | p35 | Verified |
| F6.24 | Surcharges (for example Dubai Municipality surcharge, tourism levies) go under Document Level Charges | p35 | Verified |
| F6.25 | Import VAT paid by an agent (Article 50 VAT Executive Regulation): the agent issues an Electronic Invoice and may show the VAT paid under Document Level Charges | p35 | Verified |
| F6.26 | Triangular sales: TRN or TIN of the goods recipient may go in "Delivery to Party ID" in Delivery Information | p36 | Verified |
| F6.27 | Discounts: line level in Line Level Allowances with Invoice Line Allowance Reason; document level in Document Level Allowances with Document Level Allowance Reason; a code list exists for allowance reason | p36 | Verified |
| F6.28 | Volume discounts: Electronic Credit Notes with Credit note reason code set to volume discount | p36 | Verified |
| F6.29 | Batch Number field available | p36 | Verified |
| F6.30 | VAT amount and total payable in AED are mandatory for each supply regardless of invoice currency: "VAT Line Amount" and "Amount Payable" fields; supplier is responsible for correctness | p36 | Verified |
| F6.31 | Non-AED document currency: gross total payable in AED goes in "Invoice Total Amount with VAT in Tax Accounting Currency"; conversion at the Central Bank approved rate (Article 69 VAT Decree-Law); "Tax Accounting Currency" field is mandatory when the document currency is not AED | p36 | Verified |
| F6.32 | Contract Value field must be updated in the next invoice when the project value changes | p37 | Verified |
| F6.33 | Multiple payment methods via "Payment Instructions"; multiple payment dates via "Invoice Terms" | p37 | Verified |
| F6.34 | Authority name (trade license issuing authority) is free text entered by the issuer; no code list | p37 | Verified |
| F6.35 | Industry-specific fields go through the ASP; Persons may not add their own optional fields to PINT-AE | p37 | Verified |
| F6.36 | Insurance: reinsurance statements with VAT implications must be Electronic Invoices; insurer and broker decide who issues | p37 | Verified |
| F6.37 | XML samples are in the PINT-AE "Download resources"; the Ministry also published a mandatory-fields document (link not extractable) | p33 | Verified |
| F6.38 | Electronic Invoices are XML and carry no QR code or barcode | p12 | Verified |

## 7. Advance payments and retention

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F7.1 | Chapter 12.2 item 9: adjustment amounts for advances go in the "Paid Amount" field of the final invoice, and the original advance invoice should be referenced in "Preceding Invoice Reference". Item 10: the same two fields serve prepayments | p35 | Verified |
| F7.2 | Appendix 5: on receipt of an advance a tax invoice must be issued at the time of receipt. The final invoice covers only the remaining balance, not the full value. A reference to the advance invoice may be given under IBT-25 and IBT-26, or a note in IBT-022. cbc:PrepaidAmount may be left blank because the final invoice already shows only the outstanding amount | p49 | Verified |
| F7.3 | Appendix 5 example: contract AED 10,000 plus 5% VAT; advance invoice ADV-001 (type 380) for 1,000 plus 50 VAT, payable 1,050; final invoice Final-001 (type 380) with a BillingReference to ADV-001, LineExtensionAmount 9,000, tax 450, payable 9,450 | p49, p50 | Verified |
| F7.4 | Two mechanisms are described for advances: item 9 (full value with Paid Amount deduction plus preceding reference) and Appendix 5 (balance-only final invoice with PrepaidAmount blank). The guideline does not say which applies when, or whether both remain acceptable | p35, p49 | Verified that both texts exist; precedence Unresolved. Resolve with the FTA or ASP before enabling the advance capability row (spec 2.3, 6.2) |
| F7.5 | Retention (Appendix 5): businesses may keep existing practices if VAT and Electronic Invoicing compliant. Acceptable practice: issue an Electronic Invoice for the amount payable after adjusting for retention; issue a separate Electronic Invoice for the retained amount when the Buyer becomes liable to release and settle it | p51 | Verified |
| F7.6 | Retention (Chapter 10.4 row 5): milestone and retention calculations belong on a separate commercial document, not on the Electronic Invoice; the retention release is an electronic Tax Invoice with applicable VAT | p27 | Verified |
| F7.7 | Sample invoice shows "(LESS): Paid Amount 1,000.00" reducing Total Including VAT 10,500.00 to Total Payable Amount 9,500.00 | p34 | Verified |

## 8. Corrections

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F8.1 | Tax Credit Note (definition): a document recording any amendment to reduce or cancel a Taxable Supply, including an Electronic Credit Note | p7 | Verified |
| F8.2 | Adjustments to a provisional invoice: Electronic Credit Note or an additional Electronic Invoice | p22 | Verified |
| F8.3 | A negative total payable must be documented as an electronic Credit Note (including summary invoices) | p27 | Verified |
| F8.4 | One Tax Credit Note may reference several preceding Tax Invoices; partial credit notes are allowed | p35 | Verified |
| F8.5 | Volume discount credit notes use the Credit note reason code for volume discount | p36 | Verified |
| F8.6 | The guideline contains no debit note concept (keyword "debit" absent) and no rule on cancelling or replacing an accepted Electronic Invoice; the only uses of "cancel" are in the Tax Credit Note definition and in "VAT registration is cancelled" | none | Unresolved. Resolve from PINT-AE business rules, PASR, and VAT Decree-Law Article 70. Affects spec 8.6 |
| F8.7 | Corrections to advances: see F7.2 (reference to original invoice), no separate correction rule | p49 | Verified |

## 9. Storage, retention, and archiving

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F9.1 | Retention periods (Article 3(1) Tax Procedures Executive Regulation): 5 years after the Tax Period for a Taxable Person; 5 years from end of calendar year of creation for other Persons; 7 years from end of calendar year of creation for real estate records | p12 | Verified |
| F9.2 | Extensions: additional 4 years on dispute, ongoing audit, or notice of audit; additional 1 year from a voluntary disclosure submitted in the fifth year | p12 | Verified |
| F9.3 | Article 11 of MD No. 243 of 2025: Persons subject to the system store Electronic Invoices, Electronic Credit Notes and associated data "within the State" for the Tax Procedures Law timeline | p12 | Verified |
| F9.4 | Compliance with Article 11 is met where: records are in an electronic system preserving integrity and secure retention; the infrastructure, inside or outside the UAE, allows prompt production on request; records can be retrieved and reproduced by FTA in complete and readable form. "Within the State" is read as retrievability for FTA irrespective of server, database or cloud location | p12 | Verified |
| F9.5 | "Associated data" means only information supporting integrity, authenticity and auditability of the Electronic Invoice or Credit Note; not general business documentation | p12, p13 | Verified |
| F9.6 | The Person keeps the legal obligation; delegating storage to an ASP by contract is permitted but does not transfer the obligation. The ASP may store invoices, credit notes and associated data on the Person's behalf under the commercial agreement | p47, p48 | Verified |
| F9.7 | ASPs must keep transactional logs per transaction with unique transaction identifiers covering the end-to-end exchange and reporting cycle, statuses and routing. These are ASP operational records, not the Person's Article 11 business records; kept per the OpenPeppol Service Provider Agreement and the UAE Peppol Authority Specific Requirements (PASR) | p47 | Verified |
| F9.8 | No mandated storage layer (including C1/C4); any arrangement is acceptable if the period, integrity and security, and availability to the Authority are met | p48 | Verified |
| F9.9 | Appendix 4 heading in the TOC and on p47 reads "No. 243 of 202" (truncated year in the source) | p2, p47 | Verified (source typo) |

## 10. Data and security

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F10.1 | Secure transmission of Electronic Invoices using encryption is the ASP's responsibility | p11 | Verified |
| F10.2 | Supplier and buyer agree business-specific data security requirements with their ASPs; the readiness checklist asks whether data hosting and data security requirements were agreed with the ASP | p11, p42 | Verified |
| F10.3 | ASPs must implement security measures protecting data in transmission and storage and comply with data protection regulations | p46 | Verified |
| F10.4 | Data residency: no requirement to store on servers in the UAE; retrievability for FTA governs (see F9.4) | p12, p48 | Verified |
| F10.5 | The guideline says nothing about digital signatures or seals on Electronic Invoices (keyword sweep: no hits) | none | Unresolved. Resolve from PINT-AE and PASR |
| F10.6 | ASP validation duties stated: validate invoice data received from C1 and convert to UAE standard XML; C3 validates the received invoice before delivery and before reporting; look up the buyer participant identifier; generate the UUID; use the latest specification; comply with Peppol specifications | p10, p11, p45 | Verified |
| F10.7 | ASPs must notify Persons on an event-driven basis, without undue delay, that Electronic Invoices / Tax Data Documents were transmitted to the Authority | p48 | Verified |
| F10.8 | Service disruption: ASP notifies the Person and FTA (e-invoicingsupport@tax.gov.ae); pending invoices are exchanged and reported after resumption | p46 | Verified |

## 11. Received invoices (buyer side) and self-billing

| ID | Fact | Page | Status |
| --- | --- | --- | --- |
| F11.1 | The single appointed ASP covers receiving (accounts payable) as well as sending | p14 | Verified |
| F11.2 | Persons must agree with their ASP how they will receive Electronic Invoices issued to them by suppliers, and must test receiving an Electronic Invoice from the ASP issued by a supplier | p40, p41 | Verified |
| F11.3 | Go-live covers exchange "(sending and receiving)" and reporting | p41 | Verified |
| F11.4 | C3 (buyer's ASP) validates, confirms to C2, delivers to C4 in an agreed format, reports Tax Data to C5 on success, and forwards confirmations to C4 | p10, p11 | Verified |
| F11.5 | Buyer compliance responsibility for exchange, reporting and calculating values applies to self-billed invoices only (footnote 1) | p11 | Verified |
| F11.6 | Self-billing requires the buyer to be on the system; applies only for VAT purposes under VAT Decree-Law conditions; not available where the supplier is not VAT registered, so no self-billed Commercial Invoices; needs an agreement between supplier and buyer; the self-billed electronic Tax Invoice must meet Tax Invoice criteria | p23, p24 | Verified |
| F11.7 | A supplier in mandatory scope must check that its self-billing customers can issue self-billed Electronic Invoices, because the buyer may not yet be in mandatory scope | p23, p24 | Verified |
| F11.8 | A buyer that has not implemented Electronic Invoicing may still need a separate (non-XML) Tax Invoice or Commercial Invoice for input tax recovery, corporate tax deduction, or to understand amounts payable | p15 | Verified |
| F11.9 | Buyer without a Participant Identifier: supplier must include the predefined endpoint 0235:9900000098 | p23 | Verified |

## 12. Predefined endpoint values (consolidated, for spec 6.3)

| Value | Use | Page | Status |
| --- | --- | --- | --- |
| 0235:9900000097 | Deemed supply buyer address, always | p26 | Verified |
| 0235:9900000098 | Buyer not yet on Electronic Invoicing and without a Participant Identifier | p23 | Verified |
| 0235:9900000099 | Export where the buyer has no Peppol ID | p28 | Verified |

Spelling note: the source text prints a space after the colon at p23 ("0235: 9900000098") and p28 ("0235: 9900000099"); at p26 the value wraps to the next line after "0235:". The sample electronic addresses at p34 have no space (0235:1234567890). The exact serialized form of scheme and value is Unresolved from S02 alone; take it from the PINT-AE specification (S03 sources). Status of the digit values themselves: Verified.

## 13. Deferrals to law, Cabinet, or Ministerial decisions (instrument names as cited)

| Instrument | Where cited | What is deferred |
| --- | --- | --- |
| Ministerial Decision No. 243 of 2025 on the Electronic Invoicing System | p3, p6, p7, p12, p15, p47 | Scope, Article 4 exclusions, Issuer and Recipient definitions, Article 11 storage |
| Ministerial Decision No. 244 of 2025 on the Implementation of the Electronic Invoicing System | p3, p15, p17, p19, p20 | Phased timeline, voluntary phase participation, Article 5 date for the Airway Bill exclusion |
| Ministerial Decision No. 64 of 2025 (eligibility and Accreditation of Service Providers) | p3, p4 | ASP accreditation |
| Cabinet Decision No. 106 of 2025 (Violations and Administrative Penalties, Electronic Invoicing) | p3, p32, p38, p42 | Electronic Invoicing penalties |
| Cabinet Decision No. 40 of 2017 and amendments | p32 | VAT and Tax Procedures administrative penalties |
| Federal Decree-Law No. 8 of 2017 on VAT (VAT Decree-Law), Articles 11, 12, 43, 45, 46, 48, 62, 65, 65(5), 69, 70 | p8, p15, p23, p26, p27, p30, p31, p36 | Deemed supply, margin, zero rate, exemption, reverse charge, output tax adjustment, Tax Invoice, currency, Tax Credit Note |
| Cabinet Decision No. 52 of 2017 (VAT Executive Regulation), Articles 31, 42, 50, 59 | p8, p17, p35, p36 | Zero-rated export of services, exempt financial services, agent import VAT, Tax Invoice contents |
| Federal Decree-Law No. 28 of 2022 (Tax Procedures Law) | p7, p12, p47 | Record retention timeline |
| Cabinet Decision No. 74 of 2023 (Tax Procedures Executive Regulation), Article 3(1) | p7, p12 | Retention periods |
| Federal Decree-Law No. 47 of 2022 (Corporate Tax Decree-Law) | p5 | Taxable Person definition |
| Ministerial Decision No. 26 of 2023 (Electronic Commerce criteria) | p28 | E-commerce scenario definition |
| Cabinet Decision No. 91 of 2023, Ministerial Decision No. 262 of 2023 | p30, p31 | Reverse charge on electronic devices |
| Cabinet Decision No. 127 of 2024 | p30, p31 | Reverse charge on precious metals and stones |
| Cabinet Decision No. 153 of 2025 | p30, p31 | Reverse charge on metal scrap |
| Peppol PINT-AE billing specifications and Data Dictionary | p6, p12, p22, p33 | Field content, mandatory/optional terms, XML samples |
| UAE Peppol Authority Specific Requirements (PASR); OpenPeppol Service Provider Agreement | p47 | ASP logging obligations |
| Ministry mandatory-fields document | p33 | Mandatory field list (link not extractable) |
| Future Ministerial Decisions by the Minister | p18 | Further exclusions |

## 14. Relevance to spec sections (Proposed mapping, no spec edits made)

| Spec section | Facts that bear on it | Note |
| --- | --- | --- |
| 2.1 Company policy | F3.5, F4.1 to F4.10, F5.1, F5.5 to F5.7 | Rollout dates are facts only. No numeric issuance deadline exists in S02; the issuance/date policy needs another source (F5.1) |
| 2.3 Supported scope | F3.1 to F3.14, F6.8 to F6.16, F11.1 to F11.9 | Consumer exclusion (F3.3) supports "Individual alone does not establish consumer use" only indirectly; the guideline uses "natural persons who are not in Business". Receiving path obligations F11.1 to F11.4 |
| 4.1 Master records | F1.1 to F1.13, F2.7, F2.10 | Tax Group members have own TIN and separate onboarding (F1.7, F1.8). Which TRN appears on a member's invoice is Unresolved (F1.10) |
| 6.2 Corrections to manual | F1.7, F1.10, F6.7, F6.11, F6.17, F6.28, F7.1 to F7.6 | Advance handling has two textual variants (F7.4). Credit note volume discount reason (F6.28). Export routing fallback (F6.11) |
| 6.3 Routing and scope | Section 12 table, F2.5, F6.9, F6.11, F11.9 | Three predefined endpoint values Verified with pages. Deemed supply with no recipient invoice is report-only (F2.5) |
| 8.1 States | F2.2 to F2.5, F10.7 | Distinct exchange and reporting confirmations; C3 validation failure means no C3 reporting |
| 10.2 Artifact contract | F9.1 to F9.8, F10.1 to F10.5 | Retention periods and extensions listed; residency read as retrievability; no signature requirement stated |
