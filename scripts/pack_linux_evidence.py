#!/usr/bin/env python3
"""Pack JUnit/logs from a run_all.py artifacts directory into a public zip."""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_junit(path: Path) -> dict:
    tree = ET.parse(path)
    ids: list[str] = []
    passed = failed = skipped = 0
    for case in tree.iter("testcase"):
        cls = case.get("classname") or ""
        name = case.get("name") or ""
        ids.append(f"{cls}::{name}" if cls else name)
        if case.find("failure") is not None or case.find("error") is not None:
            failed += 1
        elif case.find("skipped") is not None:
            skipped += 1
        else:
            passed += 1
    return {
        "collected": len(ids),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "node_ids": ids,
        "junit": path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def latest_run(root: Path) -> Path:
    arts = root / "artifacts"
    runs = sorted(p for p in arts.iterdir() if p.is_dir())
    if not runs:
        raise SystemExit("no artifacts run directory")
    return runs[-1]


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("linux-junit.zip")
    run = latest_run(root)
    report = json.loads((run / "REPORT.json").read_text())
    modules = {label: parse_junit(run / f"{label}-junit.xml") for label in ["M1", "M2", "M3", "M4", "M5"]}
    evidence = {
        "candidate_commit": report.get("git_commit") or report.get("source_commit"),
        "python": report.get("python"),
        "platform": report.get("platform"),
        "run_id": report.get("run_id") or run.name,
        "collected": sum(m["collected"] for m in modules.values()),
        "passed": sum(m["passed"] for m in modules.values()),
        "failed": sum(m["failed"] for m in modules.values()),
        "skipped": sum(m["skipped"] for m in modules.values()),
        "modules": modules,
        "notion": "NOTION_TARGET_MISSING",
        "real_notion_writes": False,
    }
    staging = dest.parent / "_linux_evidence_staging"
    staging.mkdir(parents=True, exist_ok=True)
    (staging / "linux-evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    for path in run.iterdir():
        if path.is_file():
            (staging / path.name).write_bytes(path.read_bytes())
    sums = [f"{sha256_file(p)}  {p.name}" for p in sorted(staging.iterdir())]
    (staging / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staging.iterdir()):
            zf.write(path, f"linux-junit/{path.name}")
    print(json.dumps({"path": str(dest), "sha256": sha256_file(dest), "bytes": dest.stat().st_size, "collected": evidence["collected"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
