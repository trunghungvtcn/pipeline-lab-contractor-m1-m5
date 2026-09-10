#!/usr/bin/env python3
"""Compare release archives against a clean git checkout. Stdlib only."""
from __future__ import annotations

import gzip
import hashlib
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

PREFIX = "pipeline-lab-contractor-m1-m5/"
EXCLUDED = {
    "MANIFEST.json",
    "REPORT.json",
    "REPORT.md",
    "junit.xml",
    "SHA256SUMS.txt",
    "SBOM.json",
}


def blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def safe_name(name: str) -> str:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        raise RuntimeError(f"unsafe archive member: {name}")
    return name[len(PREFIX) :] if name.startswith(PREFIX) else name


def git_tree(root: Path) -> dict[str, str]:
    tree: dict[str, str] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if not path.is_file() or rel.startswith(".git/") or path.name in EXCLUDED:
            continue
        tree[rel] = blob(path.read_bytes())
    return tree


def compare(got: dict[str, str], tree: dict[str, str]) -> dict[str, object]:
    common = set(got) & set(tree)
    return {
        "archive_files": len(got),
        "git_files": len(tree),
        "common": len(common),
        "content_differences": sorted(k for k in common if got[k] != tree[k]),
        "missing_from_archive": sorted(set(tree) - set(got)),
        "extra_in_archive": sorted(set(got) - set(tree)),
    }


def verify_tar(path: Path, tree: dict[str, str]) -> dict[str, object]:
    got: dict[str, str] = {}
    with path.open("rb") as fh, gzip.GzipFile(fileobj=fh) as gz, tarfile.open(fileobj=gz, mode="r|") as tf:
        for member in tf:
            name = safe_name(member.name)
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError(f"unsafe archive member: {member.name}")
            if not member.isfile():
                continue
            stream = tf.extractfile(member)
            if stream is None:
                raise RuntimeError(f"unreadable archive member: {member.name}")
            if PurePosixPath(name).name not in EXCLUDED:
                got[name] = blob(stream.read())
    return compare(got, tree)


def verify_zip(path: Path, tree: dict[str, str]) -> dict[str, object]:
    got: dict[str, str] = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = safe_name(info.filename)
            if info.is_dir():
                continue
            if PurePosixPath(name).name not in EXCLUDED:
                got[name] = blob(zf.read(info))
    return compare(got, tree)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    tree = git_tree(root)
    gzip_path = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "pipeline-lab-contractor-m1-m5.tar.gz"
    zip_path = Path(sys.argv[3]) if len(sys.argv) > 3 else root / "pipeline-lab-contractor-m1-m5.zip"
    print("tar", verify_tar(gzip_path, tree))
    print("zip", verify_zip(zip_path, tree))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
