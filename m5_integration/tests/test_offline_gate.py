from __future__ import annotations

import os
from pathlib import Path

from grok_pipeline import Pipeline

FORBIDDEN = (
    "BEGIN RSA PRIVATE KEY",
    "secret_live",
    "ghp_",
)
THBISON_RAW = ("trunghungvtcn@gmail.com", "0862.060.316")


def test_no_secret_env_required(tmp_path: Path, monkeypatch):
    for key in list(os.environ):
        if "TOKEN" in key or "SECRET" in key or "NOTION" in key:
            monkeypatch.delenv(key, raising=False)
    pipe = Pipeline(str(tmp_path))
    rec = pipe.run(
        scope="demo-tenant/synthetic-project",
        idempotency_key="demo-job-001",
        request={"operation": "extract_demo_claims", "source_id": "synthetic-manual"},
        sources={"docs/manual.txt": b"Synthetic lifting manual revision A."},
    )
    assert rec["status"] == "ok"


def test_source_scan_no_tokens_or_raw_thbison():
    root = Path(__file__).resolve().parents[2]
    hits: list[str] = []
    for mod in ("m1_locator", "m2_asset_store", "m3_job_ledger", "m4_notion_projection", "m5_integration"):
        for path in (root / mod / "src").rglob("*"):
            if path.suffix not in {".py", ".json", ".md", ".toml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in FORBIDDEN + THBISON_RAW:
                if needle in text:
                    hits.append(f"{path}:{needle}")
    assert hits == []
