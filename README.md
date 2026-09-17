## UAE Compliance

UAE Peppol e-invoicing for ERPNext. It prepares outbound sales invoices and credit notes, validates them against the official UAE rules, holds them for review, sends them through an accredited service provider, and recovers when a send goes wrong.

The app is under active development and is not ready for production use. No provider integration is in place yet.

### What it needs

Frappe and ERPNext version 16. The app pins the official PINT AE Billing 1.0.4 files and the UBL 2.1 schemas, and runs them with SaxonC-HE, which arrives with the Python dependencies.

### Installation

```bash
bench get-app https://github.com/dxbitz-technology/uae_compliance
bench --site <site> install-app uae_compliance
```

A new install starts switched off. Nothing is validated or sent until a company is set up for it.

### Working on the app

Start with `AGENTS.md` for the records and the commands. The design baseline is `docs/spec.md` and the current state is `docs/build-state.md`.

### License

AGPL-3.0-only. See `license.txt`. The official files under `uae_compliance/standards` belong to their publishers; `uae_compliance/standards/NOTICES.md` says where each came from.
