from __future__ import annotations

import pytest

from grok_notion_projection import (
    FakeTransport,
    MUTATING_OPS,
    Projector,
    READ_OPS,
    TransportError,
    acquire_snapshot,
    loads_strict,
)


def event(**kw):
    value = dict(
        event_id="e1",
        target="page",
        revision=1,
        state="SUCCEEDED",
        properties={"Status": "SUCCEEDED"},
        mapping_version=1,
    )
    value.update(kw)
    return value


def test_r09_readonly_blocks_projection_and_unknown():
    t = FakeTransport(allowed_targets={"page"}, token="demo", read_only=True)
    out = Projector().project(event(), 0, t, token="demo")
    assert out["status"] == "error"
    assert out["reason_code"] == "WRITE_BLOCKED"
    assert t.pages["page"].state == "Ready"
    q = t.call("databases.query", "page", {"filter": {}}, "demo")
    assert q["ok"] is True
    for op in sorted(MUTATING_OPS):
        try:
            t.call(op, "page", {"event_id": "x", "revision": 1, "properties": {}}, "demo")
            raise AssertionError(op)
        except TransportError as exc:
            assert exc.reason_code == "WRITE_BLOCKED"
    with pytest.raises(TransportError) as ei:
        t.call("not.a.real.op", "page", {}, "demo")
    assert ei.value.reason_code == "WRITE_BLOCKED"


def test_r10_same_revision_terminal_rollback():
    t = FakeTransport(allowed_targets={"page"}, token="demo")
    pr = Projector()
    pr.project(event(), 0, t, token="demo")
    out = pr.project(event(event_id="e2", state="RUNNING"), 0, t, token="demo")
    assert out["status"] == "error"
    assert t.pages["page"].state == "SUCCEEDED"


def test_r11_untrusted_retry_override():
    t = FakeTransport(allowed_targets={"page"}, token="demo", fail_timeouts=5)
    out = Projector(retry_budget=1).project(event(retry_budget=6), 0, t, token="demo")
    assert len(t.calls) == 1
    assert out["reason_code"] == "PROJECTION_TIMEOUT"


def test_r15_unmapped_and_protected_fields():
    t = FakeTransport(allowed_targets={"page"}, token="demo")
    out = Projector().project(
        event(properties={"Decision": "APPROVED", "unexpected": "value"}),
        0,
        t,
        token="demo",
    )
    assert out["status"] == "error"
    assert "Decision" not in t.pages["page"].properties
    assert t.pages["page"].properties == {}


def test_same_event_payload_conflict():
    t = FakeTransport(allowed_targets={"page"}, token="demo")
    pr = Projector()
    pr.project(event(), 0, t, token="demo")
    out = pr.project(event(state="FAILED"), 0, t, token="demo")
    assert out["reason_code"] == "EVENT_CONFLICT"
    assert t.pages["page"].state == "SUCCEEDED"


def test_read_ops_unchanged():
    assert "databases.query" in READ_OPS
    assert "projection.apply" in MUTATING_OPS
    assert "projection.apply" not in READ_OPS


def test_acquire_missing_target():
    t = FakeTransport(allowed_targets={"page"}, token="demo", read_only=True)
    out = acquire_snapshot(
        t, target=None, token="demo", allowlist={"page"}, fetched_at_utc="2026-09-10T00:00:00Z"
    )
    assert out["reason_code"] == "NOTION_TARGET_MISSING"


def test_acquire_pagination_and_drift():
    t = FakeTransport(
        allowed_targets={"page"},
        token="demo",
        read_only=True,
        page_size=1,
        drift_after_reads=1,
        files={"https://files.notion.example/a.bin": b"abc"},
    )
    t.pages["page"].raw_markdown = "hello token=secret_abc"
    t.pages["page"].blocks = [
        {"id": "b1", "type": "text"},
        {
            "id": "f1",
            "type": "file",
            "url": "https://files.notion.example/a.bin",
            "filename": "a.bin",
            "bytes": 3,
            "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        },
    ]
    out = acquire_snapshot(
        t, target="page", token="demo", allowlist={"page"}, fetched_at_utc="2026-09-10T00:00:00Z"
    )
    assert out["reason_code"] == "SNAPSHOT_DRIFT"
    rec = out["receipt"]
    assert rec["raw_content_sha256"] != rec["content_sha256"]
    assert rec["custody"] == "SNAPSHOT_DRIFT"
    assert t.download_forwarded_auth == 0


def test_redirect_does_not_forward_auth():
    t = FakeTransport(allowed_targets={"page"}, token="demo", read_only=True)
    with pytest.raises(TransportError) as ei:
        t.download_attachment(
            "https://cdn.example/file.bin",
            {"Authorization": "Bearer x"},
        )
    assert ei.value.reason_code == "REDIRECT_CREDENTIAL_LEAK"


def test_loads_strict_rejects_nan():
    with pytest.raises(Exception):
        loads_strict('{"x":NaN}')
