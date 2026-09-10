"""Canonical JSON + result envelope. Stdlib only."""
from __future__ import annotations

import json
import math
import uuid
from typing import Any, Callable, Mapping


SCHEMA_VERSION = 1


class DuplicateKeyError(ValueError):
    pass


def _reject_nonfinite(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise ValueError("NaN/Infinity are not allowed")
    if isinstance(obj, dict):
        return {k: _reject_nonfinite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_reject_nonfinite(v) for v in obj]
    return obj


def object_hook_no_dup(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise DuplicateKeyError(k)
        out[k] = v
    return out


def _parse_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {name}")


def _parse_float(text: str) -> float:
    value = float(text)
    if math.isnan(value) or math.isinf(value):
        raise ValueError("non-finite JSON number")
    return value


def loads_strict(data: str | bytes) -> Any:
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    parsed = json.loads(
        data,
        parse_constant=_parse_constant,
        parse_float=_parse_float,
        object_pairs_hook=object_hook_no_dup,
    )
    return _reject_nonfinite(parsed)


def dumps_canonical(obj: Any) -> bytes:
    cleaned = _reject_nonfinite(obj)
    return json.dumps(
        cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def envelope(
    *,
    status: str,
    reason_code: str,
    trace_id: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "reason_code": reason_code,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "trace_id": trace_id or str(uuid.uuid4()),
    }
    if extra:
        for k, v in extra.items():
            if k not in body:
                body[k] = v
    return body


class SystemClock:
    def now_ns(self) -> int:
        import time

        return time.time_ns()


class UuidGen:
    def new_id(self) -> str:
        return str(uuid.uuid4())


ClockFn = Callable[[], int]
IdFn = Callable[[], str]
