from __future__ import annotations

from pathlib import Path

from grok_pipeline import Pipeline

SOURCES = {"docs/manual.txt": b"Synthetic lifting manual revision A."}
REQUEST = {"operation": "extract_demo_claims", "source_id": "synthetic-manual"}


def test_admit_freeze_compute_finalize_project(tmp_path: Path):
    pipe = Pipeline(str(tmp_path))
    rec = pipe.run(scope="demo-tenant/synthetic-project", idempotency_key="demo-job-001", request=REQUEST, sources=SOURCES)
    assert rec["status"] == "ok"
    assert rec["finalize"]["state"] == "SUCCEEDED"
    assert rec["freeze"]["manifest_sha256"]
    assert rec["project"]["state"] == "SUCCEEDED"
    assert rec["project"]["reason_code"] == "OK"
    page = pipe.transport.pages["sandbox-page-001"]
    assert page.state == "SUCCEEDED"
    assert page.revision == 1


def test_replay_does_not_create_second_logical_output(tmp_path: Path):
    pipe = Pipeline(str(tmp_path))
    a = pipe.run(scope="demo-tenant/synthetic-project", idempotency_key="demo-job-001", request=REQUEST, sources=SOURCES)
    b = pipe.run(scope="demo-tenant/synthetic-project", idempotency_key="demo-job-001", request=REQUEST, sources=SOURCES)
    assert a["job_id"] == b["job_id"]
    assert a["result_digest"] == b["result_digest"]
    assert a["result_digest"]
    assert len(pipe.transport.pages["sandbox-page-001"].applied_events) == 1
