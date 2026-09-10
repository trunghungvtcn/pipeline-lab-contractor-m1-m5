"""Documented public transport contract for M5.

Pipeline talks only to this protocol. Fake internals (.pages, PageState,
applied_events) are not part of the production boundary.
"""
from __future__ import annotations

from typing import Any, Protocol


class Transport(Protocol):
    def call(self, op: str, target: str, payload: dict[str, Any], token: str) -> dict[str, Any]: ...
