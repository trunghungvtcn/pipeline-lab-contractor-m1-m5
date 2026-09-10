from __future__ import annotations

from pathlib import Path

from grok_pipeline import Pipeline


class ResolverStub:
    def validate(self, locator, profile):
        return {"schema_version": 1, "status": "ok", "reason_code": "OK", "trace_id": "stub"}

    def resolve(self, root, locator, profile, expected_sha256=None):
        from pathlib import Path as P
        import hashlib

        data = (P(root) / locator).read_bytes()
        return {
            "schema_version": 1,
            "status": "ok",
            "reason_code": "OK",
            "trace_id": "stub",
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }


def test_g9_two_jobs_do_not_share_revision(tmp_path: Path):
    p = Pipeline(str(tmp_path / "pipeline"))
    p.resolver = ResolverStub()
    a = p.run(scope="s", idempotency_key="one", request={}, sources={"a": b"A"})
    b = p.run(scope="s", idempotency_key="two", request={}, sources={"b": b"B"})
    assert a["status"] == "ok"
    assert b["status"] == "ok"
    assert a["job_id"] != b["job_id"]
    events = p.transport.pages["sandbox-page-001"].applied_events
    assert len(events) == 2


def test_g10_crash_after_result_resumes_without_recompute(tmp_path: Path):
    now = {"ns": 1_000}
    root = tmp_path / "crash"
    p = Pipeline(str(root), clock=lambda: now["ns"], lease_ms=1)
    p.crash_at = "after_result"
    first = p.run(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    assert first["reason_code"] == "CRASH_INJECTED"
    compute_before = p.compute_calls
    now["ns"] = 10**12
    p2 = Pipeline(str(root), clock=lambda: now["ns"], lease_ms=10_000)
    p2.transport = p.transport
    second = p2.run(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    assert second["status"] == "ok"
    assert p2.compute_calls == 0
    assert compute_before == 1
    assert second["result_digest"]
    third = p2.run(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    assert third["result_digest"] == second["result_digest"]
    assert p2.transport.pages["sandbox-page-001"].state == "SUCCEEDED"
