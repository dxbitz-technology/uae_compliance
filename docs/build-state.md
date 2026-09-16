# Build state

Phase: P00 Baseline. State: In progress.
Branch: main, local repository only. No remote, protected branch, or CI exists yet (D004).
Last verified code commit: none. First P00 commit pending.
Development site: uae.local on bench /Users/aslam/frappe-local/loc16. Frappe v16.22.0 (567c05b), ERPNext v16.26.2 (d1d3b24), Python 3.14.5, MariaDB 12.2.2, Node 24.16.0, macOS arm64 development host. This host is not the spec 11.2 reference host.

## Packet P00 Baseline

Requirement IDs: spec 0, 1.1, 1.3, 1.4, 3, 4.3, 6.1, 6.2, 7.2 (hook facts only), 11.2 (workload record), 12.2 P00, 13 A01, 14.

Expected behavior: repository baseline, pinned sources with hashes, verified XML runtime, official positive and negative example runs, recorded decisions and unresolved facts. No application feature, DocType, hook, fixture, or UI.

Affected interfaces: app metadata (hooks.py, pyproject.toml, modules.txt, license.txt), docs records, scripts/standards evidence tooling, vendored official artifacts under uae_compliance/standards.

Likely files: docs/spec.md, docs/build-state.md, docs/decisions.md, docs/standards-lock.json, AGENTS.md, scripts/standards/validate_examples.py, scripts/standards/check_lock.py, uae_compliance/standards/pint_ae/1.0.4, uae_compliance/standards/ubl/2.1/xsd.

Checks:

- C1 Every hash in docs/standards-lock.json matches the vendored artifact. check_lock.py exits 0.
- C2 saxonche 13.0.0 imports and executes an XSLT 2.0 stylesheet inside the bench env.
- C3 Every official example passes UBL 2.1 XSD and both Schematron layers with zero fatal failed asserts.
- C4 Altered negative examples fail on the expected official rule IDs.
- C5 Frappe v16 facts for hook order, enqueue after commit, Password storage, and private File access cite file and line in the pinned checkout.
- C6 ERPNext v16 facts for tax calculation order, item_wise_tax_detail shape, discount handling, and Quick Entry class cite file and line in the pinned checkout.
- C7 uae.local has no Custom Field, Property Setter, Server Script, or Client Script on the section 4.3 DocTypes beyond what ERPNext itself installs.
- C8 House style holds: no em dashes, tool branding, or co-author trailers in repository content or commits.

Exclusions: no DocTypes, roles, fixtures, hooks, JavaScript, or v15 lane work. No provider or MoF contact. No production, remote repository, or destructive actions.

## Outcomes

Pending.

## Blockers

- No remote repository, protected main, or CI. Owner: maintainer. Consequence: the 1.1 review gate cannot be recorded against a pull request; local commits only.
- No Frappe v15 bench on this host. Consequence: the v15 lane stays unverified (spec 3).
- No /etc/hosts entry for uae.local and no sudo in this session. Consequence: browser access to the site needs a hosts entry from the maintainer or a separate serve port. Not needed for P00.

## Next action

Collect P00 evidence, review it, record outcomes here, then request maintainer acceptance before P01.
