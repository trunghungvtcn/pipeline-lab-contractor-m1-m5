from __future__ import annotations

import threading
from pathlib import Path

from grok_job_ledger import JobLedger


def test_duplicate_admit_one_job(tmp_path: Path):
    db = str(tmp_path / "jobs.db")
    led = JobLedger(db)
    a = led.admit("scope", "k1", "digest-a")
    b = led.admit("scope", "k1", "digest-a")
    assert a["reason_code"] == "OK"
    assert b["reason_code"] == "IDEMPOTENT_HIT"
    assert a["job_id"] == b["job_id"]


def test_digest_conflict(tmp_path: Path):
    led = JobLedger(str(tmp_path / "jobs.db"))
    led.admit("scope", "k1", "d1")
    out = led.admit("scope", "k1", "d2")
    assert out["reason_code"] == "DIGEST_CONFLICT"


def test_concurrent_admit(tmp_path: Path):
    db = str(tmp_path / "jobs.db")
    barrier = threading.Barrier(2)
    ids: list[str] = []
    lock = threading.Lock()

    def worker():
        led = JobLedger(db)
        barrier.wait()
        rec = led.admit("scope", "same", "digest")
        with lock:
            ids.append(rec["job_id"])

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert len(set(ids)) == 1


def test_two_controllers_one_claim(tmp_path: Path):
    led = JobLedger(str(tmp_path / "jobs.db"))
    job = led.admit("s", "k", "d")["job_id"]
    a = led.claim(job, "w1", 10_000)
    b = led.claim(job, "w2", 10_000)
    assert a["status"] == "ok"
    assert b["reason_code"] == "LEASE_HELD"


def test_stale_worker_cannot_finalize(tmp_path: Path):
    now = {"ns": 1_000}
    led = JobLedger(str(tmp_path / "jobs.db"), clock=lambda: now["ns"])
    job = led.admit("s", "k", "d")["job_id"]
    c1 = led.claim(job, "old", 1)  # 1ms lease
    now["ns"] = 10**12
    future = JobLedger(str(tmp_path / "jobs.db"), clock=lambda: now["ns"])
    c2 = future.claim(job, "new", 10_000)
    assert c2["status"] == "ok"
    stale = led.finalize(job, c1["lease_token"], c1["fence"], "SUCCEEDED", "r")
    assert stale["reason_code"] == "LEASE_LOST"
    ok = future.finalize(job, c2["lease_token"], c2["fence"], "SUCCEEDED", "r")
    assert ok["status"] == "ok"


def test_restart_persists_counters(tmp_path: Path):
    db = str(tmp_path / "jobs.db")
    led = JobLedger(db)
    job = led.admit("s", "k", "d")["job_id"]
    claim = led.claim(job, "w", 10_000)
    led.record_attempt(job, claim["lease_token"], claim["fence"], "transient")
    led2 = JobLedger(db)
    row = led2.get(job)
    assert row["transient_attempts"] == 1
    assert row["attempt"] == 1


def test_terminal_replay_no_restart(tmp_path: Path):
    led = JobLedger(str(tmp_path / "jobs.db"))
    job = led.admit("s", "k", "d")["job_id"]
    claim = led.claim(job, "w", 10_000)
    a = led.finalize(job, claim["lease_token"], claim["fence"], "SUCCEEDED", "out")
    b = led.finalize(job, claim["lease_token"], claim["fence"], "SUCCEEDED", "out")
    assert a["reason_code"] == "OK"
    # lease cleared after finalize, so second is LEASE_LOST or IDEMPOTENT
    assert b["reason_code"] in {"IDEMPOTENT_HIT", "LEASE_LOST"}
    again = led.claim(job, "w2", 10_000)
    assert again["reason_code"] == "TERMINAL"


def test_cancel_blocks_late_output(tmp_path: Path):
    led = JobLedger(str(tmp_path / "jobs.db"))
    job = led.admit("s", "k", "d")["job_id"]
    claim = led.claim(job, "w", 10_000)
    led.cancel(job)
    late = led.finalize(job, claim["lease_token"], claim["fence"], "SUCCEEDED", "out")
    assert late["reason_code"] in {"LEASE_LOST", "IDEMPOTENT_HIT"}
    assert led.get(job)["state"] == "CANCELLED"


def test_budget_no_race(tmp_path: Path):
    led = JobLedger(str(tmp_path / "jobs.db"))
    job = led.admit("s", "k", "d")["job_id"]
    ok = 0
    fail = 0
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def w():
        nonlocal ok, fail
        barrier.wait()
        rec = led.reserve_budget(job, 20)
        with lock:
            if rec["status"] == "ok":
                ok += 1
            else:
                fail += 1

    threads = [threading.Thread(target=w) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ok == 5  # limit 100 / 20
    assert fail == 3
