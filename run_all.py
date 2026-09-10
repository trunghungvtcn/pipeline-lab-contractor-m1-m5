#!/usr/bin/env python3
"""Run M1–M5 offline tests into a fresh run directory. Stdlib + pytest."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
MODULES = [
    ("M1", ROOT / "m1_locator"),
    ("M2", ROOT / "m2_asset_store"),
    ("M3", ROOT / "m3_job_ledger"),
    ("M4", ROOT / "m4_notion_projection"),
    ("M5", ROOT / "m5_integration"),
]
CACHE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", "private"}
CACHE_SUFFIXES = {".pyc", ".pyo"}
ENV_ALLOW = {
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "TMPDIR",
    "TMP",
    "TEMP",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "SYSTEMDRIVE",
    "PROGRAMFILES",
    "PROGRAMDATA",
    "OS",
    "TERM",
    "TZ",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_cache(path: Path, start: Path) -> bool:
    rel = path.relative_to(start)
    if any(part in CACHE_PARTS for part in rel.parts):
        return True
    return path.suffix in CACHE_SUFFIXES


def source_sha(mod_dir: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(mod_dir.rglob("*")):
        if not path.is_file() or is_cache(path, mod_dir):
            continue
        if path.name in {"REPORT.json", "REPORT.md", "SHA256SUMS.txt", "junit.xml", "SBOM.json"}:
            continue
        if path.suffix.lower() not in {".py", ".toml", ".json", ".md", ".xml", ".yml", ".yaml", ".sh", ".txt", ".in"}:
            continue
        h.update(path.relative_to(mod_dir).as_posix().encode())
        h.update(b"\0")
        h.update(path.read_bytes())
    return h.hexdigest()


def parse_junit(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"collected": 0, "passed": 0, "failed": 0, "skipped": 0, "node_ids": []}
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = failures = skipped = errors = 0
    node_ids: list[str] = []
    for s in suites:
        tests += int(s.attrib.get("tests", 0))
        failures += int(s.attrib.get("failures", 0))
        skipped += int(s.attrib.get("skipped", 0))
        errors += int(s.attrib.get("errors", 0))
        for case in s.findall("testcase"):
            name = case.attrib.get("name", "")
            cls = case.attrib.get("classname", "")
            node_ids.append(f"{cls}::{name}" if cls else name)
    failed = failures + errors
    passed = max(0, tests - failed - skipped)
    return {
        "collected": tests,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "node_ids": node_ids,
    }


def whitelist_env(pythonpath: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in ENV_ALLOW}
    env["PYTHONPATH"] = pythonpath
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def run_mod(code: str, mod_dir: Path, run_dir: Path) -> dict:
    extra = [str(mod_dir / "src")]
    if code == "M5":
        extra = [
            str(ROOT / "m5_integration" / "src"),
            str(ROOT / "m1_locator" / "src"),
            str(ROOT / "m2_asset_store" / "src"),
            str(ROOT / "m3_job_ledger" / "src"),
            str(ROOT / "m4_notion_projection" / "src"),
        ]
    env = whitelist_env(os.pathsep.join(extra))
    junit = run_dir / f"{code}-junit.xml"
    log = run_dir / f"{code}.log"
    t0 = time.time()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests",
            "-q",
            f"--junitxml={junit}",
            "-W",
            "error::pytest.PytestUnhandledThreadExceptionWarning",
            "-W",
            "error::pytest.PytestUnraisableExceptionWarning",
            "-W",
            "error::ResourceWarning",
        ],
        cwd=mod_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    log.write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")
    tests = parse_junit(junit)
    tests["exit_code"] = proc.returncode
    tests["duration_s"] = round(time.time() - t0, 3)
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    tail_s = tail[-1] if tail else ""
    failed = int(tests["failed"])
    skipped = int(tests["skipped"])
    verdict = "PASS" if proc.returncode == 0 and failed == 0 and skipped == 0 else "PARTIAL"
    src_sha = source_sha(mod_dir)
    report = {
        "module": code,
        "verdict": verdict,
        "source_sha256": src_sha,
        "tests": {k: tests[k] for k in ("collected", "passed", "failed", "skipped", "exit_code")},
        "node_ids": tests["node_ids"],
        "boundary": {
            "notion_access_mode": "READ_ONLY",
            "notion_reads_performed": False,
            "notion_real_read": "NOT_VERIFIED",
            "real_notion_writes": False,
            "other_thbison_resources_accessed": False,
        },
        "blockers": [] if verdict == "PASS" else [tail_s],
        "python": sys.version.split()[0],
        "stdout_tail": tail_s,
    }
    (mod_dir / "REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (mod_dir / "REPORT.md").write_text(
        f"# {code}\n\n- verdict: `{verdict}`\n- tests: {tests['passed']}/{tests['collected']}\n- python: {sys.version.split()[0]}\n"
    )
    return report


def write_checksums(mod_dir: Path) -> None:
    sums = []
    for path in sorted(mod_dir.rglob("*")):
        if not path.is_file() or is_cache(path, mod_dir):
            continue
        if path.name in {"REPORT.json", "REPORT.md", "SHA256SUMS.txt", "junit.xml", "SBOM.json"}:
            continue
        if path.suffix.lower() in {".py", ".toml", ".json", ".md", ".xml", ".yml", ".yaml", ".sh", ".txt"}:
            sums.append(f"{sha256_file(path)}  {path.relative_to(mod_dir).as_posix()}")
    (mod_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    sbom = {
        "module": mod_dir.name,
        "python_requires": ">=3.12",
        "dependencies": ["pytest==9.1.1"],
    }
    (mod_dir / "SBOM.json").write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n")


def main() -> int:
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8]
    run_dir = ROOT / "artifacts" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for code, path in MODULES:
        reports.append(run_mod(code, path, run_dir))
        write_checksums(path)
    modules_pass = all(r["verdict"] == "PASS" for r in reports)
    skipped = sum(int(r["tests"]["skipped"]) for r in reports)
    failed = sum(int(r["tests"]["failed"]) for r in reports)
    linux_host = sys.platform.startswith("linux")
    docker_verified = os.environ.get("LINUX_DOCKER_VERIFIED") == "1"
    notion_verified = os.environ.get("NOTION_READ_VERIFIED") == "1"
    gates_ok = modules_pass and skipped == 0 and failed == 0 and linux_host and docker_verified and notion_verified
    overall = "CONTRACTOR_PASS" if gates_ok else "CONTRACTOR_PARTIAL"
    out = {
        "verdict": overall,
        "contractor_modules_verdict": "CONTRACTOR_PASS" if modules_pass else "CONTRACTOR_PARTIAL",
        "run_id": run_id,
        "interpreter": sys.version,
        "platform": platform.platform(),
        "modules": reports,
        "boundary": {
            "notion_access_mode": "READ_ONLY",
            "notion_reads_performed": False,
            "notion_real_read": "NOT_VERIFIED",
            "linux_docker": "NOT_VERIFIED",
            "real_notion_writes": False,
            "other_thbison_resources_accessed": False,
        },
        "production_ready": False,
        "merged": False,
        "deployed": False,
        "scheduler_enabled": False,
        "model_training": "NOT_RUN",
    }
    (ROOT / "REPORT.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    (run_dir / "REPORT.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(overall)
    print(f"run_id={run_id}")
    return 0 if overall == "CONTRACTOR_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
