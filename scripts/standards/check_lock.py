"""Check the vendored standards artifacts against docs/standards-lock.json.

Recomputes SHA-256 for every path in the lock's "files" map, reports
mismatches and missing files, and reports files under
uae_compliance/standards that the lock does not list. Exits 0 only when
everything matches. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "docs" / "standards-lock.json"
STANDARDS_ROOT = REPO_ROOT / "uae_compliance" / "standards"
# Notices and other prose under the standards folder are not official artifacts.
UNLISTED_ALLOWED_SUFFIXES = {".md", ".txt"}


def sha256(path: Path) -> str:
	digest = hashlib.sha256()
	with path.open("rb") as handle:
		for chunk in iter(lambda: handle.read(1 << 20), b""):
			digest.update(chunk)
	return digest.hexdigest()


def main() -> int:
	if not LOCK_PATH.is_file():
		print(f"missing lock file: {LOCK_PATH.relative_to(REPO_ROOT)}")
		return 1
	lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
	files = lock.get("files")
	if not isinstance(files, dict) or not files:
		print("lock has no files map")
		return 1

	problems = 0
	for rel in sorted(files):
		path = REPO_ROOT / rel
		if not path.is_file():
			print(f"missing: {rel}")
			problems += 1
			continue
		actual = sha256(path)
		if actual != files[rel]:
			print(f"mismatch: {rel}")
			print(f"  lock   {files[rel]}")
			print(f"  actual {actual}")
			problems += 1

	listed = set(files)
	for path in sorted(STANDARDS_ROOT.rglob("*")):
		if not path.is_file() or path.suffix in UNLISTED_ALLOWED_SUFFIXES:
			continue
		rel = path.relative_to(REPO_ROOT).as_posix()
		if rel not in listed:
			print(f"unlisted: {rel}")
			problems += 1

	print(f"checked {len(files)} listed files, {problems} problems")
	return 1 if problems else 0


if __name__ == "__main__":
	raise SystemExit(main())
