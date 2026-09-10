"""Integration harness. Imports public APIs only; does not patch child modules."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Callable

from grok_asset_store import AssetStore, DictReader, SourceRef
from grok_job_ledger import JobLedger
from grok_locator import LocatorProfile, LocatorResolver, dumps_canonical, loads_strict
from grok_notion_projection import FakeTransport, Projector

from . import fake_compute


def synthetic_request_digest(request: dict[str, Any], sources: dict[str, bytes] | None = None) -> str:
    if sources is None:
        return hashlib.sha256(dumps_canonical(request)).hexdigest()
    payload = {
        "request": request,
        "sources": [
            {"locator": loc, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for loc, data in sorted(sources.items())
        ],
    }
    return hashlib.sha256(dumps_canonical(payload)).hexdigest()


def _safe_source_id(locator: str) -> str:
    return "s-" + hashlib.sha256(locator.encode("utf-8")).hexdigest()[:32]


class Pipeline:
    def __init__(
        self,
        root: str,
        *,
        clock: Callable[[], int] | None = None,
        id_gen: Callable[[], str] | None = None,
        transport: FakeTransport | None = None,
    ) -> None:
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.resolver = LocatorResolver(clock=clock, id_gen=id_gen)
        self.store = AssetStore(clock=clock, id_gen=id_gen)
        self.ledger = JobLedger(os.path.join(root, "jobs.db"), clock=clock, id_gen=id_gen)
        self.projector = Projector(clock=clock, id_gen=id_gen)
        self.transport = transport or FakeTransport(
            allowed_targets={"sandbox-page-001"}, token="sandbox-token"
        )
        self.profile = LocatorProfile(
            dialect="posix",
            root_id="demo-root",
            case_policy="sensitive",
            unicode_policy="nfc_only",
        )
        self.writes = 0

    def _write(self, path: str, data: bytes) -> None:
        self.writes += 1
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def _project_event(self, job_id: str, result_digest: str, idempotency_key: str) -> dict[str, Any]:
        return {
            "event_id": f"proj-{job_id}-{result_digest[:12]}",
            "job_id": job_id,
            "mapping_version": 1,
            "properties": {
                "Result Ref": f"synthetic://result/{idempotency_key}",
                "Status": "SUCCEEDED",
            },
            "revision": 1,
            "state": "SUCCEEDED",
            "target": "sandbox-page-001",
        }

    def _replay_terminal(self, admitted: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        job_id = admitted["job_id"]
        row = self.ledger.get(job_id)
        result_digest = row.get("result_digest")
        if row.get("state") != "SUCCEEDED":
            return {
                **admitted,
                "result_digest": result_digest,
                "status": "ok" if admitted["status"] == "ok" else admitted["status"],
            }
        event = None
        if row.get("outbox"):
            try:
                event = json.loads(row["outbox"])
            except (TypeError, ValueError):
                event = None
        if event is None and result_digest:
            event = self._project_event(job_id, result_digest, idempotency_key)
        projected = {"status": "ok", "reason_code": "IDEMPOTENT_HIT", "state": "SUCCEEDED"}
        if row.get("projection_status") != "APPLIED" and event is not None:
            projected = self.projector.project(
                event, int(event.get("revision") or 1), self.transport, token="sandbox-token", compute=None
            )
            if projected["status"] == "ok":
                self.ledger.mark_projected(job_id, json.dumps(event), row.get("result_payload"))
        status = projected["status"]
        return {
            "admit": admitted,
            "job_id": job_id,
            "project": projected,
            "result_digest": result_digest,
            "status": status,
        }

    def run(
        self,
        *,
        scope: str,
        idempotency_key: str,
        request: dict[str, Any],
        sources: dict[str, bytes],
        worker_id: str = "worker-a",
    ) -> dict[str, Any]:
        # Syntax/containment before any mkdir/open/write of untrusted names.
        for locator in sources:
            checked = self.resolver.validate(locator, self.profile)
            if checked["status"] != "ok":
                return checked

        digest = synthetic_request_digest(request, sources)
        admitted = self.ledger.admit(scope, idempotency_key, digest)
        if admitted["status"] != "ok":
            return admitted
        job_id = admitted["job_id"]
        if admitted["reason_code"] == "IDEMPOTENT_HIT" and admitted.get("state") in {
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "RECONCILE_REQUIRED",
        }:
            return self._replay_terminal(admitted, idempotency_key)

        claim = self.ledger.claim(job_id, worker_id, 30_000)
        if claim["status"] != "ok":
            if claim["reason_code"] == "LEASE_HELD":
                return claim
            return claim

        job_root = os.path.join(self.root, "jobs", job_id)
        os.makedirs(job_root, exist_ok=True)
        # Persist inputs under opaque names only — never join untrusted locators.
        input_dir = os.path.join(job_root, "inputs")
        os.makedirs(input_dir, exist_ok=True)
        refs: list[SourceRef] = []
        reader_map: dict[str, bytes] = {}
        for locator, data in sources.items():
            sid = _safe_source_id(locator)
            self._write(os.path.join(input_dir, sid), data)
            resolved = self.resolver.resolve(
                input_dir,
                sid,
                self.profile,
                expected_sha256=hashlib.sha256(data).hexdigest(),
            )
            if resolved["status"] != "ok":
                return resolved
            refs.append(SourceRef(sid, sid, resolved["sha256"]))
            reader_map[sid] = data

        frozen = self.store.freeze(job_root, refs, DictReader(reader_map))
        if frozen["status"] != "ok":
            return frozen

        result_path = os.path.join(job_root, "result.json")
        if frozen.get("reason_code") == "IDEMPOTENT_HIT" and os.path.isfile(result_path):
            result = loads_strict(open(result_path, "rb").read())
        else:
            result = fake_compute.run(frozen["manifest_sha256"], request)
            artifact = dumps_canonical(result)
            self._write(result_path, artifact)
        if "result_digest" not in result:
            return {"status": "error", "reason_code": "COMPUTE_INVALID"}
        artifact_text = dumps_canonical(result).decode("utf-8")
        event = self._project_event(job_id, result["result_digest"], idempotency_key)
        self.ledger.store_outbox(job_id, json.dumps(event), artifact_text)

        final = self.ledger.finalize(
            job_id, claim["lease_token"], claim["fence"], "SUCCEEDED", result["result_digest"]
        )
        if final["status"] != "ok":
            return final

        projected = self.projector.project(
            event, 1, self.transport, token="sandbox-token", compute=None
        )
        if projected["status"] == "ok":
            self.ledger.mark_projected(job_id, json.dumps(event), artifact.decode("utf-8"))
        return {
            "admit": admitted,
            "finalize": final,
            "freeze": frozen,
            "job_id": job_id,
            "project": projected,
            "result_digest": result["result_digest"],
            "status": projected["status"],
        }
