"""Strip tokens and signed URLs from logs and receipts."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

TOKEN_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~\-+/=]+|secret_[a-z0-9]+|ntn_[a-z0-9]+|sk-[a-z0-9]+)"
)
SIGNED_QUERY_KEYS = {
    "awsaccesskeyid",
    "signature",
    "x-amz-signature",
    "x-amz-credential",
    "x-amz-security-token",
    "token",
    "expires",
    "x-amz-expires",
    "x-amz-date",
}


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    q = parse_qsl(parts.query, keep_blank_values=True)
    if any(k.lower() in SIGNED_QUERY_KEYS for k, _ in q):
        return "[REDACTED_SIGNED_URL]"
    return urlunsplit(parts)


def redact_text(text: str) -> str:
    text = TOKEN_RE.sub("[REDACTED_TOKEN]", text)
    def _url(match: re.Match[str]) -> str:
        return redact_url(match.group(0))

    return re.sub(r"https?://[^\s\"'<>]+", _url, text)


def redact(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            key = k.lower()
            if key in {"authorization", "token", "secret", "api_key", "signed_url"}:
                out[k] = "[REDACTED_TOKEN]"
            else:
                out[k] = redact(v)
        return out
    return obj
