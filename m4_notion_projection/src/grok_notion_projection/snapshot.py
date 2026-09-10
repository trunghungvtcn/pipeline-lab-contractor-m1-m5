"""Read-only snapshot receipts. Raw hash ≠ redacted hash. Never self-certify VERIFIED."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from .canon import dumps_canonical, envelope
from .redaction import redact, redact_text


class ReadTransport(Protocol):
    def call(self, op: str, target: str, payload: dict[str, Any], token: str) -> dict[str, Any]: ...


@dataclass
class AttachmentMeta:
    attachment_id: str
    block_id: str
    filename: str
    reported_bytes: int
    reported_sha256: str
    status: str
    actual_sha256: str | None = None
    actual_bytes: int | None = None


@dataclass
class SnapshotReceipt:
    page_id: str
    title: str
    fetched_at_utc: str
    last_edited_time: str
    size_bytes: int
    content_sha256: str
    raw_content_sha256: str = ""
    custody: str = "NOT_VERIFIED"
    flags: list[str] = field(default_factory=list)
    attachments: list[AttachmentMeta] = field(default_factory=list)
    child_databases_listed: list[str] = field(default_factory=list)
    child_databases_queried: bool = False
    knowledge_content_read: bool = False
    block_ids: list[str] = field(default_factory=list)
    file_ids: list[str] = field(default_factory=list)
    revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        return redact(asdict(self))


def build_receipt(
    *,
    page_id: str,
    title: str,
    fetched_at_utc: str,
    last_edited_time: str,
    markdown: str,
    flags: list[str] | None = None,
    attachments: list[AttachmentMeta] | None = None,
    child_databases_listed: list[str] | None = None,
    custody: str | None = None,
    raw_markdown: str | None = None,
) -> SnapshotReceipt:
    raw = raw_markdown if raw_markdown is not None else markdown
    redacted = redact_text(markdown)
    digest = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
    raw_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    # Callers cannot force VERIFIED; only acquire_snapshot may set SNAPSHOT_CONSISTENT.
    allowed_custody = {"NOT_VERIFIED", "NOTION_TARGET_MISSING", "SNAPSHOT_CONSISTENT", "SNAPSHOT_DRIFT"}
    mark = custody if custody in allowed_custody and custody != "SNAPSHOT_CONSISTENT" else "NOT_VERIFIED"
    if custody == "VERIFIED":
        mark = "NOT_VERIFIED"
    return SnapshotReceipt(
        page_id=page_id,
        title=title,
        fetched_at_utc=fetched_at_utc,
        last_edited_time=last_edited_time,
        size_bytes=len(redacted.encode("utf-8")),
        content_sha256=digest,
        raw_content_sha256=raw_digest,
        custody=mark,
        flags=list(flags or []),
        attachments=list(attachments or []),
        child_databases_listed=list(child_databases_listed or []),
        child_databases_queried=False,
        knowledge_content_read=False,
    )


def dumps_receipt(receipt: SnapshotReceipt) -> bytes:
    return dumps_canonical(receipt.to_dict())


def acquire_snapshot(
    transport: ReadTransport,
    *,
    target: str | None,
    token: str,
    allowlist: set[str],
    fetched_at_utc: str,
    title: str = "sandbox",
) -> dict[str, Any]:
    """Read-only acquisition. Missing target → NOTION_TARGET_MISSING, no workspace scan."""
    if not target or target not in allowlist:
        rec = build_receipt(
            page_id=target or "",
            title=title,
            fetched_at_utc=fetched_at_utc,
            last_edited_time="",
            markdown="",
            flags=["NOTION_TARGET_MISSING"],
            custody="NOTION_TARGET_MISSING",
        )
        return envelope(
            status="error",
            reason_code="NOTION_TARGET_MISSING",
            extra={"custody": rec.custody, "receipt": rec.to_dict()},
        )
    page = transport.call("pages.retrieve", target, {}, token)
    revision_1 = int(page.get("revision") or 0)
    edited_1 = page.get("last_edited_time") or ""
    raw_md = page.get("markdown") or ""
    blocks: list[dict[str, Any]] = []
    cursor: str | None = "0"
    while cursor is not None:
        chunk = transport.call("blocks.retrieve", target, {"start_cursor": cursor}, token)
        blocks.extend(chunk.get("blocks") or [])
        cursor = chunk.get("next_cursor")
        if not chunk.get("has_more"):
            break
    attachments: list[AttachmentMeta] = []
    for block in blocks:
        if block.get("type") != "file":
            continue
        url = block.get("url") or ""
        headers = {"Range": "bytes=0-"}
        # Never forward Authorization on a cross-host download.
        dl = transport.call("files.download", target, {"url": url, "headers": headers}, token)
        reported = block.get("sha256") or ""
        actual = dl.get("sha256")
        status = "DOWNLOADED" if actual else "MISSING"
        if reported and actual and reported != actual:
            status = "CORRUPT"
        attachments.append(
            AttachmentMeta(
                attachment_id=block.get("id") or url,
                block_id=block.get("id") or "",
                filename=block.get("filename") or "file.bin",
                reported_bytes=int(block.get("bytes") or 0),
                reported_sha256=reported,
                status=status,
                actual_sha256=actual,
                actual_bytes=dl.get("bytes"),
            )
        )
    page2 = transport.call("pages.retrieve", target, {}, token)
    revision_2 = int(page2.get("revision") or 0)
    flags: list[str] = ["SYNTHETIC_TEST"]
    custody = "SNAPSHOT_CONSISTENT"
    if revision_1 != revision_2 or (page2.get("last_edited_time") or "") != edited_1:
        flags.append("SNAPSHOT_DRIFT")
        custody = "SNAPSHOT_DRIFT"
    if any(a.status == "CORRUPT" for a in attachments):
        flags.append("ATTACHMENT_CORRUPT")
        custody = "NOT_VERIFIED"
    rec = SnapshotReceipt(
        page_id=target,
        title=title,
        fetched_at_utc=fetched_at_utc,
        last_edited_time=edited_1,
        size_bytes=len(raw_md.encode("utf-8")),
        content_sha256=hashlib.sha256(redact_text(raw_md).encode("utf-8")).hexdigest(),
        raw_content_sha256=hashlib.sha256(raw_md.encode("utf-8")).hexdigest(),
        custody=custody,
        flags=flags,
        attachments=attachments,
        block_ids=[str(b.get("id")) for b in blocks if b.get("id")],
        file_ids=[a.attachment_id for a in attachments],
        revision=revision_1,
        child_databases_queried=False,
        knowledge_content_read=False,
    )
    reason = "OK" if custody == "SNAPSHOT_CONSISTENT" else custody
    status = "ok" if custody == "SNAPSHOT_CONSISTENT" else "error"
    return envelope(status=status, reason_code=reason, extra={"custody": custody, "receipt": rec.to_dict()})
