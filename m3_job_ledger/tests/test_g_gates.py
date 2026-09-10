from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from grok_job_ledger import JobLedger


def _proc_admit(payload: tuple[str, str, str, str]) -> tuple[str | None, str | None]:
    db, scope, key, digest = payload
    led = JobLedger(db)
    try:
        rec = led.admit(scope, key, digest)
        return rec.get("job_id"), rec.get("reason_code")
    finally:
        led.close()


def test_g3_two_processes_one_job(tmp_path: Path):
    db = str(tmp_path / "fresh.db")
    args = [(db, "s", "k", "d")] * 8
    with ProcessPoolExecutor(max_workers=4) as pool:
        got = list(pool.map(_proc_admit, args))
    ids = {job for job, _ in got if job}
    codes = {code for _, code in got}
    assert len(ids) == 1
    assert codes <= {"OK", "IDEMPOTENT_HIT"}
    assert None not in {job for job, _ in got}


def test_g4_unknown_retry_class_is_rejected(tmp_path: Path):
    led = JobLedger(str(tmp_path / "retry.db"))
    job_id = led.admit("s", "k", "d")["job_id"]
    lease = led.claim(job_id, "w", 10000)
    before = led.get(job_id)
    out = led.record_attempt(job_id, lease["lease_token"], lease["fence"], "typo")
    after = led.get(job_id)
    assert out["reason_code"] == "INVALID_RETRY_CLASS"
    assert after["state"] == before["state"] == "RUNNING"
    assert after["permanent_attempts"] == before["permanent_attempts"] == 0
    assert after["transient_attempts"] == before["transient_attempts"] == 0


def test_g5_reservation_conflict_across_jobs(tmp_path: Path):
    led = JobLedger(str(tmp_path / "reserve.db"))
    j1 = led.admit("s", "a", "a")["job_id"]
    j2 = led.admit("s", "b", "b")["job_id"]
    r1 = led.reserve_budget(j1, 10, "same-reservation")
    r2 = led.reserve_budget(j2, 20, "same-reservation")
    assert r1["reason_code"] == "OK"
    assert r2["reason_code"] == "RESERVATION_CONFLICT"
    assert led.get(j2)["budget_reserved"] == 0
    again = led.reserve_budget(j1, 10, "same-reservation")
    assert again["reason_code"] == "IDEMPOTENT_HIT"
    terminal = led.claim(j1, "w", 10000)
    led.finalize(j1, terminal["lease_token"], terminal["fence"], "SUCCEEDED", "x")
    blocked = led.reserve_budget(j1, 5, "after-terminal")
    assert blocked["reason_code"] == "TERMINAL"


def test_g6_deadline_and_not_before(tmp_path: Path):
    now = {"ns": 1_000}
    led = JobLedger(str(tmp_path / "time.db"), clock=lambda: now["ns"])
    job = led.admit("s", "k", "d", deadline_ns=5_000, not_before_ns=2_000)["job_id"]
    early = led.claim(job, "w", 1000)
    assert early["reason_code"] == "NOT_BEFORE"
    now["ns"] = 2_500
    ok = led.claim(job, "w", 1000)
    assert ok["status"] == "ok"
    now["ns"] = 9_000
    late = led.claim(job, "w2", 1000)
    assert late["reason_code"] == "RECONCILE_REQUIRED"
    assert led.get(job)["state"] == "RECONCILE_REQUIRED"
    led.close()
    led2 = JobLedger(str(tmp_path / "time.db"), clock=lambda: now["ns"])
    assert led2.get(job)["deadline_ns"] == 5_000
    assert led2.get(job)["not_before_ns"] == 2_000
    assert led2.get(job)["state"] == "RECONCILE_REQUIRED"
