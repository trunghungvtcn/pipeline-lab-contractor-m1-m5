from __future__ import annotations

from grok_notion_projection import build_receipt, redact
from grok_notion_projection.snapshot import AttachmentMeta


def test_redact_token_and_signed_url():
    payload = {
        "authorization": "Bearer secret_live_abc",
        "note": "token=secret_abc and https://s3.amazonaws.com/x?X-Amz-Signature=deadbeef&Expires=1",
    }
    out = redact(payload)
    blob = str(out)
    assert "secret_live" not in blob
    assert "deadbeef" not in blob
    assert "[REDACTED_TOKEN]" in out["authorization"]
    assert "[REDACTED_SIGNED_URL]" in out["note"]


def test_snapshot_receipt_hashes_redacted_markdown():
    md = "page body token=secret_abc https://s3.example/x?X-Amz-Signature=ffff"
    rec = build_receipt(
        page_id="11111111-1111-1111-1111-111111111111",
        title="sandbox architecture",
        fetched_at_utc="2026-09-10T00:00:00Z",
        last_edited_time="2026-09-01T00:00:00Z",
        markdown=md,
        flags=["SNAPSHOT_DRIFT"],
        attachments=[
            AttachmentMeta(
                attachment_id="att-1",
                block_id="blk-1",
                filename="demo.csv",
                reported_bytes=12,
                reported_sha256="a" * 64,
                status="META_ONLY",
            )
        ],
        child_databases_listed=["Evidence Sources"],
    )
    d = rec.to_dict()
    assert d["child_databases_queried"] is False
    assert d["knowledge_content_read"] is False
    assert "secret_abc" not in str(d)
    assert "ffff" not in d["content_sha256"]
    assert len(d["content_sha256"]) == 64
    assert "SNAPSHOT_DRIFT" in d["flags"]
