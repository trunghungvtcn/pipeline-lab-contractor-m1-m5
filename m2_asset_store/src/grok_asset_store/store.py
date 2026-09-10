"""Content-addressed asset store. Opaque source ids, verified CAS, atomic publish."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .canon import dumps_canonical, envelope, loads_strict

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Opaque, collision-free on-disk key. Not a path.
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STAGE_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")
PROVENANCE_KEYS = ("blob", "locator", "size", "source_id")


class Reader(Protocol):
    def read(self, locator: str) -> bytes: ...


class Crash(Exception):
    pass


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    locator: str
    expected_sha256: str


class DictReader:
    def __init__(self, mapping: dict[str, bytes]):
        self.mapping = mapping

    def read(self, locator: str) -> bytes:
        if locator not in self.mapping:
            raise KeyError(locator)
        return self.mapping[locator]


def _reject_locator(locator: str) -> None:
    if not locator or not isinstance(locator, str):
        raise ValueError("locator")
    if "\\" in locator or locator.startswith("/") or locator.startswith("~"):
        raise ValueError("locator")
    if re.match(r"^[a-zA-Z]:", locator) or locator.startswith(("\\\\", "//")):
        raise ValueError("locator")
    parts = locator.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise ValueError("locator")
    if any("\x00" in p for p in parts):
        raise ValueError("locator")


def _reject_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not SOURCE_ID_RE.match(source_id):
        raise ValueError("source_id")


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _fsync_dir(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def contained_under(root: str, path: str) -> bool:
    """True iff path is inside root after realpath. Unresolved last component allowed."""
    root_r = os.path.realpath(os.path.abspath(root))
    abs_path = os.path.abspath(path)
    parent, name = os.path.split(abs_path)
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        return False
    parent_r = os.path.realpath(parent) if os.path.isdir(parent) else os.path.abspath(parent)
    candidate = os.path.join(parent_r, name)
    try:
        return os.path.commonpath([root_r, candidate]) == root_r
    except ValueError:
        return False


class AssetStore:
    def __init__(
        self,
        *,
        clock: Callable[[], int] | None = None,
        id_gen: Callable[[], str] | None = None,
        crash_after_writes: int | None = None,
    ) -> None:
        from .canon import SystemClock, UuidGen

        self._clock = clock or (lambda: SystemClock().now_ns())
        self._id = id_gen or (lambda: UuidGen().new_id())
        self._crash_after = crash_after_writes
        self._writes = 0

    def _write(self, path: str, data: bytes) -> None:
        self._writes += 1
        if self._crash_after is not None and self._writes >= self._crash_after:
            raise Crash(f"injected crash at write {self._writes}")
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        if parent:
            _fsync_dir(parent)

    def _exclusive_stage(self, job_root: str) -> str:
        """Allocate a directory under job_root. Never uses id_gen/trace as a path."""
        job_root = os.path.abspath(job_root)
        os.makedirs(job_root, exist_ok=True)
        for _ in range(16):
            token = hashlib.sha256(os.urandom(32)).hexdigest()
            if not STAGE_TOKEN_RE.fullmatch(token):
                continue
            stage = os.path.join(job_root, f".stage-{token}")
            if not contained_under(job_root, stage):
                raise OSError("stage-escape")
            try:
                os.mkdir(stage)
            except FileExistsError:
                continue
            if not contained_under(job_root, os.path.realpath(stage)):
                os.rmdir(stage)
                raise OSError("stage-escape")
            return stage
        raise OSError("stage-alloc")

    def _safe_rmtree(self, job_root: str, path: str | None) -> None:
        if not path:
            return
        if not contained_under(job_root, path):
            return
        real = os.path.realpath(path)
        if not contained_under(job_root, real):
            return
        shutil.rmtree(real, ignore_errors=True)

    def freeze(self, job_root: str, sources: list[SourceRef], reader: Reader) -> dict[str, Any]:
        trace = self._id()
        stage: str | None = None
        job_root = os.path.abspath(job_root)
        try:
            if not sources:
                return envelope(status="error", reason_code="EMPTY_SOURCES", trace_id=trace)
            seen_ids: set[str] = set()
            for s in sources:
                try:
                    _reject_source_id(s.source_id)
                    _reject_locator(s.locator)
                except ValueError:
                    return envelope(status="error", reason_code="LOCATOR_REJECTED", trace_id=trace)
                if s.source_id in seen_ids:
                    return envelope(status="error", reason_code="DUPLICATE_SOURCE_ID", trace_id=trace)
                seen_ids.add(s.source_id)
                if not isinstance(s.expected_sha256, str) or not SHA256_RE.match(s.expected_sha256.lower()):
                    return envelope(status="error", reason_code="INVALID_SOURCE", trace_id=trace)

            os.makedirs(job_root, exist_ok=True)
            try:
                stage = self._exclusive_stage(job_root)
            except FileExistsError:
                return envelope(status="error", reason_code="STAGE_EXISTS", trace_id=trace)

            entries: list[dict[str, Any]] = []
            blobs: dict[str, int] = {}

            for src in sources:
                data = reader.read(src.locator)
                digest = hashlib.sha256(data).hexdigest()
                if digest != src.expected_sha256.lower():
                    self._safe_rmtree(job_root, stage)
                    return envelope(status="error", reason_code="HASH_MISMATCH", trace_id=trace)
                blob_path = os.path.join(stage, "cas", digest[:2], digest)
                if not contained_under(stage, blob_path):
                    self._safe_rmtree(job_root, stage)
                    return envelope(status="error", reason_code="IO_ERROR", trace_id=trace)
                if digest not in blobs:
                    existing = os.path.join(job_root, "cas", digest[:2], digest)
                    if os.path.isfile(existing):
                        prev = _read_bytes(existing)
                        if hashlib.sha256(prev).hexdigest() != digest or len(prev) != len(data):
                            self._safe_rmtree(job_root, stage)
                            return envelope(status="error", reason_code="CORRUPT_CAS", trace_id=trace)
                    else:
                        self._write(blob_path, data)
                    blobs[digest] = len(data)
                prov = {
                    "blob": digest,
                    "locator": src.locator,
                    "size": len(data),
                    "source_id": src.source_id,
                }
                prov_path = os.path.join(stage, "provenance", f"{src.source_id}.json")
                if not contained_under(stage, prov_path):
                    self._safe_rmtree(job_root, stage)
                    return envelope(status="error", reason_code="IO_ERROR", trace_id=trace)
                self._write(prov_path, dumps_canonical(prov))
                entries.append(
                    {
                        "blob": digest,
                        "locator": src.locator,
                        "sha256": digest,
                        "size": len(data),
                        "source_id": src.source_id,
                    }
                )

            payload = {
                "blobs": [{"sha256": k, "size": blobs[k]} for k in sorted(blobs)],
                "schema_version": 1,
                "sources": sorted(entries, key=lambda e: e["source_id"]),
            }
            payload_sha = hashlib.sha256(dumps_canonical(payload)).hexdigest()

            published = os.path.join(job_root, "MANIFEST.json")
            if os.path.isfile(published):
                existing_ok = self.verify_manifest(job_root)
                if not existing_ok:
                    self._safe_rmtree(job_root, stage)
                    return envelope(status="error", reason_code="CORRUPT_CAS", trace_id=trace)
                current = loads_strict(_read_bytes(published))
                if current.get("payload_sha256") == payload_sha:
                    self._safe_rmtree(job_root, stage)
                    return envelope(
                        status="ok",
                        reason_code="IDEMPOTENT_HIT",
                        trace_id=trace,
                        extra={
                            "blob_count": len(current["blobs"]),
                            "job_root": job_root,
                            "manifest_file_sha256": hashlib.sha256(_read_bytes(published)).hexdigest(),
                            "manifest_sha256": payload_sha,
                            "payload_sha256": payload_sha,
                            "sources": current["sources"],
                        },
                    )
                self._safe_rmtree(job_root, stage)
                return envelope(status="error", reason_code="ALREADY_PUBLISHED", trace_id=trace)

            on_disk = dict(payload)
            on_disk["payload_sha256"] = payload_sha
            raw = dumps_canonical(on_disk)
            manifest_file_sha = hashlib.sha256(raw).hexdigest()
            self._write(os.path.join(stage, "MANIFEST.json"), raw)

            final_cas = os.path.join(job_root, "cas")
            os.makedirs(final_cas, exist_ok=True)
            for digest, size in blobs.items():
                dst_blob = os.path.join(final_cas, digest[:2], digest)
                src_blob = os.path.join(stage, "cas", digest[:2], digest)
                if os.path.isfile(dst_blob):
                    prev = _read_bytes(dst_blob)
                    if hashlib.sha256(prev).hexdigest() != digest or len(prev) != size:
                        self._safe_rmtree(job_root, stage)
                        return envelope(status="error", reason_code="CORRUPT_CAS", trace_id=trace)
                elif os.path.isfile(src_blob):
                    os.makedirs(os.path.dirname(dst_blob), exist_ok=True)
                    os.replace(src_blob, dst_blob)
                    _fsync_dir(os.path.dirname(dst_blob))
                    wrote = _read_bytes(dst_blob)
                    if hashlib.sha256(wrote).hexdigest() != digest:
                        return envelope(status="error", reason_code="CORRUPT_CAS", trace_id=trace)

            new_prov = os.path.join(job_root, f".provenance-{payload_sha}")
            if not contained_under(job_root, new_prov):
                self._safe_rmtree(job_root, stage)
                return envelope(status="error", reason_code="IO_ERROR", trace_id=trace)
            if os.path.exists(new_prov):
                self._safe_rmtree(job_root, new_prov)
            os.rename(os.path.join(stage, "provenance"), new_prov)
            final_prov = os.path.join(job_root, "provenance")
            if os.path.isdir(final_prov):
                shutil.rmtree(final_prov)
            os.replace(new_prov, final_prov)
            _fsync_dir(job_root)
            os.replace(os.path.join(stage, "MANIFEST.json"), published)
            _fsync_dir(job_root)
            self._safe_rmtree(job_root, stage)

            if not self.verify_manifest(job_root):
                return envelope(status="error", reason_code="VERIFY_FAILED", trace_id=trace)

            return envelope(
                status="ok",
                reason_code="OK",
                trace_id=trace,
                extra={
                    "blob_count": len(blobs),
                    "job_root": job_root,
                    "manifest_file_sha256": manifest_file_sha,
                    "manifest_sha256": payload_sha,
                    "payload_sha256": payload_sha,
                    "sources": entries,
                },
            )
        except Crash:
            self._safe_rmtree(job_root, stage)
            return envelope(status="error", reason_code="CRASH_INJECTED", trace_id=trace)
        except KeyError:
            self._safe_rmtree(job_root, stage)
            return envelope(status="error", reason_code="LOCATOR_REJECTED", trace_id=trace)
        except OSError:
            self._safe_rmtree(job_root, stage)
            return envelope(status="error", reason_code="IO_ERROR", trace_id=trace)

    @staticmethod
    def is_published(job_root: str) -> bool:
        return os.path.isfile(os.path.join(job_root, "MANIFEST.json"))

    @staticmethod
    def verify_manifest(job_root: str) -> bool:
        try:
            path = os.path.join(job_root, "MANIFEST.json")
            if not os.path.isfile(path):
                return False
            raw = _read_bytes(path)
            man = loads_strict(raw)
            if not isinstance(man, dict):
                return False
            if man.get("schema_version") != 1:
                return False
            blobs = man.get("blobs")
            sources = man.get("sources")
            payload_sha = man.get("payload_sha256")
            extra_top = set(man.keys()) - {"blobs", "schema_version", "sources", "payload_sha256"}
            if extra_top:
                return False
            if not isinstance(blobs, list) or not isinstance(sources, list):
                return False
            if not isinstance(payload_sha, str) or not SHA256_RE.match(payload_sha):
                return False
            identity = {
                "blobs": blobs,
                "schema_version": 1,
                "sources": sources,
            }
            if hashlib.sha256(dumps_canonical(identity)).hexdigest() != payload_sha:
                return False
            seen_ids: set[str] = set()
            seen_digests: set[str] = set()
            for blob in blobs:
                if not isinstance(blob, dict):
                    return False
                if set(blob.keys()) != {"sha256", "size"}:
                    return False
                digest = blob.get("sha256")
                size = blob.get("size")
                if not isinstance(digest, str) or not SHA256_RE.match(digest):
                    return False
                if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                    return False
                if digest in seen_digests:
                    return False
                seen_digests.add(digest)
                p = os.path.join(job_root, "cas", digest[:2], digest)
                if not os.path.isfile(p):
                    return False
                data = _read_bytes(p)
                if hashlib.sha256(data).hexdigest() != digest or len(data) != size:
                    return False
            for src in sources:
                if not isinstance(src, dict):
                    return False
                if set(src.keys()) != {"blob", "locator", "sha256", "size", "source_id"}:
                    return False
                sid = src.get("source_id")
                loc = src.get("locator")
                digest = src.get("sha256")
                blob = src.get("blob")
                size = src.get("size")
                if not isinstance(sid, str) or not SOURCE_ID_RE.match(sid):
                    return False
                if sid in seen_ids:
                    return False
                seen_ids.add(sid)
                try:
                    _reject_locator(str(loc))
                except ValueError:
                    return False
                if blob != digest or not isinstance(digest, str) or digest not in seen_digests:
                    return False
                blob_size = next(b["size"] for b in blobs if b["sha256"] == digest)
                if size != blob_size:
                    return False
                prov_path = os.path.join(job_root, "provenance", f"{sid}.json")
                if not os.path.isfile(prov_path):
                    return False
                prov = loads_strict(_read_bytes(prov_path))
                if not isinstance(prov, dict) or tuple(sorted(prov.keys())) != tuple(sorted(PROVENANCE_KEYS)):
                    return False
                expected = {
                    "blob": digest,
                    "locator": loc,
                    "size": size,
                    "source_id": sid,
                }
                if dumps_canonical(prov) != dumps_canonical(expected):
                    return False
            return True
        except Exception:
            return False
