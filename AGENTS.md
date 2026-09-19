# Working on this app

Read `docs/build-state.md` first. It names the current phase, the packet in hand, what was checked, and the next step. Do one packet at a time and finish it before starting another.

## Records

| File | What it holds |
| --- | --- |
| `docs/spec.md` | The design baseline. Do not copy it into other files. |
| `docs/build-state.md` | Where the work stands right now. Keep it under 80 lines. |
| `docs/decisions.md` | Decisions and open questions, each with its evidence and status. |
| `docs/source-map.md` | Where every canonical value comes from in ERPNext. |
| `docs/operations.md` | Running it: enabling production sending, restoring, pausing, what to watch. |
| `docs/capacity.md` | What was measured, on what machine, and what was not. |
| `docs/standards-lock.json` | The pinned official files with their checksums and the last run results. |
| `uae_compliance/standards/NOTICES.md` | Where the official files came from and under what terms. |

## Commands

Run everything CI runs, from the repository root:

```bash
sh scripts/check.sh
```

On the development bench, point it at the bench environment:

```bash
PYTHON=/Users/aslam/frappe-local/loc16/env/bin/python RUFF=/Users/aslam/frappe-local/loc16/env/bin/ruff sh scripts/check.sh
```

It runs each step on its own, prints pass or fail per step with the output of anything that failed, and exits non-zero if any step failed. Read its verdict, not the last line of a single command. A tool can print a cheerful final line and still exit with a failure, which is how a red build once reached the repository.

The individual steps, if you need one on its own:

```bash
ruff check . && ruff format --check .
python -m unittest discover -s uae_compliance/domain -t . -p 'test_*.py'
python scripts/standards/test_validate_examples.py   # checks on the harness itself
python scripts/standards/check_lock.py               # every pinned file still matches its checksum
python scripts/standards/validate_examples.py        # all official examples
python scripts/standards/validate_examples.py --negative
python scripts/standards/validate_examples.py --determinism
```

## Site tests

`scripts/check.sh` runs without a database, so it cannot cover anything that needs a site. Those tests live in `uae_compliance/tests/` and run on a bench:

```bash
bench --site uae.local run-tests --app uae_compliance
```

The site needs `allow_tests` turned on, or the `CI` environment variable set:

```bash
bench --site uae.local set-config allow_tests true
```

The test runner disables the scheduler and writes to the site, so point it at a throwaway site, not at anything you care about.

`uae_compliance/tests/` has no `__init__.py` on purpose. Frappe's runner finds `test_*.py` by walking the app directory and imports it as a namespace package. `unittest discover`, which the `ci` job uses, skips any directory without an `__init__.py`, so the pure Python job never tries to import Frappe. Adding an `__init__.py` there would break the `ci` job.

The `site-tests` job in `.github/workflows/site-tests.yml` does the same thing on a clean machine. It pins Frappe and ERPNext by tag and checks the resulting commits before it creates the site.

## A real invoice to check against

Extraction is only worth trusting against an invoice ERPNext actually posted.
This builds one, matching the first worked example in spec 5.3:

```bash
bench --site uae.local console
```

```
>>> from uae_compliance.development.build_invoice import run
>>> run()
```

It uses its own company, so it does not collide with the site tests. Safe to
run again.

## Reading lists

`frappe.get_all` does not check permissions and `frappe.get_list` does. That
is the framework's own design, not an oversight, and both are correct in
different places.

Anything a person reads uses `get_list`: the reports and the whitelisted
methods. A restricted user asking for a readiness report must not be handed
another company's invoices, and `get_all` would hand them over.

The workers use `get_all` on purpose. A scheduled job has no session to
check against and has already worked out what it is allowed to touch.

## Companies on the development site

`UAE Peppol Test Company` belongs to the site tests. Taking it, or binding it
to a seller profile, makes those tests fail in ways that look unrelated to
whatever you were doing.

The demo builders use their own: `Peppol Demo Co` for selling and
`Peppol Buying Demo` for receiving.

## Branching

Fetch immediately before branching. `git fetch origin && git checkout -B <name> origin/develop`.
A stale remote ref makes a branch that silently lacks the last merge, and the
first sign of it is a confusing failure somewhere unrelated.

## Ground rules

Evidence before claims. Check a framework detail in the pinned source and cite the file and line rather than trusting memory. Label what you record as Verified, Proposed, or Unresolved.

Branches follow the Frappe apps: `develop` is where work lands, `version-16` will carry releases. Every change goes through a pull request with a review.

Writing style is in `docs/spec.md` section 1.4. Plain short sentences, no em dashes, no tool names or credits anywhere in the app content or the commit messages.
