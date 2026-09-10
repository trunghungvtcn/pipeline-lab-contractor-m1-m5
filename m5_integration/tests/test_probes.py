from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from grok_pipeline import Pipeline
from grok_notion_projection import FakeTransport


def test_r01_write_before_validate(tmp_path: Path):
    pipe = Pipeline(str(tmp_path / "pipeline"))
    sentinel = tmp_path / "pipeline" / "sentinel.txt"
    sentinel.write_bytes(b"BEFORE")
    before_writes = pipe.writes
    out = pipe.run(
        scope="demo",
        idempotency_key="escape",
        request={},
        sources={"../sentinel.txt": b"AFTER"},
    )
    assert out.get("reason_code") == "LOCATOR_REJECTED"
    assert sentinel.read_bytes() == b"BEFORE"
    assert pipe.writes == before_writes


def test_r12_projection_retry_after_terminal(tmp_path: Path):
    t = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token", fail_timeouts=3)
    p = Pipeline(str(tmp_path / "projection-loss"), transport=t)
    args = dict(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    first = p.run(**args)
    assert first["status"] != "ok"
    second = p.run(**args)
    assert second["status"] == "ok"
    assert t.pages["sandbox-page-001"].state == "SUCCEEDED"
    assert first.get("result_digest")
    assert first["result_digest"] == second["result_digest"]


def test_r13_source_in_identity(tmp_path: Path):
    p = Pipeline(str(tmp_path / "source-identity"))
    a = p.run(scope="s", idempotency_key="k", request={}, sources={"a": b"A"})
    b = p.run(scope="s", idempotency_key="k", request={}, sources={"a": b"B"})
    assert a["status"] == "ok"
    assert b["reason_code"] == "DIGEST_CONFLICT"


def test_a_slash_b_and_a_dunder_b_do_not_collide(tmp_path: Path):
    p = Pipeline(str(tmp_path))
    rec = p.run(
        scope="s",
        idempotency_key="k",
        request={},
        sources={"a/b": b"one", "a__b": b"two"},
    )
    assert rec["status"] == "ok"
    assert rec["freeze"]["blob_count"] == 2


def test_concurrent_pipeline_same_and_different_keys(tmp_path: Path):
    root = tmp_path / "c"
    errors: list[BaseException] = []
    results: list[dict] = []
    lock = threading.Lock()
    barrier = threading.Barrier(4)

    def worker(key: str, payload: bytes):
        try:
            barrier.wait()
            rec = Pipeline(str(root)).run(
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
        threading.Thread(target=worker, args=("same", b"A")),
        threading.Thread(target=worker, args=("same", b"A")),
        threading.Thread(target=worker, args=("other", b"B")),
        threading.Thread(target=worker, args=("other2", b"C")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert results
    ok = [r for r in results if r.get("status") == "ok"]
    assert len(ok) >= 3
