from __future__ import annotations

import hashlib

from grok_notion_projection import FakeTransport, acquire_snapshot


EMPTY = hashlib.sha256(b"").hexdigest()


def test_g7_missing_attachment_not_consistent():
    t = FakeTransport(allowed_targets={"page"}, token="token", read_only=True)
    t.pages["page"].blocks = [
        {
            "id": "f1",
            "type": "file",
            "url": "https://files.notion.example/missing",
            "filename": "x.bin",
            "bytes": 10,
            "sha256": "0" * 64,
        }
    ]
    t.pages["page"].raw_markdown = "# hello"
    out = acquire_snapshot(t, target="page", token="token", allowlist={"page"}, fetched_at_utc="2026-09-10T00:00:00Z")
    assert out["custody"] != "SNAPSHOT_CONSISTENT"
    assert out["receipt"]["attachments"][0]["status"] == "MISSING"
    assert out["receipt"]["knowledge_content_read"] is True
    assert "SYNTHETIC_TEST" in out["receipt"]["flags"]
    assert out["receipt"]["notion_reads_performed"] >= 1


def test_g7_empty_file_ok():
    url = "https://files.notion.example/empty.bin"
    t = FakeTransport(allowed_targets={"page"}, token="token", files={url: b""})
    t.pages["page"].blocks = [
        {"id": "e1", "type": "file", "url": url, "filename": "e.bin", "bytes": 0, "sha256": EMPTY}
    ]
    out = acquire_snapshot(t, target="page", token="token", allowlist={"page"}, fetched_at_utc="2026-09-10T00:00:00Z")
    assert out["custody"] == "SNAPSHOT_CONSISTENT"
    assert out["receipt"]["attachments"][0]["status"] == "EMPTY_OK"


def test_g7_hash_and_size_mismatch():
    url = "https://files.notion.example/a.bin"
    t = FakeTransport(allowed_targets={"page"}, token="token", files={url: b"abc"})
    t.pages["page"].blocks = [
        {"id": "h1", "type": "file", "url": url, "filename": "a.bin", "bytes": 3, "sha256": "0" * 64}
    ]
    out = acquire_snapshot(t, target="page", token="token", allowlist={"page"}, fetched_at_utc="2026-09-10T00:00:00Z")
    assert out["custody"] == "NOT_VERIFIED"
    assert out["receipt"]["attachments"][0]["status"] == "HASH_MISMATCH"


def test_g7_redirect_cross_host():
    t = FakeTransport(allowed_targets={"page"}, token="token")
    t.pages["page"].blocks = [
        {
            "id": "r1",
            "type": "file",
            "url": "https://cdn.example/file.bin",
            "filename": "x.bin",
            "bytes": 1,
            "sha256": "0" * 64,
        }
    ]
    out = acquire_snapshot(t, target="page", token="token", allowlist={"page"}, fetched_at_utc="2026-09-10T00:00:00Z")
    assert out["custody"] == "NOT_VERIFIED"
    assert out["receipt"]["attachments"][0]["status"] == "UNSAFE_REDIRECT"
    assert t.download_forwarded_auth == 0


def test_g8_missing_target_no_search():
    t = FakeTransport(allowed_targets={"page"}, token="token")
    out = acquire_snapshot(t, target=None, token="token", allowlist={"page"}, fetched_at_utc="2026-09-10T00:00:00Z")
    assert out["reason_code"] == "NOTION_TARGET_MISSING"
    assert not any(c.get("op") == "search" for c in t.calls)
