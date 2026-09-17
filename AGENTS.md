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

## Ground rules

Evidence before claims. Check a framework detail in the pinned source and cite the file and line rather than trusting memory. Label what you record as Verified, Proposed, or Unresolved.

Branches follow the Frappe apps: `develop` is where work lands, `version-16` will carry releases. Every change goes through a pull request with a review.

Writing style is in `docs/spec.md` section 1.4. Plain short sentences, no em dashes, no tool names or credits anywhere in the app content or the commit messages.
