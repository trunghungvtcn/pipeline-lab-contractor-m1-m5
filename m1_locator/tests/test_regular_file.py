from __future__ import annotations

import os
import stat
from pathlib import Path

from grok_locator import LocatorProfile, LocatorResolver


def posix_profile() -> LocatorProfile:
    return LocatorProfile(
        dialect="posix",
        root_id="demo-root",
        case_policy="sensitive",
        unicode_policy="nfc_only",
    )


def test_rejects_directory(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    out = LocatorResolver().resolve(str(tmp_path), "docs", posix_profile())
    assert out["status"] == "error"
    assert out["reason_code"] == "LOCATOR_REJECTED"


def test_rejects_fifo_when_available(tmp_path: Path):
    if not hasattr(os, "mkfifo"):
        return
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    assert stat.S_ISFIFO(os.stat(fifo).st_mode)
    out = LocatorResolver().resolve(str(tmp_path), "pipe", posix_profile())
    assert out["status"] == "error"
    assert out["reason_code"] == "LOCATOR_REJECTED"
