from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from grok_notion_projection import FakeTransport
from grok_pipeline import Pipeline


class PublicOnlyTransport:
    """Conforming facade: documented call() only. No fake internals."""

    __slots__ = ("_inner",)

    def __init__(self, inner: FakeTransport):
        object.__setattr__(self, "_inner", inner)

    def call(self, op, target, payload, token):
        return object.__getattribute__(self, "_inner").call(op, target, payload, token)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_public_wrapper_has_no_fake_internals():
    inner = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token")
    wrapper = PublicOnlyTransport(inner)
    assert not hasattr(wrapper, "pages")
    try:
        _ = wrapper.pages
        raise AssertionError("pages must not exist")
    except AttributeError as exc:
        assert "pages" in str(exc)


def test_two_sequential_jobs_through_public_transport(tmp_path: Path):
    inner = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token")
    wrapper = PublicOnlyTransport(inner)
    p = Pipeline(str(tmp_path / "seq"), transport=wrapper)
    a = p.run(scope="s", idempotency_key="one", request={}, sources={"a": b"A"})
    b = p.run(scope="s", idempotency_key="two", request={}, sources={"b": b"B"})
    assert a["status"] == "ok"
    assert b["status"] == "ok"
    assert a["job_id"] != b["job_id"]
    page = inner.call("pages.retrieve", "sandbox-page-001", {}, "sandbox-token")
    assert page["revision"] == 2
    assert page["state"] == "SUCCEEDED"


def test_replay_idempotent_through_public_transport(tmp_path: Path):
    inner = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token")
    wrapper = PublicOnlyTransport(inner)
    p = Pipeline(str(tmp_path / "replay"), transport=wrapper)
    args = dict(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    a = p.run(**args)
    b = p.run(**args)
    assert a["status"] == b["status"] == "ok"
    assert a["job_id"] == b["job_id"]
    assert a["result_digest"] == b["result_digest"]
    page = inner.call("pages.retrieve", "sandbox-page-001", {}, "sandbox-token")
    assert page["revision"] == 1


def test_projection_timeout_retry_through_public_transport(tmp_path: Path):
    inner = FakeTransport(
        allowed_targets={"sandbox-page-001"}, token="sandbox-token", fail_timeouts=3
    )
    wrapper = PublicOnlyTransport(inner)
    p = Pipeline(str(tmp_path / "retry"), transport=wrapper)
    args = dict(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    first = p.run(**args)
    assert first["status"] != "ok"
    second = p.run(**args)
    assert second["status"] == "ok"
    assert first.get("result_digest") == second.get("result_digest")


def test_restart_through_public_transport(tmp_path: Path):
    now = {"ns": 1_000}
    root = tmp_path / "restart"
    inner = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token")
    wrapper = PublicOnlyTransport(inner)
    p = Pipeline(str(root), transport=wrapper, clock=lambda: now["ns"], lease_ms=1)
    p.crash_at = "after_result"
    first = p.run(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    assert first["reason_code"] == "CRASH_INJECTED"
    now["ns"] = 10**12
    p2 = Pipeline(str(root), transport=wrapper, clock=lambda: now["ns"], lease_ms=10_000)
    second = p2.run(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    assert second["status"] == "ok"
    assert p2.compute_calls == 0
    page = inner.call("pages.retrieve", "sandbox-page-001", {}, "sandbox-token")
    assert page["state"] == "SUCCEEDED"


def test_concurrent_jobs_through_public_transport(tmp_path: Path):
    inner = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token")
    wrapper = PublicOnlyTransport(inner)
    root = tmp_path / "conc"
    errors: list[BaseException] = []
    results: list[dict] = []
    lock = threading.Lock()
    barrier = threading.Barrier(3)

    def worker(key: str, payload: bytes):
        try:
            barrier.wait()
            rec = Pipeline(str(root), transport=wrapper).run(
                scope="s",
                idempotency_key=key,
                request={},
                sources={"docs/manual.txt": payload},
            )
            with lock:
                results.append(rec)
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("a", b"A")),
        threading.Thread(target=worker, args=("b", b"B")),
        threading.Thread(target=worker, args=("c", b"C")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    ok = [r for r in results if r.get("status") == "ok"]
    assert len(ok) == 3
