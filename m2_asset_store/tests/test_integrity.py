from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from grok_asset_store import AssetStore, DictReader, SourceRef, dumps_canonical, loads_strict


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_r02_source_id_escape(tmp_path: Path):
    jobroot = tmp_path / "asset-escape"
    jobroot.mkdir()
    out = AssetStore(id_gen=lambda: "fixed").freeze(
        str(jobroot),
        [SourceRef("../../escaped", "ok", sha(b"A"))],
        DictReader({"ok": b"A"}),
    )
    assert out["status"] == "error"
    assert not (jobroot.parent / "escaped.json").exists()
    assert not (tmp_path / "escaped.json").exists()


def test_r03_existing_corrupt_blob(tmp_path: Path):
    jr = tmp_path / "corrupt"
    d = sha(b"A")
    blob = jr / "cas" / d[:2] / d
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"CORRUPT")
    out = AssetStore().freeze(str(jr), [SourceRef("s", "a", d)], DictReader({"a": b"A"}))
    assert out["status"] == "error"
    assert out["reason_code"] == "CORRUPT_CAS"
    assert not AssetStore.verify_manifest(str(jr))


def test_r04_manifest_forgery(tmp_path: Path):
    jr = tmp_path / "manifest"
    d = sha(b"A")
    out = AssetStore().freeze(str(jr), [SourceRef("s", "a", d)], DictReader({"a": b"A"}))
    assert out["status"] == "ok"
    man = json.loads((jr / "MANIFEST.json").read_bytes())
    man["sources"][0]["sha256"] = "0" * 64
    man["sources"][0]["size"] = 999
    man["manifest_sha256"] = "0" * 64
    man["payload_sha256"] = "0" * 64
    (jr / "MANIFEST.json").write_text(json.dumps(man))
    assert AssetStore.verify_manifest(str(jr)) is False


def test_r05_replay_identity(tmp_path: Path):
    jr = tmp_path / "replay"
    d = sha(b"A")
    a = AssetStore().freeze(str(jr), [SourceRef("s", "a", d)], DictReader({"a": b"A"}))
    b = AssetStore().freeze(str(jr), [SourceRef("s", "a", d)], DictReader({"a": b"A"}))
    assert a["manifest_sha256"] == b["manifest_sha256"]
    assert a["status"] == b["status"] == "ok"


def test_duplicate_source_id_rejected(tmp_path: Path):
    d = sha(b"A")
    out = AssetStore().freeze(
        str(tmp_path),
        [SourceRef("s1", "a", d), SourceRef("s1", "b", d)],
        DictReader({"a": b"A", "b": b"A"}),
    )
    assert out["reason_code"] == "DUPLICATE_SOURCE_ID"


def test_backslash_locator_rejected(tmp_path: Path):
    d = sha(b"A")
    out = AssetStore().freeze(
        str(tmp_path),
        [SourceRef("s1", "ok\\a", d)],
        DictReader({"ok\\a": b"A"}),
    )
    assert out["reason_code"] == "LOCATOR_REJECTED"


def test_loads_strict_rejects_nan():
    with pytest.raises(Exception):
        loads_strict('{"x":NaN}')
    assert dumps_canonical({"a": 1}) == b'{"a":1}'
