"""Deterministic fake compute. No models, no network."""
from __future__ import annotations

import hashlib
from typing import Any

from grok_locator import dumps_canonical


def run(frozen_manifest_sha: str, request: dict[str, Any]) -> dict[str, Any]:
    body = {
        "claims": [{"predicate": "demo_capacity", "unit": "demo-unit", "value": "1"}],
        "frozen_manifest_sha": frozen_manifest_sha,
        "request": request,
        "status": "SUCCEEDED",
    }
    digest = hashlib.sha256(dumps_canonical(body)).hexdigest()
    body["result_digest"] = digest
    return body
