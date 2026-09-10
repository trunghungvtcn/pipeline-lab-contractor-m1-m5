"""Durable job ledger on SQLite. Lease/state CAS in one transaction."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Callable

from .canon import envelope

TERMINAL = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "RECONCILE_REQUIRED"})
NONTERMINAL = frozenset({"ADMITTED", "RUNNING", "Ready"})
SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  state TEXT NOT NULL,
  worker_id TEXT,
  lease_token TEXT,
  fence INTEGER NOT NULL DEFAULT 0,
  lease_until_ns INTEGER,
  attempt INTEGER NOT NULL DEFAULT 0,
  transient_attempts INTEGER NOT NULL DEFAULT 0,
  permanent_attempts INTEGER NOT NULL DEFAULT 0,
  budget_reserved INTEGER NOT NULL DEFAULT 0,
  budget_limit INTEGER NOT NULL DEFAULT 100,
  result_digest TEXT,
  created_ns INTEGER NOT NULL,
  updated_ns INTEGER NOT NULL,
  UNIQUE(scope, idempotency_key)
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
  reservation_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  amount INTEGER NOT NULL,
  operation TEXT NOT NULL DEFAULT 'reserve',
  state TEXT NOT NULL,
  at_ns INTEGER NOT NULL
);
"""
ADD_COLUMNS = (
    ("deadline_ns", "INTEGER"),
    ("not_before_ns", "INTEGER"),
    ("max_transient", "INTEGER"),
    ("max_permanent", "INTEGER"),
    ("dispatch_count", "INTEGER NOT NULL DEFAULT 0"),
    ("projection_status", "TEXT"),
    ("outbox", "TEXT"),
    ("result_payload", "TEXT"),
    ("reservation_operation", "TEXT"),
)


class JobLedger:
    def __init__(
        self,
        db_path: str,
        *,
        clock: Callable[[], int] | None = None,
        id_gen: Callable[[], str] | None = None,
        max_transient: int = 5,
        max_permanent: int = 1,
    ) -> None:
        from .canon import SystemClock, UuidGen

        self._db_path = db_path
        self._clock = clock or (lambda: SystemClock().now_ns())
        self._id = id_gen or (lambda: UuidGen().new_id())
        self._max_transient = int(max_transient)
        self._max_permanent = int(max_permanent)
        self._local = threading.local()
        self._migrate()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            self._local.conn = None

    def __enter__(self) -> "JobLedger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _configure(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA busy_timeout=30000")
        last: Exception | None = None
        for _ in range(80):
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                return
            except sqlite3.OperationalError as exc:
                last = exc
                if "locked" in str(exc).lower():
                    time.sleep(0.02)
                    continue
                raise
        raise last or sqlite3.OperationalError("database is locked")

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self._db_path,
                timeout=60,
                isolation_level=None,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            self._configure(conn)
            self._local.conn = conn
        return conn

    def _migrate(self) -> None:
        last: Exception | None = None
        for _ in range(80):
            c = sqlite3.connect(self._db_path, timeout=60)
            try:
                c.execute("PRAGMA busy_timeout=30000")
                try:
                    c.execute("PRAGMA journal_mode=WAL")
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower():
                        raise
                    last = exc
                    time.sleep(0.02)
                    continue
                c.executescript(SCHEMA)
                cols = {r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
                for name, decl in ADD_COLUMNS:
                    if name not in cols:
                        try:
                            c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {decl}")
                        except sqlite3.OperationalError as exc:
                            if "duplicate column" not in str(exc).lower():
                                raise
                rcols = {r[1] for r in c.execute("PRAGMA table_info(reservations)").fetchall()}
                if "operation" not in rcols:
                    try:
                        c.execute("ALTER TABLE reservations ADD COLUMN operation TEXT NOT NULL DEFAULT 'reserve'")
                    except sqlite3.OperationalError as exc:
                        if "duplicate column" not in str(exc).lower():
                            raise
                c.commit()
                return
            except sqlite3.OperationalError as exc:
                last = exc
                if "locked" in str(exc).lower():
                    time.sleep(0.02)
                    continue
                raise
            finally:
                c.close()
        raise last or sqlite3.OperationalError("database is locked")

    def _begin(self, c: sqlite3.Connection) -> None:
        last: Exception | None = None
        for _ in range(80):
            try:
                c.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                last = exc
                if "locked" in str(exc).lower():
                    time.sleep(0.015)
                    continue
                raise
        raise last or sqlite3.OperationalError("database is locked")

    def _event(self, c: sqlite3.Connection, job_id: str, kind: str, payload: str) -> None:
        c.execute(
            "INSERT INTO events(job_id, kind, payload, at_ns) VALUES (?,?,?,?)",
            (job_id, kind, payload, self._clock()),
        )

    def admit(
        self,
        scope: str,
        idempotency_key: str,
        request_digest: str,
        *,
        deadline_ns: int | None = None,
        not_before_ns: int | None = None,
    ) -> dict[str, Any]:
        trace = self._id()
        now = self._clock()
        if deadline_ns is not None and (not isinstance(deadline_ns, int) or isinstance(deadline_ns, bool)):
            return envelope(status="error", reason_code="INVALID_DEADLINE", trace_id=trace)
        if not_before_ns is not None and (not isinstance(not_before_ns, int) or isinstance(not_before_ns, bool)):
            return envelope(status="error", reason_code="INVALID_NOT_BEFORE", trace_id=trace)
        c = self._conn()
        self._begin(c)
        try:
            row = c.execute(
                "SELECT * FROM jobs WHERE scope=? AND idempotency_key=?",
                (scope, idempotency_key),
            ).fetchone()
            if row:
                c.execute("COMMIT")
                if row["request_digest"] == request_digest:
                    extra = {
                        "job_id": row["job_id"],
                        "projection_status": row["projection_status"],
                        "result_digest": row["result_digest"],
                        "state": row["state"],
                    }
                    return envelope(status="ok", reason_code="IDEMPOTENT_HIT", trace_id=trace, extra=extra)
                return envelope(
                    status="error",
                    reason_code="DIGEST_CONFLICT",
                    trace_id=trace,
                    extra={"job_id": row["job_id"], "state": row["state"]},
                )
            job_id = self._id()
            c.execute(
                "INSERT INTO jobs(job_id, scope, idempotency_key, request_digest, state, created_ns, updated_ns, "
                "max_transient, max_permanent, dispatch_count, projection_status, deadline_ns, not_before_ns) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    scope,
                    idempotency_key,
                    request_digest,
                    "ADMITTED",
                    now,
                    now,
                    self._max_transient,
                    self._max_permanent,
                    0,
                    "NONE",
                    deadline_ns,
                    not_before_ns,
                ),
            )
            self._event(c, job_id, "ADMITTED", request_digest)
            c.execute("COMMIT")
            return envelope(
                status="ok",
                reason_code="OK",
                trace_id=trace,
                extra={"job_id": job_id, "state": "ADMITTED"},
            )
        except sqlite3.IntegrityError:
            c.execute("ROLLBACK")
            row = c.execute(
                "SELECT * FROM jobs WHERE scope=? AND idempotency_key=?",
                (scope, idempotency_key),
            ).fetchone()
            if row and row["request_digest"] == request_digest:
                return envelope(
                    status="ok",
                    reason_code="IDEMPOTENT_HIT",
                    trace_id=trace,
                    extra={"job_id": row["job_id"], "state": row["state"]},
                )
            return envelope(
                status="error",
                reason_code="DIGEST_CONFLICT",
                trace_id=trace,
                extra={"job_id": row["job_id"], "state": row["state"]} if row else {},
            )
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def claim(self, job_id: str, worker_id: str, lease_ms: int) -> dict[str, Any]:
        trace = self._id()
        now = self._clock()
        if not isinstance(lease_ms, int) or isinstance(lease_ms, bool) or lease_ms <= 0:
            return envelope(status="error", reason_code="INVALID_LEASE", trace_id=trace)
        until = now + lease_ms * 1_000_000
        c = self._conn()
        self._begin(c)
        try:
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="NOT_FOUND", trace_id=trace)
            if row["state"] in TERMINAL:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="TERMINAL", trace_id=trace, extra={"state": row["state"]})
            nb = row["not_before_ns"]
            if nb is not None and now < int(nb):
                c.execute("COMMIT")
                return envelope(status="error", reason_code="NOT_BEFORE", trace_id=trace)
            dl = row["deadline_ns"]
            if dl is not None and now > int(dl):
                if int(row["dispatch_count"] or 0) > 0 or row["state"] == "RUNNING":
                    c.execute(
                        "UPDATE jobs SET state=?, lease_token=NULL, worker_id=NULL, updated_ns=? "
                        "WHERE job_id=? AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED')",
                        ("RECONCILE_REQUIRED", now, job_id),
                    )
                    self._event(c, job_id, "DEADLINE", "RECONCILE_REQUIRED")
                    c.execute("COMMIT")
                    return envelope(status="error", reason_code="RECONCILE_REQUIRED", trace_id=trace)
                c.execute(
                    "UPDATE jobs SET state=?, lease_token=NULL, worker_id=NULL, updated_ns=? "
                    "WHERE job_id=? AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED')",
                    ("FAILED", now, job_id),
                )
                self._event(c, job_id, "DEADLINE", "DEADLINE_EXCEEDED")
                c.execute("COMMIT")
                return envelope(status="error", reason_code="DEADLINE_EXCEEDED", trace_id=trace)
            if row["lease_until_ns"] and row["lease_until_ns"] > now and row["lease_token"]:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="LEASE_HELD", trace_id=trace)
            max_t = row["max_transient"] if row["max_transient"] is not None else self._max_transient
            dispatch = int(row["dispatch_count"] or 0)
            if dispatch >= int(max_t):
                c.execute(
                    "UPDATE jobs SET state=?, lease_token=NULL, worker_id=NULL, updated_ns=? WHERE job_id=? AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED')",
                    ("FAILED", now, job_id),
                )
                self._event(c, job_id, "TRANSIENT_EXHAUSTED", str(dispatch))
                c.execute("COMMIT")
                return envelope(status="error", reason_code="TRANSIENT_EXHAUSTED", trace_id=trace)
            token = self._id()
            fence = int(row["fence"]) + 1
            cur = c.execute(
                "UPDATE jobs SET worker_id=?, lease_token=?, fence=?, lease_until_ns=?, state=?, "
                "updated_ns=?, dispatch_count=dispatch_count+1 "
                "WHERE job_id=? AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED') "
                "AND (lease_token IS NULL OR lease_until_ns IS NULL OR lease_until_ns<=?)",
                (worker_id, token, fence, until, "RUNNING", now, job_id, now),
            )
            if cur.rowcount != 1:
                c.execute("ROLLBACK")
                return envelope(status="error", reason_code="LEASE_HELD", trace_id=trace)
            self._event(c, job_id, "CLAIMED", worker_id)
            c.execute("COMMIT")
            return envelope(
                status="ok",
                reason_code="OK",
                trace_id=trace,
                extra={"fence": fence, "job_id": job_id, "lease_token": token, "state": "RUNNING"},
            )
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def _require_lease(self, job_id: str, lease_token: str, fence: int) -> sqlite3.Row | str:
        """Read helper kept for tests; mutations must still CAS in the same UPDATE."""
        row = self._conn().execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return "NOT_FOUND"
        if row["state"] in TERMINAL:
            return "TERMINAL"
        if row["lease_token"] != lease_token or row["fence"] != fence:
            return "LEASE_LOST"
        if row["lease_until_ns"] and row["lease_until_ns"] < self._clock():
            return "LEASE_LOST"
        return row

    def record_attempt(self, job_id: str, lease_token: str, fence: int, klass: str) -> dict[str, Any]:
        trace = self._id()
        if klass not in {"transient", "permanent"}:
            return envelope(status="error", reason_code="INVALID_RETRY_CLASS", trace_id=trace)
        now = self._clock()
        c = self._conn()
        self._begin(c)
        try:
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="NOT_FOUND", trace_id=trace)
            if row["lease_token"] != lease_token or row["fence"] != fence:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="LEASE_LOST", trace_id=trace)
            if row["lease_until_ns"] and row["lease_until_ns"] < now:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="LEASE_LOST", trace_id=trace)
            if row["state"] in TERMINAL:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="TERMINAL", trace_id=trace)
            dl = row["deadline_ns"]
            if dl is not None and now > int(dl):
                c.execute("COMMIT")
                return envelope(status="error", reason_code="RECONCILE_REQUIRED", trace_id=trace)
            if klass == "transient":
                n = int(row["transient_attempts"]) + 1
                cap = int(row["max_transient"] or self._max_transient)
                c.execute(
                    "UPDATE jobs SET transient_attempts=?, attempt=attempt+1, updated_ns=? "
                    "WHERE job_id=? AND lease_token=? AND fence=?",
                    (n, now, job_id, lease_token, fence),
                )
                self._event(c, job_id, "ATTEMPT", klass)
                c.execute("COMMIT")
                if n >= cap:
                    return self.finalize(job_id, lease_token, fence, "FAILED", None)
            else:
                n = int(row["permanent_attempts"]) + 1
                cap = int(row["max_permanent"] or self._max_permanent)
                c.execute(
                    "UPDATE jobs SET permanent_attempts=?, attempt=attempt+1, updated_ns=? "
                    "WHERE job_id=? AND lease_token=? AND fence=?",
                    (n, now, job_id, lease_token, fence),
                )
                self._event(c, job_id, "ATTEMPT", klass)
                c.execute("COMMIT")
                if n >= cap:
                    return self.finalize(job_id, lease_token, fence, "FAILED", None)
            return envelope(status="ok", reason_code="OK", trace_id=trace, extra={"job_id": job_id})
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def finalize(
        self, job_id: str, lease_token: str, fence: int, terminal_status: str, result_digest: str | None
    ) -> dict[str, Any]:
        trace = self._id()
        now = self._clock()
        # Probe R06 patches this to cancel on a second connection between read and UPDATE.
        got = self._require_lease(job_id, lease_token, fence)
        c = self._conn()
        self._begin(c)
        try:
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="NOT_FOUND", trace_id=trace)
            if row["state"] in TERMINAL:
                c.execute("COMMIT")
                if terminal_status == row["state"] and (result_digest == row["result_digest"] or result_digest is None):
                    return envelope(
                        status="ok",
                        reason_code="IDEMPOTENT_HIT",
                        trace_id=trace,
                        extra={"job_id": job_id, "state": row["state"], "result_digest": row["result_digest"]},
                    )
                return envelope(
                    status="error",
                    reason_code="LEASE_LOST",
                    trace_id=trace,
                    extra={"job_id": job_id, "state": row["state"]},
                )
            if terminal_status not in TERMINAL:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="INVALID_STATE", trace_id=trace)
            if isinstance(got, str) and got == "LEASE_LOST":
                # Lease already lost on the pre-check; still CAS below in case of races.
                pass
            cur = c.execute(
                "UPDATE jobs SET state=?, result_digest=?, lease_token=NULL, worker_id=NULL, "
                "updated_ns=?, projection_status=CASE WHEN ?='SUCCEEDED' THEN 'PENDING' ELSE projection_status END "
                "WHERE job_id=? AND lease_token=? AND fence=? "
                "AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED') "
                "AND (lease_until_ns IS NULL OR lease_until_ns>=?)",
                (terminal_status, result_digest, now, terminal_status, job_id, lease_token, fence, now),
            )
            if cur.rowcount != 1:
                live = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
                c.execute("COMMIT")
                if live and live["state"] in TERMINAL:
                    if live["state"] == terminal_status and live["result_digest"] == result_digest:
                        return envelope(
                            status="ok",
                            reason_code="IDEMPOTENT_HIT",
                            trace_id=trace,
                            extra={"job_id": job_id, "state": live["state"]},
                        )
                    return envelope(
                        status="error",
                        reason_code="LEASE_LOST",
                        trace_id=trace,
                        extra={"state": live["state"] if live else None},
                    )
                return envelope(status="error", reason_code="LEASE_LOST", trace_id=trace)
            self._event(c, job_id, "FINALIZED", terminal_status)
            c.execute("COMMIT")
            return envelope(
                status="ok",
                reason_code="OK",
                trace_id=trace,
                extra={"job_id": job_id, "result_digest": result_digest, "state": terminal_status},
            )
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def mark_projected(self, job_id: str, outbox: str, result_payload: str | None = None) -> dict[str, Any]:
        trace = self._id()
        c = self._conn()
        self._begin(c)
        try:
            cur = c.execute(
                "UPDATE jobs SET projection_status=?, outbox=?, result_payload=COALESCE(?, result_payload), updated_ns=? "
                "WHERE job_id=? AND state='SUCCEEDED'",
                ("APPLIED", outbox, result_payload, self._clock(), job_id),
            )
            c.execute("COMMIT")
            if cur.rowcount != 1:
                return envelope(status="error", reason_code="NOT_FOUND", trace_id=trace)
            return envelope(status="ok", reason_code="OK", trace_id=trace)
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def store_outbox(self, job_id: str, outbox: str, result_payload: str) -> dict[str, Any]:
        trace = self._id()
        c = self._conn()
        self._begin(c)
        try:
            cur = c.execute(
                "UPDATE jobs SET outbox=?, result_payload=?, updated_ns=? WHERE job_id=?",
                (outbox, result_payload, self._clock(), job_id),
            )
            c.execute("COMMIT")
            if cur.rowcount != 1:
                return envelope(status="error", reason_code="NOT_FOUND", trace_id=trace)
            return envelope(status="ok", reason_code="OK", trace_id=trace)
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def mark_reconcile(self, job_id: str, lease_token: str, fence: int, reason: str) -> dict[str, Any]:
        return self.finalize(job_id, lease_token, fence, "RECONCILE_REQUIRED", reason)

    def cancel(self, job_id: str) -> dict[str, Any]:
        trace = self._id()
        c = self._conn()
        self._begin(c)
        try:
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="NOT_FOUND", trace_id=trace)
            if row["state"] in TERMINAL:
                c.execute("COMMIT")
                return envelope(status="ok", reason_code="IDEMPOTENT_HIT", trace_id=trace, extra={"state": row["state"]})
            cur = c.execute(
                "UPDATE jobs SET state=?, lease_token=NULL, worker_id=NULL, updated_ns=? "
                "WHERE job_id=? AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED')",
                ("CANCELLED", self._clock(), job_id),
            )
            if cur.rowcount != 1:
                c.execute("ROLLBACK")
                return envelope(status="error", reason_code="LEASE_LOST", trace_id=trace)
            self._event(c, job_id, "CANCELLED", "")
            c.execute("COMMIT")
            return envelope(status="ok", reason_code="OK", trace_id=trace, extra={"job_id": job_id, "state": "CANCELLED"})
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def reserve_budget(self, job_id: str, amount: int, reservation_id: str | None = None, *, operation: str = "reserve") -> dict[str, Any]:
        trace = self._id()
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            return envelope(status="error", reason_code="INVALID_AMOUNT", trace_id=trace)
        if operation != "reserve":
            return envelope(status="error", reason_code="INVALID_OPERATION", trace_id=trace)
        rid = reservation_id or self._id()
        c = self._conn()
        self._begin(c)
        try:
            existing = c.execute("SELECT * FROM reservations WHERE reservation_id=?", (rid,)).fetchone()
            if existing:
                same = (
                    existing["job_id"] == job_id
                    and int(existing["amount"]) == amount
                    and (existing["operation"] or "reserve") == operation
                )
                c.execute("COMMIT")
                if same:
                    return envelope(status="ok", reason_code="IDEMPOTENT_HIT", trace_id=trace)
                return envelope(status="error", reason_code="RESERVATION_CONFLICT", trace_id=trace)
            row = c.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not row:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="NOT_FOUND", trace_id=trace)
            if row["state"] in TERMINAL:
                c.execute("COMMIT")
                return envelope(status="error", reason_code="TERMINAL", trace_id=trace)
            if int(row["budget_reserved"]) + amount > int(row["budget_limit"]):
                c.execute("COMMIT")
                return envelope(status="error", reason_code="BUDGET_EXCEEDED", trace_id=trace)
            cur = c.execute(
                "UPDATE jobs SET budget_reserved=budget_reserved+?, updated_ns=? "
                "WHERE job_id=? AND budget_reserved+? <= budget_limit "
                "AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED')",
                (amount, self._clock(), job_id, amount),
            )
            if cur.rowcount != 1:
                c.execute("ROLLBACK")
                return envelope(status="error", reason_code="BUDGET_EXCEEDED", trace_id=trace)
            c.execute(
                "INSERT INTO reservations(reservation_id, job_id, amount, operation, state, at_ns) VALUES (?,?,?,?,?,?)",
                (rid, job_id, amount, operation, "reserved", self._clock()),
            )
            c.execute("COMMIT")
            return envelope(status="ok", reason_code="OK", trace_id=trace, extra={"reservation_id": rid})
        except sqlite3.IntegrityError:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            existing = c.execute("SELECT * FROM reservations WHERE reservation_id=?", (rid,)).fetchone()
            if existing and existing["job_id"] == job_id and int(existing["amount"]) == amount:
                return envelope(status="ok", reason_code="IDEMPOTENT_HIT", trace_id=trace)
            return envelope(status="error", reason_code="RESERVATION_CONFLICT", trace_id=trace)
        except Exception:
            try:
                c.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def get(self, job_id: str) -> dict[str, Any]:
        trace = self._id()
        row = self._conn().execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return envelope(status="error", reason_code="NOT_FOUND", trace_id=trace)
        extra = {k: row[k] for k in row.keys()}
        if extra.get("outbox"):
            try:
                extra["outbox_obj"] = json.loads(extra["outbox"])
            except (TypeError, ValueError):
                pass
        return envelope(status="ok", reason_code="OK", trace_id=trace, extra=extra)

    def history(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._conn().execute(
            "SELECT kind, payload, at_ns FROM events WHERE job_id=? ORDER BY id", (job_id,)
        ).fetchall()
        return [{"at_ns": r["at_ns"], "kind": r["kind"], "payload": r["payload"]} for r in rows]
