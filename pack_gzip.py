#!/usr/bin/env python3
"""Pack M1–M5 as .tar.gz using the stdlib gzip module (not the gzip CLI)."""

from __future__ import annotations

import gzip
import json
import os
import stat
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from pack import (
    PREFIX,
    ROOT,
    collect,
    sha256_file,
    write_manifest,
)

MTIME = 1757487000  # 2026-09-10 06:10:00 UTC
GZIP_NAME = f"{PREFIX}.tar.gz"


def tarinfo_for(path: Path, arcname: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name=arcname)
    info.size = path.stat().st_size
    info.mtime = MTIME
    info.mode = 0o755 if (path.stat().st_mode & stat.S_IXUSR) else 0o644
    info.type = tarfile.REGTYPE
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def pack_gzip(dest: Path) -> dict:
    files = collect()
    write_manifest(files)
    all_files = collect() + [ROOT / "MANIFEST.json", ROOT / "SHA256SUMS.txt"]
    all_files.sort(key=lambda p: p.relative_to(ROOT).as_posix())

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()

    with tmp.open("wb") as raw:
        with gzip.GzipFile(
            filename=GZIP_NAME,
            mode="wb",
            fileobj=raw,
            compresslevel=9,
            mtime=0,
        ) as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for path in all_files:
                    rel = path.relative_to(ROOT).as_posix()
                    arcname = f"{PREFIX}/{rel}"
                    info = tarinfo_for(path, arcname)
                    with path.open("rb") as fh:
                        tar.addfile(info, fh)

    tmp.replace(dest)
    digest = sha256_file(dest)
    sidecar = dest.with_name(dest.name + ".sha256")
    sidecar.write_text(f"{digest}  {dest.name}\n", encoding="utf-8")
    return {
        "path": str(dest),
        "bytes": dest.stat().st_size,
        "files": len(all_files),
        "sha256": digest,
        "packed_at": datetime.now(timezone.utc).isoformat(),
        "engine": "python gzip.GzipFile + tarfile (compresslevel=9, mtime=0)",
    }


def main() -> None:
    dest = Path(
        os.environ.get(
            "PACK_GZIP_DEST",
            "/workspace/public/pipeline-lab-contractor-m1-m5.tar.gz",
        )
    )
    result = pack_gzip(dest)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
