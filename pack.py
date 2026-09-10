#!/usr/bin/env python3
"""Pack M1–M5 into a DEFLATE ZIP using the stdlib zipfile module only."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent
STAMP = datetime(2026, 9, 10, 6, 10, 0)
PREFIX = "pipeline-lab-contractor-m1-m5"
SKIP_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    "private",
    "artifacts",
    "node_modules",
}
SKIP_FILE_SUFFIXES = {".pyc", ".pyo"}
SKIP_FILE_NAMES = {".DS_Store"}


def skip_path(path: Path) -> bool:
    if path.name in SKIP_FILE_NAMES or path.suffix in SKIP_FILE_SUFFIXES:
        return True
    return any(part in SKIP_DIR_NAMES for part in path.relative_to(ROOT).parts)


def collect() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or skip_path(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel in {"MANIFEST.json", "SHA256SUMS.txt"}:
            continue
        files.append(path)
    files.sort(key=lambda p: p.relative_to(ROOT).as_posix())
    return files


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(files: list[Path]) -> None:
    entries = []
    sums: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        digest = sha256_file(path)
        size = path.stat().st_size
        entries.append({"path": rel, "bytes": size, "sha256": digest})
        sums.append(f"{digest}  {rel}")
    payload = {
        "name": PREFIX,
        "packed_at": "2026-09-10T06:10:00Z",
        "packer": "python3 zipfile.ZIP_DEFLATED",
        "python": "stdlib zipfile (no zip CLI)",
        "files": len(entries),
        "excluded": sorted(SKIP_DIR_NAMES | SKIP_FILE_NAMES | SKIP_FILE_SUFFIXES),
        "entries": entries,
    }
    (ROOT / "MANIFEST.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ROOT / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")


def zipinfo_for(arcname: str, data: bytes, mode: int) -> ZipInfo:
    info = ZipInfo(filename=arcname, date_time=STAMP.timetuple()[:6])
    info.compress_type = ZIP_DEFLATED
    info.external_attr = (mode & 0o777) << 16
    info.create_system = 3
    info.file_size = len(data)
    return info


def pack_zip(dest: Path) -> dict:
    files = collect()
    write_manifest(files)
    all_files = collect() + [ROOT / "MANIFEST.json", ROOT / "SHA256SUMS.txt"]
    all_files.sort(key=lambda p: p.relative_to(ROOT).as_posix())

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".zip.tmp")
    if tmp.exists():
        tmp.unlink()

    with ZipFile(tmp, "w", compression=ZIP_DEFLATED, compresslevel=9) as zf:
        for path in all_files:
            rel = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            mode = path.stat().st_mode
            unix = 0o755 if (mode & stat.S_IXUSR) else 0o644
            info = zipinfo_for(f"{PREFIX}/{rel}", data, unix)
            zf.writestr(info, data)

    tmp.replace(dest)
    digest = sha256_file(dest)
    sidecar = dest.with_suffix(".sha256")
    sidecar.write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
    return {
        "path": str(dest),
        "bytes": dest.stat().st_size,
        "files": len(all_files),
        "sha256": digest,
        "packed_at": datetime.now(timezone.utc).isoformat(),
        "engine": "python zipfile.ZIP_DEFLATED",
    }


def main() -> None:
    dest = Path(os.environ.get("PACK_DEST", "/workspace/public/pipeline-lab-contractor-m1-m5.zip"))
    result = pack_zip(dest)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
