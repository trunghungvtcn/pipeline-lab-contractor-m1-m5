from __future__ import annotations

from grok_notion_projection import FakeTransport, TransportError


def test_read_only_blocks_named_mutations_not_query():
    t = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token", read_only=True)
    q = t.call("databases.query", "sandbox-page-001", {"filter": {}}, "sandbox-token")
    assert q["ok"] is True
    for op in ("pages.update", "pages.create", "comments.create", "properties.Status"):
        try:
            t.call(op, "sandbox-page-001", {"properties": {"Status": "APPROVED"}}, "sandbox-token")
            raise AssertionError(op)
        except TransportError as exc:
            assert exc.reason_code == "WRITE_BLOCKED"


def test_attachment_redirect_does_not_forward_credential():
    t = FakeTransport(allowed_targets={"sandbox-page-001"}, token="sandbox-token")
    try:
        t.download_attachment(
            "https://cdn.example/file.bin?X-Amz-Signature=abc",
            {"Authorization": "Bearer secret_abc"},
        )
        raise AssertionError("should leak-detect")
    except TransportError as exc:
        assert exc.reason_code == "REDIRECT_CREDENTIAL_LEAK"
    ok = t.download_attachment("https://files.notion.example/a.bin", {"Authorization": "Bearer x"})
    assert ok["ok"] is True
