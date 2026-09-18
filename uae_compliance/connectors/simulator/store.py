"""Where the simulator keeps what it has been sent.

It is a file on disk, not a dictionary, and that is the whole point. A worker
that dies after the provider accepted a document has to be able to come back
and find that the document is there. A store that lived in the process would
disappear along with the crash and would prove nothing.

Everything written here is stamped Simulation. Nothing in it means anything
outside a test.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass

ENVIRONMENT = "Simulation"
ACCEPTED_LABEL = "Accepted by simulator"

# The identifier the simulator hands out. The registry refuses one of these on
# a Production connection, so a document invented here cannot be chased at a
# real provider.
ID_PREFIX = "SIM-"
EVENT_PREFIX = "SIM-EV-"
TOKEN_PREFIX = "sim_tok_"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
	id TEXT PRIMARY KEY,
	client_id TEXT NOT NULL,
	idempotency_key TEXT,
	number TEXT,
	media_type TEXT,
	digest TEXT,
	payload BLOB,
	behaviour TEXT NOT NULL,
	status TEXT NOT NULL,
	exchange TEXT NOT NULL,
	reporting TEXT NOT NULL,
	settled INTEGER NOT NULL DEFAULT 0,
	settle_at REAL NOT NULL DEFAULT 0,
	received_at REAL NOT NULL,
	sequence INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS documents_key ON documents (client_id, idempotency_key);
CREATE INDEX IF NOT EXISTS documents_number ON documents (number);

CREATE TABLE IF NOT EXISTS artifacts (
	identifier TEXT PRIMARY KEY,
	document_id TEXT NOT NULL,
	kind TEXT NOT NULL,
	media_type TEXT NOT NULL,
	body BLOB NOT NULL,
	present INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS events (
	event_id TEXT PRIMARY KEY,
	document_id TEXT NOT NULL,
	sequence INTEGER NOT NULL,
	kind TEXT NOT NULL,
	body TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
	token TEXT PRIMARY KEY,
	client_id TEXT NOT NULL,
	expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS counters (
	name TEXT PRIMARY KEY,
	value INTEGER NOT NULL
);
"""


@dataclass
class Document:
	id: str
	client_id: str
	idempotency_key: str | None
	number: str | None
	media_type: str | None
	digest: str | None
	behaviour: str
	status: str
	exchange: str
	reporting: str
	settled: bool
	settle_at: float
	received_at: float
	sequence: int

	def as_json(self) -> dict:
		"""What the simulator tells a caller about this document.

		Every field that says what happened also says where it happened. A
		reader who sees one of these in a log should not have to work out
		whether it was real.
		"""
		return {
			"id": self.id,
			"number": self.number,
			"status": self.status,
			"c3_mls_status": self.exchange,
			"c5_mls_status": self.reporting,
			"status_label": ACCEPTED_LABEL,
			"environment": ENVIRONMENT,
			"received_at": self.received_at,
			"sequence": self.sequence,
		}


class Store:
	"""The simulator's records, on disk, shared by whatever threads serve it."""

	def __init__(self, path: str):
		self.path = str(path)
		self._lock = threading.Lock()
		self._db = sqlite3.connect(self.path, check_same_thread=False)
		self._db.row_factory = sqlite3.Row
		with self._lock:
			self._db.executescript(SCHEMA)
			self._db.commit()

	def close(self) -> None:
		with self._lock:
			self._db.close()

	def _next(self, name: str) -> int:
		row = self._db.execute("SELECT value FROM counters WHERE name = ?", (name,)).fetchone()
		value = (row["value"] if row else 0) + 1
		self._db.execute(
			"INSERT INTO counters (name, value) VALUES (?, ?) "
			"ON CONFLICT(name) DO UPDATE SET value = excluded.value",
			(name, value),
		)
		return value

	def issue_token(self, client_id: str, seconds: float) -> tuple[str, float]:
		with self._lock:
			number = self._next("token")
			token = f"{TOKEN_PREFIX}{number:08d}"
			expires_at = time.time() + seconds
			self._db.execute(
				"INSERT INTO tokens (token, client_id, expires_at) VALUES (?, ?, ?)",
				(token, client_id, expires_at),
			)
			self._db.commit()
		return token, expires_at

	def client_for(self, token: str) -> str | None:
		"""The client this token belongs to, or nothing if it is unknown or past its time."""
		with self._lock:
			row = self._db.execute("SELECT * FROM tokens WHERE token = ?", (token,)).fetchone()
		if not row or row["expires_at"] <= time.time():
			return None
		return row["client_id"]

	def expire_tokens(self) -> None:
		"""Age every token out at once, so a test does not have to wait for one."""
		with self._lock:
			self._db.execute("UPDATE tokens SET expires_at = ?", (time.time() - 1,))
			self._db.commit()

	def add_document(self, **fields) -> Document:
		with self._lock:
			number = self._next("document")
			identifier = f"{ID_PREFIX}{number:06d}"
			record = {
				"id": identifier,
				"sequence": 0,
				"received_at": time.time(),
				"settled": 0,
				"settle_at": fields.pop("settle_at", 0.0),
				"status": fields.pop("status", "Processing"),
				"exchange": fields.pop("exchange", "pending"),
				"reporting": fields.pop("reporting", "pending"),
				**fields,
			}
			columns = ", ".join(record)
			marks = ", ".join("?" for _ in record)
			self._db.execute(f"INSERT INTO documents ({columns}) VALUES ({marks})", tuple(record.values()))
			self._db.commit()
		return self.get(identifier)

	def get(self, identifier: str) -> Document | None:
		with self._lock:
			row = self._db.execute("SELECT * FROM documents WHERE id = ?", (identifier,)).fetchone()
		return _document(row)

	def find_by_key(self, client_id: str, key: str) -> Document | None:
		with self._lock:
			row = self._db.execute(
				"SELECT * FROM documents WHERE client_id = ? AND idempotency_key = ? ORDER BY id LIMIT 1",
				(client_id, key),
			).fetchone()
		return _document(row)

	def find_by_number(self, client_id: str, number: str) -> list[Document]:
		with self._lock:
			rows = self._db.execute(
				"SELECT * FROM documents WHERE client_id = ? AND number = ? ORDER BY id",
				(client_id, number),
			).fetchall()
		return [_document(row) for row in rows]

	def page(self, client_id: str, after: str | None, limit: int) -> tuple[list[Document], str | None]:
		"""A page of documents in identifier order, with the cursor for the next one."""
		with self._lock:
			rows = self._db.execute(
				"SELECT * FROM documents WHERE client_id = ? AND id > ? ORDER BY id LIMIT ?",
				(client_id, after or "", limit + 1),
			).fetchall()
		documents = [_document(row) for row in rows]
		if len(documents) > limit:
			return documents[:limit], documents[limit - 1].id
		return documents, None

	def settle(self, identifier: str, status: str, exchange: str, reporting: str) -> Document | None:
		with self._lock:
			self._db.execute(
				"UPDATE documents SET status = ?, exchange = ?, reporting = ?, settled = 1, "
				"sequence = sequence + 1 WHERE id = ?",
				(status, exchange, reporting, identifier),
			)
			self._db.commit()
		return self.get(identifier)

	def add_artifact(self, document_id: str, kind: str, media_type: str, body: bytes, present=True) -> str:
		identifier = f"{document_id}/{kind}"
		with self._lock:
			self._db.execute(
				"INSERT OR REPLACE INTO artifacts (identifier, document_id, kind, media_type, body, present) "
				"VALUES (?, ?, ?, ?, ?, ?)",
				(identifier, document_id, kind, media_type, body, 1 if present else 0),
			)
			self._db.commit()
		return identifier

	def artifact(self, identifier: str) -> sqlite3.Row | None:
		with self._lock:
			row = self._db.execute(
				"SELECT * FROM artifacts WHERE identifier = ? AND present = 1", (identifier,)
			).fetchone()
		return row

	def artifacts_of(self, document_id: str) -> list[sqlite3.Row]:
		with self._lock:
			return self._db.execute(
				"SELECT * FROM artifacts WHERE document_id = ? ORDER BY identifier", (document_id,)
			).fetchall()

	def add_event(self, document_id: str, sequence: int, kind: str, body: dict) -> dict:
		with self._lock:
			number = self._next("event")
			event_id = f"{EVENT_PREFIX}{number:06d}"
			payload = {
				"event_id": event_id,
				"sequence": sequence,
				"type": kind,
				"invoice_id": document_id,
				"environment": ENVIRONMENT,
				"status_label": ACCEPTED_LABEL,
				**body,
			}
			self._db.execute(
				"INSERT INTO events (event_id, document_id, sequence, kind, body) VALUES (?, ?, ?, ?, ?)",
				(event_id, document_id, sequence, kind, json.dumps(payload)),
			)
			self._db.commit()
		return payload

	def documents(self) -> list[Document]:
		with self._lock:
			rows = self._db.execute("SELECT * FROM documents ORDER BY id").fetchall()
		return [_document(row) for row in rows]


def _document(row) -> Document | None:
	if row is None:
		return None
	return Document(
		id=row["id"],
		client_id=row["client_id"],
		idempotency_key=row["idempotency_key"],
		number=row["number"],
		media_type=row["media_type"],
		digest=row["digest"],
		behaviour=row["behaviour"],
		status=row["status"],
		exchange=row["exchange"],
		reporting=row["reporting"],
		settled=bool(row["settled"]),
		settle_at=row["settle_at"],
		received_at=row["received_at"],
		sequence=row["sequence"],
	)
