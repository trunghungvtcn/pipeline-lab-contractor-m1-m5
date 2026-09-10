"""In-memory Notion-compatible transport. Fail-closed. Never talks to a real workspace."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

from .canon import dumps_canonical
from .redaction import redact

MUTATING_OPS = frozenset(
    {
        "blocks.append",
        "blocks.delete",
        "blocks.update",
        "comments.create",
        "databases.create",
        "databases.update",
        "pages.create",
        "pages.delete",
        "pages.update",
        "projection.apply",
        "properties.Decision",
        "properties.Reviewer Note",
        "properties.Status",
    }
)
READ_OPS = frozenset(
    {
        "blocks.retrieve",
        "databases.query",
        "files.download",
        "pages.retrieve",
        "search",
    }
)
PROTECTED_FIELDS = frozenset({"Decision", "Reviewer Note"})
TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "RECONCILE_REQUIRED"})


class TransportError(Exception):
    def __init__(self, reason_code: str, message: str = ""):
        super().__init__(message or reason_code)
        self.reason_code = reason_code


@dataclass
class PageState:
    target: str
    revision: int = 0
    state: str = "Ready"
    last_edited: str = "1970-01-01T00:00:00Z"
    properties: dict[str, Any] = field(default_factory=dict)
    applied_events: dict[str, dict[str, Any]] = field(default_factory=dict)
    blocks: list[dict[str, Any]] = field(default_factory=list)
    raw_markdown: str = ""


class FakeTransport:
    """Injectable fake. Clock and timeout injector are test hooks."""

    def __init__(
        self,
        *,
        allowed_targets: set[str],
        token: str,
        read_only: bool = False,
        clock: Callable[[], int] | None = None,
        fail_timeouts: int = 0,
        files: dict[str, bytes] | None = None,
        page_size: int = 2,
        drift_after_reads: int = 0,
    ) -> None:
        self.allowed_targets = set(allowed_targets)
        self.token = token
        self.read_only = read_only
        self._clock = clock or (lambda: 0)
        self._fail_timeouts = fail_timeouts
        self.pages: dict[str, PageState] = {t: PageState(target=t) for t in allowed_targets}
        self.calls: list[dict[str, Any]] = []
        self.compute_calls = 0
        self.files = dict(files or {})
        self.page_size = page_size
        self.drift_after_reads = drift_after_reads
        self._retrieves = 0
        self.download_hosts: list[str] = []
        self.download_forwarded_auth = 0

    def _auth(self, token: str, target: str) -> None:
        if token != self.token:
            raise TransportError("AUTH_DENIED")
        if target not in self.allowed_targets:
            raise TransportError("TARGET_OUT_OF_SCOPE")

    def public_ops(self) -> set[str]:
        return set(MUTATING_OPS) | set(READ_OPS)

    def call(self, op: str, target: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
        rec = redact({"at_ns": self._clock(), "op": op, "payload": payload, "target": target})
        self.calls.append(rec)
        self._auth(token, target)

        if self._fail_timeouts > 0:
            self._fail_timeouts -= 1
            raise TransportError("TIMEOUT")

        # Fail-closed: anything not on the read allowlist is a mutation.
        if op not in READ_OPS:
            if self.read_only:
                raise TransportError("WRITE_BLOCKED")
            if op not in MUTATING_OPS:
                raise TransportError("UNKNOWN_OP")

        if op == "files.download":
            return self.download_attachment(payload.get("url", ""), payload.get("headers") or {})

        if op == "pages.retrieve":
            return self._retrieve_page(target)

        if op == "blocks.retrieve":
            return self._retrieve_blocks(target, payload)

        if op in READ_OPS:
            page = self.pages[target]
            return {"ok": True, "op": op, "properties": dict(page.properties), "revision": page.revision}

        return self._apply_projection(target, payload)

    def _retrieve_page(self, target: str) -> dict[str, Any]:
        self._retrieves += 1
        page = self.pages[target]
        if self.drift_after_reads and self._retrieves > self.drift_after_reads:
            page.last_edited = "2099-01-01T00:00:00Z"
            page.revision += 1
        return {
            "ok": True,
            "op": "pages.retrieve",
            "id": target,
            "revision": page.revision,
            "last_edited_time": page.last_edited,
            "properties": dict(page.properties),
            "markdown": page.raw_markdown,
        }

    def _retrieve_blocks(self, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        page = self.pages[target]
        blocks = list(page.blocks)
        cursor = payload.get("start_cursor") or 0
        try:
            cursor = int(cursor)
        except (TypeError, ValueError):
            cursor = 0
        chunk = blocks[cursor : cursor + self.page_size]
        nxt = cursor + self.page_size
        has_more = nxt < len(blocks)
        return {
            "ok": True,
            "blocks": chunk,
            "has_more": has_more,
            "next_cursor": str(nxt) if has_more else None,
        }

    def _event_digest(self, payload: dict[str, Any]) -> str:
        body = {
            "event_id": payload.get("event_id"),
            "properties": payload.get("properties") or {},
            "revision": int(payload.get("revision") or 0),
            "state": payload.get("state"),
        }
        return hashlib.sha256(dumps_canonical(body)).hexdigest()

    def _apply_projection(self, target: str, payload: dict[str, Any]) -> dict[str, Any]:
        page = self.pages[target]
        event_id = payload["event_id"]
        revision = int(payload["revision"])
        new_state = payload.get("state") or page.state
        digest = self._event_digest(payload)

        if event_id in page.applied_events:
            prev = page.applied_events[event_id]
            if prev.get("digest") != digest:
                raise TransportError("EVENT_CONFLICT")
            return {"idempotent": True, "ok": True, "revision": page.revision, "state": page.state}

        if revision < page.revision:
            raise TransportError("STALE_REVISION")
        if page.revision != 0 and revision == page.revision:
            raise TransportError("REVISION_CONFLICT")
        if page.revision != 0 and revision != page.revision + 1:
            raise TransportError("REVISION_CONFLICT")

        if page.state in TERMINAL_STATES and new_state not in TERMINAL_STATES:
            raise TransportError("TERMINAL_LOCKED")
        if page.state in TERMINAL_STATES and new_state in TERMINAL_STATES and new_state != page.state:
            raise TransportError("TERMINAL_LOCKED")

        props_in = payload.get("properties") or {}
        if any(k in PROTECTED_FIELDS for k in props_in):
            raise TransportError("PROTECTED_FIELD")

        props = dict(page.properties)
        props.update(props_in)
        page.properties = props
        page.revision = revision
        page.state = new_state
        applied = {"digest": digest, "event_id": event_id, "revision": page.revision, "state": page.state}
        page.applied_events[event_id] = applied
        return {"idempotent": False, "ok": True, "event_id": event_id, "revision": page.revision, "state": page.state}

    def download_attachment(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        host = (urlsplit(url).hostname or "").lower()
        self.download_hosts.append(host)
        has_auth = any(k.lower() == "authorization" for k in headers)
        if has_auth and host not in {"files.notion.example", "localhost"}:
            self.download_forwarded_auth += 1
            raise TransportError("REDIRECT_CREDENTIAL_LEAK")
        data = self.files.get(url)
        if data is None:
            return {"ok": True, "bytes": 0, "host": host, "sha256": None, "status": "MISSING"}
        digest = hashlib.sha256(data).hexdigest()
        return {
            "ok": True,
            "bytes": len(data),
            "data": data,
            "host": host,
            "sha256": digest,
            "status": "DOWNLOADED",
        }
