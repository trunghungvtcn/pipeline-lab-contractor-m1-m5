from __future__ import annotations

import hashlib
from pathlib import Path

from grok_asset_store import AssetStore, DictReader, SourceRef


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_dedupe_same_bytes_two_provenance(tmp_path: Path):
    payload = b"hello-blob"
    digest = sha(payload)
    reader = DictReader({"p/a.txt": payload, "p/b.txt": payload})
    store = AssetStore()
    rec = store.freeze(
        str(tmp_path),
        [
            SourceRef("s1", "p/a.txt", digest),
            SourceRef("s2", "p/b.txt", digest),
        ],
        reader,
    )
    assert rec["status"] == "ok"
    assert rec["blob_count"] == 1
    assert (tmp_path / "provenance" / "s1.json").exists()
    assert (tmp_path / "provenance" / "s2.json").exists()
    assert AssetStore.verify_manifest(str(tmp_path))


def test_same_basename_different_bytes(tmp_path: Path):
    a, b = b"A-bytes", b"B-bytes"
    reader = DictReader({"x/same.txt": a, "y/same.txt": b})
    rec = AssetStore().freeze(
        str(tmp_path),
        [
            SourceRef("s1", "x/same.txt", sha(a)),
            SourceRef("s2", "y/same.txt", sha(b)),
        ],
        reader,
    )
    assert rec["status"] == "ok"
    assert rec["blob_count"] == 2
    hashes = {e["sha256"] for e in rec["sources"]}
    assert hashes == {sha(a), sha(b)}


def test_hash_mismatch(tmp_path: Path):
    reader = DictReader({"p/a.txt": b"abc"})
    rec = AssetStore().freeze(
        str(tmp_path),
        [SourceRef("s1", "p/a.txt", sha(b"zzz"))],
        reader,
    )
    assert rec["reason_code"] == "HASH_MISMATCH"
    assert not AssetStore.is_published(str(tmp_path))


def test_locator_outside_sources_rejected(tmp_path: Path):
    reader = DictReader({"ok.txt": b"1"})
    rec = AssetStore().freeze(
        str(tmp_path),
        [SourceRef("s1", "../etc/passwd", sha(b"1"))],
        reader,
    )
    assert rec["reason_code"] == "LOCATOR_REJECTED"
    assert not AssetStore.is_published(str(tmp_path))


def test_crash_before_manifest(tmp_path: Path):
    payload = b"data"
    reader = DictReader({"p/a.txt": payload})
    rec = AssetStore(crash_after_writes=1).freeze(
        str(tmp_path),
        [SourceRef("s1", "p/a.txt", sha(payload))],
        reader,
    )
    assert rec["reason_code"] == "CRASH_INJECTED"
    assert not AssetStore.is_published(str(tmp_path))


def test_replay_idempotent(tmp_path: Path):
    payload = b"data"
    digest = sha(payload)
    reader = DictReader({"p/a.txt": payload})
    a = AssetStore().freeze(str(tmp_path), [SourceRef("s1", "p/a.txt", digest)], reader)
    b = AssetStore().freeze(str(tmp_path), [SourceRef("s1", "p/a.txt", digest)], reader)
    assert a["status"] == b["status"] == "ok"
    assert AssetStore.verify_manifest(str(tmp_path))
