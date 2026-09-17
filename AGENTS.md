# Working on this app

Read `docs/build-state.md` first. It names the current phase, the packet in hand, what was checked, and the next step. Do one packet at a time and finish it before starting another.

## Records

| File | What it holds |
| --- | --- |
| `docs/spec.md` | The design baseline. Do not copy it into other files. |
| `docs/build-state.md` | Where the work stands right now. Keep it under 80 lines. |
| `docs/decisions.md` | Decisions and open questions, each with its evidence and status. |
| `docs/standards-lock.json` | The pinned official files with their checksums and the last run results. |
| `uae_compliance/standards/NOTICES.md` | Where the official files came from and under what terms. |

## Commands

Run these from the repository root. On the development bench use `/Users/aslam/frappe-local/loc16/env/bin/python`.

```bash
python scripts/standards/test_validate_examples.py   # checks on the harness itself
python scripts/standards/check_lock.py               # every pinned file still matches its checksum
python scripts/standards/validate_examples.py        # all official examples
python scripts/standards/validate_examples.py --negative
python scripts/standards/validate_examples.py --determinism
ruff check . && ruff format --check .
```

The same steps run in CI as one job named `ci`.

## Ground rules

Evidence before claims. Check a framework detail in the pinned source and cite the file and line rather than trusting memory. Label what you record as Verified, Proposed, or Unresolved.

Branches follow the Frappe apps: `develop` is where work lands, `version-16` will carry releases. Every change goes through a pull request with a review.

Writing style is in `docs/spec.md` section 1.4. Plain short sentences, no em dashes, no tool names or credits anywhere in the app content or the commit messages.
