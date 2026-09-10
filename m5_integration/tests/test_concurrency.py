from __future__ import annotations

import threading
from pathlib import Path

from grok_pipeline import Pipeline

SOURCES = {"docs/manual.txt": b"Synthetic lifting manual revision A."}
REQUEST = {"operation": "extract_demo_claims", "source_id": "synthetic-manual"}


def test_duplicate_concurrent_admit_one_job(tmp_path: Path):
    pipe = Pipeline(str(tmp_path))
    ids: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait()
            rec = pipe.ledger.admit("demo-tenant/synthetic-project", "demo-job-001", "digest")
            with lock:
                ids.append(rec["job_id"])
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(ids) == 2
    assert len(set(ids)) == 1


def test_stale_lease_cannot_finalize(tmp_path: Path):
    now = {"ns": 1_000}
    pipe = Pipeline(str(tmp_path), clock=lambda: now["ns"])
    job = pipe.ledger.admit("s", "k", "d")["job_id"]
    old = pipe.ledger.claim(job, "old", 1)
    now["ns"] = 10**12
    future = Pipeline(str(tmp_path), clock=lambda: now["ns"])
    nxt = future.ledger.claim(job, "new", 10_000)
    stale = pipe.ledger.finalize(job, old["lease_token"], old["fence"], "SUCCEEDED", "r")
    assert stale["reason_code"] == "LEASE_LOST"
    ok = future.ledger.finalize(job, nxt["lease_token"], nxt["fence"], "SUCCEEDED", "r")
    assert ok["status"] == "ok"
