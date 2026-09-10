from __future__ import annotations

from pathlib import Path

from grok_asset_store import AssetStore, DictReader, SourceRef
from grok_pipeline import Pipeline

SOURCES = {"docs/manual.txt": b"Synthetic lifting manual revision A."}
REQUEST = {"operation": "extract_demo_claims", "source_id": "synthetic-manual"}


def test_restart_reopens_same_ledger(tmp_path: Path):
    a = Pipeline(str(tmp_path))
    rec = a.run(scope="demo-tenant/synthetic-project", idempotency_key="demo-job-001", request=REQUEST, sources=SOURCES)
    job_id = rec["job_id"]
    b = Pipeline(str(tmp_path))
    row = b.ledger.get(job_id)
    assert row["state"] == "SUCCEEDED"
    assert row["result_digest"] == rec["result_digest"]


def test_crash_before_manifest_leaves_unpublished(tmp_path: Path):
    payload = b"data"
    digest = __import__("hashlib").sha256(payload).hexdigest()
    rec = AssetStore(crash_after_writes=1).freeze(
        str(tmp_path / "job"),
        [SourceRef("s1", "p/a.txt", digest)],
        DictReader({"p/a.txt": payload}),
    )
    assert rec["reason_code"] == "CRASH_INJECTED"
    assert not AssetStore.is_published(str(tmp_path / "job"))
