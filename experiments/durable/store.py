"""SQLite state machine for the application-owned DUR-01 fixture."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

CAPABILITY = "ledger.credit"
REVISION = "ledger-v1"
CODEC = 1
TTL = 120
LEASE = 30
ATTEMPTS = 2
BACKOFF = 3

SCHEMA = """
CREATE TABLE clock (offset INTEGER NOT NULL);
INSERT INTO clock VALUES (0);
CREATE TABLE authority (
    tenant TEXT, subject TEXT, allowed INTEGER NOT NULL,
    PRIMARY KEY (tenant, subject)
);
CREATE TABLE work (
    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL,
    request TEXT NOT NULL, capability TEXT NOT NULL, revision TEXT NOT NULL,
    codec INTEGER NOT NULL, payload TEXT NOT NULL, fingerprint TEXT NOT NULL,
    admitted REAL NOT NULL, expires REAL NOT NULL, attempt_limit INTEGER NOT NULL,
    ready REAL NOT NULL, generation INTEGER NOT NULL DEFAULT 0, lease REAL,
    state TEXT NOT NULL DEFAULT 'queued', armed INTEGER NOT NULL DEFAULT 0,
    cancel INTEGER NOT NULL DEFAULT 0, result INTEGER, failure TEXT,
    UNIQUE (tenant, subject, capability, request)
);
CREATE TABLE audit (
    id TEXT, generation INTEGER, event TEXT, execution TEXT,
    PRIMARY KEY (id, generation, event)
);
-- The simulated business effect and its optional reconciliation receipt commit
-- together, in a transaction separate from the queue's result transaction.
CREATE TABLE credits (id TEXT PRIMARY KEY, cents INTEGER NOT NULL);
CREATE TABLE receipts (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, cents INTEGER NOT NULL);
"""


class Refused(ValueError):
    """Safe fixture boundary rejection."""


class LostLease(RuntimeError):
    """This worker can no longer mutate the submission or commit its effect."""


@contextmanager
def database(path: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(path, timeout=2, autocommit=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA synchronous = FULL")
        yield db
    finally:
        db.close()


@contextmanager
def write(db: sqlite3.Connection) -> Iterator[None]:
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise


def clock(db: sqlite3.Connection) -> float:
    # Only the harness modifies the offset, to cross lease/TTL boundaries deterministically.
    return time.time() + db.execute("SELECT offset FROM clock").fetchone()[0]


def allowed(db: sqlite3.Connection, tenant: str, subject: str) -> bool:
    row = db.execute(
        "SELECT allowed FROM authority WHERE tenant = ? AND subject = ?", (tenant, subject)
    ).fetchone()
    return row is not None and row["allowed"] == 1


def credit_input(payload: object) -> int:
    if not isinstance(payload, dict) or payload.keys() != {"cents"}:
        raise Refused("expected one cents field")
    cents = payload["cents"]
    if type(cents) is not int or not 1 <= cents <= 1_000_000:
        raise Refused("cents must be an integer in range")
    return cents


def admit(
    db: sqlite3.Connection,
    tenant: str,
    subject: str,
    request: str,
    raw: bytes,
    checkpoint: Callable[[str], None] | None = None,
) -> str:
    if len(raw) > 64 or not (1 <= len(request) <= 32 and request.isascii() and request.isalnum()):
        raise Refused("admission bounds exceeded")
    # The canonical spelling is the codec. Comparing the whole record rejects
    # duplicate keys, extra whitespace, alternate numbers and invalid UTF-8.
    try:
        cents = credit_input(json.loads(raw))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Refused("invalid JSON") from error
    canonical = json.dumps({"cents": cents}, separators=(",", ":"))
    if raw != canonical.encode("ascii"):
        raise Refused("noncanonical input")
    digest = hashlib.sha256(raw).hexdigest()
    with write(db):
        if not allowed(db, tenant, subject):
            raise Refused("admission denied")
        prior = db.execute(
            """SELECT id, fingerprint FROM work
               WHERE tenant = ? AND subject = ? AND capability = ? AND request = ?""",
            (tenant, subject, CAPABILITY, request),
        ).fetchone()
        if prior is not None:
            if prior["fingerprint"] != digest:
                raise Refused("submission conflict")
            return prior["id"]
        job = uuid4().hex
        now = clock(db)
        db.execute(
            """INSERT INTO work
               (id, tenant, subject, request, capability, revision, codec, payload, fingerprint,
                admitted, expires, attempt_limit, ready)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job,
                tenant,
                subject,
                request,
                CAPABILITY,
                REVISION,
                CODEC,
                canonical,
                digest,
                now,
                now + TTL,
                ATTEMPTS,
                now,
            ),
        )
        if checkpoint is not None:
            checkpoint("before_admission_commit")
    if checkpoint is not None:
        checkpoint("after_admission_commit")
    return job


def get(db: sqlite3.Connection, job: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM work WHERE id = ?", (job,)).fetchone()
    if row is None:
        raise LookupError(job)
    return row


def visible(db: sqlite3.Connection, tenant: str, subject: str, job: str) -> sqlite3.Row | None:
    return db.execute(
        """SELECT w.id, w.state, w.result, w.failure FROM work w JOIN authority a
           ON a.tenant = w.tenant AND a.subject = w.subject
           WHERE w.id = ? AND w.tenant = ? AND w.subject = ? AND a.allowed = 1""",
        (job, tenant, subject),
    ).fetchone()


def audit(
    db: sqlite3.Connection, row: sqlite3.Row, event: str, execution: str | None = None
) -> None:
    db.execute(
        "INSERT INTO audit VALUES (?, ?, ?, ?)", (row["id"], row["generation"], event, execution)
    )


def transition(
    db: sqlite3.Connection,
    row: sqlite3.Row,
    state: str,
    *,
    result: int | None = None,
    failure: str | None = None,
    delay: int = 0,
) -> None:
    """All callers hold the write transaction and read the current row inside it."""
    db.execute(
        "UPDATE work SET state = ?, result = ?, failure = ?, lease = NULL, ready = ? WHERE id = ?",
        (state, result, failure, clock(db) + delay, row["id"]),
    )
    audit(db, row, state)


def claim(db: sqlite3.Connection, job: str, revision: str | None) -> sqlite3.Row | None:
    with write(db):
        row = get(db, job)
        now = clock(db)
        if row["state"] == "running" and row["lease"] <= now:
            if row["armed"]:
                transition(db, row, "uncertain")
                return None
        elif row["state"] != "queued" or row["ready"] > now:
            return None
        if row["cancel"]:
            transition(db, row, "cancelled")
        elif row["expires"] <= now:
            transition(db, row, "expired")
        elif (row["capability"], row["revision"], row["codec"]) != (CAPABILITY, revision, CODEC):
            transition(db, row, "quarantined")
        elif row["generation"] >= row["attempt_limit"]:
            transition(db, row, "exhausted")
        else:
            db.execute(
                """UPDATE work SET state = 'running', generation = generation + 1, lease = ?,
                   armed = 0, failure = NULL WHERE id = ?""",
                (min(now + LEASE, row["expires"]), job),
            )
            current = get(db, job)
            audit(db, current, "claimed")
            return current
        return None


def owned(db: sqlite3.Connection, job: str, generation: int) -> sqlite3.Row:
    row = get(db, job)
    if row["state"] != "running" or row["generation"] != generation or row["lease"] <= clock(db):
        raise LostLease
    return row


def record_credit(
    db: sqlite3.Connection, job: str, generation: int, cents: int, *, receipt: bool
) -> None:
    with write(db):
        row = owned(db, job, generation)
        if row["cancel"] or not allowed(db, row["tenant"], row["subject"]):
            raise Refused("effect denied")
        db.execute("INSERT INTO credits VALUES (?, ?)", (job, cents))
        if receipt:
            db.execute("INSERT INTO receipts VALUES (?, ?, ?)", (job, row["fingerprint"], cents))


def finish(
    db: sqlite3.Connection, job: str, generation: int, *, result: int | None, failure: str | None
) -> None:
    with write(db):
        row = owned(db, job, generation)
        if result is not None:
            transition(db, row, "succeeded", result=result)
        elif row["armed"]:
            transition(db, row, "uncertain", failure=failure)
        elif row["cancel"]:
            transition(db, row, "cancelled")
        elif failure in {"rate_limited", "unavailable"}:
            state = "queued" if generation < row["attempt_limit"] else "exhausted"
            transition(db, row, state, failure=failure, delay=BACKOFF)
        else:
            transition(db, row, "failed", failure=failure)


def cancel(db: sqlite3.Connection, tenant: str, subject: str, job: str) -> bool:
    with write(db):
        if visible(db, tenant, subject, job) is None:
            return False
        row = get(db, job)
        if row["state"] not in {"queued", "running"}:
            return False
        if not row["cancel"]:
            db.execute("UPDATE work SET cancel = 1 WHERE id = ?", (job,))
            audit(db, row, "cancel_requested")
        if not row["armed"]:
            transition(db, row, "cancelled")
        return True


def reconcile(db: sqlite3.Connection, tenant: str, subject: str, job: str) -> bool:
    with write(db):
        if visible(db, tenant, subject, job) is None:
            return False
        row = get(db, job)
        if row["state"] != "uncertain":
            return False
        receipt = db.execute(
            "SELECT cents FROM receipts WHERE id = ? AND fingerprint = ?", (job, row["fingerprint"])
        ).fetchone()
        if receipt is None:
            db.execute(
                "INSERT OR IGNORE INTO audit VALUES (?, ?, 'receipt_missing', NULL)",
                (job, row["generation"]),
            )
            return False
        audit(db, row, "receipt_verified")
        transition(db, row, "succeeded", result=receipt["cents"])
        return True
