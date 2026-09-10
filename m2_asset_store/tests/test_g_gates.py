from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from grok_asset_store import AssetStore, DictReader, SourceRef
from grok_asset_store.store import contained_under


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TrackingStore(AssetStore):
    def __init__(self, id_gen):
        super().__init__(id_gen=id_gen)
        self.paths: list[str] = []

    def _write(self, path, data):
        self.paths.append(os.path.abspath(path))
        raise RuntimeError("stop-before-write")


def test_g1_untrusted_stage_id_stays_in_job_root(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    tracker = TrackingStore(id_gen=lambda: "../../../../escaped-stage")
    try:
        tracker.freeze(str(job), [SourceRef("s", "a", sha(b"A"))], DictReader({"a": b"A"}))
    except RuntimeError:
        pass
    assert tracker.paths
    for p in tracker.paths:
        assert contained_under(str(job), p)
        assert os.path.commonpath([os.path.abspath(job), p]) == os.path.abspath(job)
    assert not (tmp_path / "escaped-stage").exists()


def test_g1_trace_not_used_as_dirname(tmp_path: Path):
    job = tmp_path / "job2"
    out = AssetStore(id_gen=lambda: "not-a-path-token").freeze(
        str(job), [SourceRef("s", "a", sha(b"A"))], DictReader({"a": b"A"})
    )
    assert out["status"] == "ok"
    assert not any(p.name.startswith(".stage-not-a-path-token") for p in job.iterdir())


def test_g2_provenance_locator_and_size_bound(tmp_path: Path):
    job = tmp_path / "prov"
    store = AssetStore()
    assert store.freeze(str(job), [SourceRef("s", "a", sha(b"A"))], DictReader({"a": b"A"}))["status"] == "ok"
    prov = job / "provenance" / "s.json"
    body = json.loads(prov.read_text(encoding="utf-8"))
    body["locator"] = "different"
    body["size"] = 999
    prov.write_text(json.dumps(body), encoding="utf-8")
    assert store.verify_manifest(str(job)) is False


def test_g2_provenance_extra_field_rejected(tmp_path: Path):
    job = tmp_path / "extra"
    store = AssetStore()
    store.freeze(str(job), [SourceRef("s", "a", sha(b"A"))], DictReader({"a": b"A"}))
    prov = job / "provenance" / "s.json"
    body = json.loads(prov.read_text(encoding="utf-8"))
    body["extra"] = "nope"
    prov.write_text(json.dumps(body), encoding="utf-8")
    assert store.verify_manifest(str(job)) is False
