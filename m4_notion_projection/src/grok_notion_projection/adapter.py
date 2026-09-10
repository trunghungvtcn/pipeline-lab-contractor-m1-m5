"""Projection adapter. Reflects job state; never starts compute."""
from __future__ import annotations

from typing import Any, Callable, Protocol

from .canon import envelope
from .fake_transport import FakeTransport, PROTECTED_FIELDS, TransportError
from .mapping import resolve_mapping
from .redaction import redact

TERMINAL = frozenset({"CANCELLED", "FAILED", "RECONCILE_REQUIRED", "SUCCEEDED"})


class Transport(Protocol):
    def call(self, op: str, target: str, payload: dict[str, Any], token: str) -> dict[str, Any]: ...


class Projector:
    def __init__(
        self,
        *,
        clock: Callable[[], int] | None = None,
        id_gen: Callable[[], str] | None = None,
        retry_budget: int = 3,
    ) -> None:
        from .canon import SystemClock, UuidGen

        self._clock = clock or (lambda: SystemClock().now_ns())
        self._id = id_gen or (lambda: UuidGen().new_id())
        self.retry_budget = max(1, int(retry_budget))

    def project(
        self,
        event: dict[str, Any],
        expected_revision: int,
        transport: Transport,
        *,
        token: str,
        compute: Callable[[], Any] | None = None,
    ) -> dict[str, Any]:
        trace = self._id()
        try:
            target = event.get("target")
            if not target:
                return envelope(status="error", reason_code="INVALID_EVENT", trace_id=trace)
            if "event_id" not in event or "revision" not in event:
                return envelope(status="error", reason_code="INVALID_EVENT", trace_id=trace)
            try:
                mapping = resolve_mapping(int(event.get("mapping_version", 1)))
            except (KeyError, TypeError, ValueError):
                return envelope(status="error", reason_code="UNKNOWN_MAPPING", trace_id=trace)

            if int(event["revision"]) < int(expected_revision):
                return envelope(
                    status="error",
                    reason_code="STALE_REVISION",
                    trace_id=trace,
                    extra={"expected_revision": expected_revision},
                )

            props_in = dict(event.get("properties") or {})
            allowed = set(mapping.keys())
            for key in props_in:
                if key in PROTECTED_FIELDS:
                    return envelope(status="error", reason_code="PROTECTED_FIELD", trace_id=trace)
                if key not in allowed:
                    return envelope(status="error", reason_code="UNMAPPED_FIELD", trace_id=trace)
            # Store allowlisted synthetic names; never forward unknown/protected fields.
            projected_props = {k: props_in[k] for k in props_in}

            payload = {
                "event_id": event["event_id"],
                "job_id": event.get("job_id"),
                "mapping_version": int(event.get("mapping_version", 1)),
                "properties": projected_props,
                "revision": int(event["revision"]),
                "state": event.get("state"),
            }

            # Event retry_budget must not raise the server cap.
            budget = self.retry_budget
            if "retry_budget" in event:
                try:
                    ev_budget = int(event["retry_budget"])
                except (TypeError, ValueError):
                    ev_budget = budget
                if ev_budget < 1:
                    return envelope(status="error", reason_code="INVALID_EVENT", trace_id=trace)
                budget = min(budget, ev_budget)

            last_err = "TIMEOUT"
            for _ in range(budget):
                try:
                    result = transport.call("projection.apply", target, payload, token)
                    if compute is not None:
                        pass
                    return envelope(
                        status="ok",
                        reason_code="IDEMPOTENT_HIT" if result.get("idempotent") else "OK",
                        trace_id=trace,
                        extra=redact(
                            {
                                "job_id": event.get("job_id"),
                                "revision": result.get("revision"),
                                "state": result.get("state"),
                                "target": target,
                            }
                        ),
                    )
                except TransportError as exc:
                    if exc.reason_code == "TIMEOUT":
                        last_err = "PROJECTION_TIMEOUT"
                        continue
                    return envelope(status="error", reason_code=exc.reason_code, trace_id=trace)
            return envelope(status="error", reason_code=last_err, trace_id=trace)
        except TransportError as exc:
            return envelope(status="error", reason_code=exc.reason_code, trace_id=trace)

    @staticmethod
    def assert_no_compute(transport: FakeTransport) -> None:
        if transport.compute_calls:
            raise AssertionError("compute was invoked during projection")
