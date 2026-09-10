from __future__ import annotations

from grok_notion_projection import FakeTransport, Projector


def event(**kw):
    base = {
        "event_id": "evt-1",
        "job_id": "job-1",
        "mapping_version": 1,
        "properties": {"Result Ref": "synthetic://result/demo-job-001", "Status": "SUCCEEDED"},
        "revision": 1,
        "state": "SUCCEEDED",
        "target": "sandbox-page-001",
    }
    base.update(kw)
    return base


def make():
    t = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token")
    p = Projector()
    return t, p


def test_happy_path_projects_status():
    t, p = make()
    rec = p.project(event(), 1, t, token="sandbox-token")
    assert rec["status"] == "ok"
    assert rec["reason_code"] == "OK"
    assert rec["state"] == "SUCCEEDED"
    assert t.pages["sandbox-page-001"].properties["Status"] == "SUCCEEDED"


def test_auth_and_scope_before_write():
    t, p = make()
    bad_token = p.project(event(), 1, t, token="wrong")
    assert bad_token["reason_code"] == "AUTH_DENIED"
    bad_target = p.project(event(target="other-page"), 1, t, token="sandbox-token")
    assert bad_target["reason_code"] == "TARGET_OUT_OF_SCOPE"
    assert t.pages["sandbox-page-001"].revision == 0


def test_duplicate_event_idempotent():
    t, p = make()
    a = p.project(event(), 1, t, token="sandbox-token")
    b = p.project(event(), 1, t, token="sandbox-token")
    assert a["reason_code"] == "OK"
    assert b["reason_code"] == "IDEMPOTENT_HIT"
    assert t.pages["sandbox-page-001"].revision == 1


def test_old_revision_does_not_rollback():
    t, p = make()
    p.project(event(revision=2, event_id="evt-2", state="SUCCEEDED"), 1, t, token="sandbox-token")
    stale = p.project(event(revision=1, event_id="evt-old", state="FAILED"), 2, t, token="sandbox-token")
    assert stale["reason_code"] == "STALE_REVISION"
    assert t.pages["sandbox-page-001"].state == "SUCCEEDED"
    assert t.pages["sandbox-page-001"].revision == 2


def test_timeout_retries_without_compute():
    t = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token", fail_timeouts=2)
    p = Projector(retry_budget=3)
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        t.compute_calls += 1

    rec = p.project(event(), 1, t, token="sandbox-token", compute=compute)
    assert rec["status"] == "ok"
    assert calls["n"] == 0
    assert t.compute_calls == 0


def test_timeout_budget_exhausted():
    t = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token", fail_timeouts=9)
    p = Projector(retry_budget=3)
    rec = p.project(event(), 1, t, token="sandbox-token")
    assert rec["reason_code"] == "PROJECTION_TIMEOUT"
    assert t.pages["sandbox-page-001"].revision == 0


def test_terminal_does_not_return_to_ready():
    t, p = make()
    p.project(event(), 1, t, token="sandbox-token")
    back = p.project(event(event_id="evt-2", revision=2, state="Ready"), 1, t, token="sandbox-token")
    assert back["reason_code"] == "TERMINAL_LOCKED"
    assert t.pages["sandbox-page-001"].state == "SUCCEEDED"


def test_unknown_mapping_rejected():
    t, p = make()
    rec = p.project(event(mapping_version=99), 1, t, token="sandbox-token")
    assert rec["reason_code"] == "UNKNOWN_MAPPING"
