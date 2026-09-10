from __future__ import annotations

from pathlib import Path

import pytest

from grok_job_ledger import JobLedger, loads_strict


def test_r06_cancel_finalize_race(tmp_path: Path):
    db = str(tmp_path / "race.db")
    led = JobLedger(db)
    job = led.admit("s", "k", "d")["job_id"]
    lease = led.claim(job, "old", 100000)
    original = led._require_lease

    def schedule_cancel(*args):
        row = original(*args)
        JobLedger(db).cancel(job)
        return row

    led._require_lease = schedule_cancel
    out = led.finalize(job, lease["lease_token"], lease["fence"], "SUCCEEDED", "old-result")
    assert led.get(job)["state"] == "CANCELLED"
    assert out["status"] == "error"


def test_r07_negative_and_over_budget(tmp_path: Path):
    led = JobLedger(str(tmp_path / "budget.db"))
    job = led.admit("s", "k", "d")["job_id"]
    a = led.reserve_budget(job, -1000)
    b = led.reserve_budget(job, 1100)
    c = led.reserve_budget(job, True)  # type: ignore[arg-type]
    assert a["status"] == "error"
    assert b["reason_code"] == "BUDGET_EXCEEDED"
    assert c["reason_code"] == "INVALID_AMOUNT"
    assert led.get(job)["budget_reserved"] == 0
    ok = led.reserve_budget(job, 40)
    again = led.reserve_budget(job, 40, reservation_id="r1")
    dup = led.reserve_budget(job, 40, reservation_id="r1")
    assert ok["status"] == "ok"
    assert again["status"] == "ok"
    assert dup["reason_code"] == "IDEMPOTENT_HIT"
    assert led.get(job)["budget_reserved"] == 80


def test_r08_crash_reclaim_bounded(tmp_path: Path):
    now = [1]
    led = JobLedger(str(tmp_path / "attempt.db"), clock=lambda: now[0], max_transient=2)
    job = led.admit("s", "k", "d")["job_id"]
    statuses = []
    for _ in range(10):
        statuses.append(led.claim(job, "w", 1)["status"])
        now[0] += 2_000_000
    row = led.get(job)
    assert statuses.count("ok") <= 2
    assert any(s == "error" for s in statuses)
    assert row["dispatch_count"] <= 2


def test_terminal_replay_same_result_idempotent(tmp_path: Path):
    led = JobLedger(str(tmp_path / "jobs.db"))
    job = led.admit("s", "k", "d")["job_id"]
    claim = led.claim(job, "w", 10_000)
    a = led.finalize(job, claim["lease_token"], claim["fence"], "SUCCEEDED", "out")
    b = led.finalize(job, claim["lease_token"], claim["fence"], "SUCCEEDED", "out")
    assert a["reason_code"] == "OK"
    assert b["reason_code"] == "IDEMPOTENT_HIT"
    assert led.get(job)["state"] == "SUCCEEDED"


def test_loads_strict_rejects_nan():
    with pytest.raises(Exception):
        loads_strict('{"x":NaN}')
