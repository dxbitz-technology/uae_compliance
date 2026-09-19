# Third-party notices for files under uae_compliance/standards

This directory holds official artifacts from third parties. The app keeps them unchanged and uses them for validation only. Each section states the publisher, the source, the checksum of the download, and the terms found in the artifacts.

## PINT AE Billing 1.0.4

Directory: `pint_ae/1.0.4/trn-invoice` and `pint_ae/1.0.4/trn-creditnote` (code lists in genericode, Schematron rules with compiled XSLT, and example documents).

Publisher as stated in the artifacts: OpenPeppol AISBL, Post-Award Coordinating Community (footer of the Peppol BIS document). The release notes state "Maintained by United Arab Emirates (UAE) Peppol Authority".

Source URL: https://docs.peppol.eu/poac/ae/pint-ae/

Download: `resources.zip`, sha256 `1e8b0bd595c672ac9d6fc886ddd0eb8027cb39a1d26bebdcb1ada37b7eee491f`, downloaded 16-09-2026.

Files kept unchanged: all 75 files under `trn-invoice` and `trn-creditnote` match the archive byte for byte. The three PDF documents in the archive (`common/docs/bis.pdf`, `compliance.pdf`, `specialized-release-notes.pdf`) are not kept in this repository.

Terms: the code lists, Schematron files, and example documents carry no license or copyright text. The only statement in the archive is the copyright notice in the BIS document, quoted verbatim:

> The copyright of PINT is owned by OpenPEPPOL and its members. OpenPEPPOL AISBL holds the copyright of this Peppol BIS.
>
> This Peppol BIS document may not be modified, re-distribute, sold or repackaged in any other way without the prior consent of OpenPEPPOL AISBL.

That statement covers the BIS document. Terms for redistribution of the technical artifacts are not stated in the downloaded artifacts; see `docs/decisions.md`.

## PINT AE Self-Billing 1.0.4

Directory: `pint_ae_sb/1.0.4/trn-invoice` and `pint_ae_sb/1.0.4/trn-creditnote` (code lists in genericode, Schematron rules with compiled XSLT, and example documents).

Publisher as stated in the artifacts: the same as PINT AE Billing above. This is a separate published specification with the same data model and its own rules, covering the self-billing invoice and the self-billed credit note.

Source URL: https://docs.peppol.eu/poac/ae/pint-ae-sb/

Download: `resources.zip`, sha256 `7e6e58f120132dd2d2a6acf21b4a9318f0d07f2685c30ff282fae0e2a6613d15`, downloaded 19-09-2026.

Files kept unchanged: all 47 files under `trn-invoice` and `trn-creditnote` match the archive byte for byte. The three PDF documents in the archive are not kept in this repository, as with the billing package.

Terms: the same as the billing package. The artifacts carry no license or copyright text of their own and the copyright notice in the BIS document applies.

## OASIS UBL 2.1 XSD

Directory: `ubl/2.1/xsd/maindoc` and `ubl/2.1/xsd/common`.

Copyright (c) OASIS Open 2013. All Rights Reserved.

Source URL: http://docs.oasis-open.org/ubl/os-UBL-2.1/ (file `UBL-2.1.zip`).

Download: `UBL-2.1.zip`, sha256 `60b80d76394a8a2add90723ecb8e0e2e9d826775de9749df37a72d60703f86ed`, downloaded 16-09-2026.

Files kept unchanged. The notice at the end of each schema file, quoted verbatim:

> OASIS takes no position regarding the validity or scope of any intellectual property or other rights that might be claimed to pertain to the implementation or use of the technology described in this document or the extent to which any license under such rights might or might not be available; neither does it represent that it has made any effort to identify any such rights. Information on OASIS's procedures with respect to rights in OASIS specifications can be found at the OASIS website. Copies of claims of rights made available for publication and any assurances of licenses to be made available, or the result of an attempt made to obtain a general license or permission for the use of such proprietary rights by implementors or users of this specification, can be obtained from the OASIS Executive Director.
>
> OASIS invites any interested party to bring to its attention any copyrights, patents or patent applications, or other proprietary rights which may cover technology that may be required to implement this specification. Please address the information to the OASIS Executive Director.
>
> This document and translations of it may be copied and furnished to others, and derivative works that comment on or otherwise explain it or assist in its implementation may be prepared, copied, published and distributed, in whole or in part, without restriction of any kind, provided that the above copyright notice and this paragraph are included on all such copies and derivative works. However, this document itself may not be modified in any way, such as by removing the copyright notice or references to OASIS, except as needed for the purpose of developing OASIS specifications, in which case the procedures for copyrights defined in the OASIS Intellectual Property Rights document must be followed, or as required to translate it into languages other than English.
>
> The limited permissions granted above are perpetual and will not be revoked by OASIS or its successors or assigns.
>
> This document and the information contained herein is provided on an "AS IS" basis and OASIS DISCLAIMS ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTY THAT THE USE OF THE INFORMATION HEREIN WILL NOT INFRINGE ANY RIGHTS OR ANY IMPLIED WARRANTIES OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.

## Runtime dependency: SaxonC-HE

Package: `saxonche` 13.0.0 (SaxonC-HE), by Saxonica.

License: Mozilla Public License 2.0. Terms: https://www.saxonica.com/license/terms.xml

The package is not vendored in this repository. It is installed as a Python dependency and runs the compiled Schematron XSLT files listed above.
