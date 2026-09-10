from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from grok_locator import DefaultFS, LocatorProfile, LocatorResolver, dumps_canonical, loads_strict


def posix_profile(**kw) -> LocatorProfile:
    return LocatorProfile(
        dialect="posix",
        root_id="demo-root",
        case_policy="sensitive",
        unicode_policy="nfc_only",
        **kw,
    )


def win_profile() -> LocatorProfile:
    return LocatorProfile(
        dialect="windows",
        root_id="demo-root",
        case_policy="sensitive",
        unicode_policy="nfc_only",
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "manual.txt").write_bytes(b"Synthetic lifting manual revision A.")
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "same.txt").write_bytes(b"A")
    (tmp_path / "b" / "same.txt").write_bytes(b"B")
    return tmp_path


def test_posix_and_windows_same_bytes(root: Path):
    r = LocatorResolver()
    a = r.resolve(str(root), "docs/manual.txt", posix_profile())
    b = r.resolve(str(root), "docs\\manual.txt", win_profile())
    assert a["status"] == "ok" and b["status"] == "ok"
    assert a["sha256"] == b["sha256"]
    assert a["size"] == len(b"Synthetic lifting manual revision A.")


def test_same_basename_different_bytes(root: Path):
    r = LocatorResolver()
    a = r.resolve(str(root), "a/same.txt", posix_profile())
    b = r.resolve(str(root), "b/same.txt", posix_profile())
    assert a["sha256"] != b["sha256"]


def test_missing_profile_rejected(root: Path):
    r = LocatorResolver()
    out = r.resolve(str(root), "docs/manual.txt", None)
    assert out["status"] == "error"
    assert out["reason_code"] == "INVALID_PROFILE"


def test_rejects_before_read(root: Path):
    r = LocatorResolver()
    cases = [
        ("/etc/passwd", "LOCATOR_REJECTED"),
        ("../docs/manual.txt", "LOCATOR_REJECTED"),
        ("docs/../../etc/passwd", "LOCATOR_REJECTED"),
        ("C:\\windows\\x", "LOCATOR_REJECTED"),
        ("\\\\unc\\share", "LOCATOR_REJECTED"),
        ("CON", "LOCATOR_REJECTED"),
        ("docs/NUL.txt", "LOCATOR_REJECTED"),
        ("file:stream", "LOCATOR_REJECTED"),
        ("docs/\x00x", "LOCATOR_REJECTED"),
        ("docs\\manual.txt", "LOCATOR_REJECTED"),
    ]
    for loc, code in cases:
        out = r.resolve(str(root), loc, posix_profile())
        assert out["status"] == "error", loc
        assert out["reason_code"] == code, loc


def test_symlink_escape(root: Path):
    outside = root.parent / "outside.txt"
    outside.write_bytes(b"secret")
    link = root / "docs" / "escape"
    os.symlink(outside, link)
    r = LocatorResolver()
    out = r.resolve(str(root), "docs/escape", posix_profile())
    assert out["status"] == "error"
    assert out["reason_code"] == "SYMLINK_ESCAPE"


def test_symlink_cycle_finite(root: Path):
    a = root / "loop-a"
    b = root / "loop-b"
    os.symlink(b, a)
    os.symlink(a, b)
    r = LocatorResolver()
    out = r.resolve(str(root), "loop-a", posix_profile())
    assert out["status"] == "error"
    assert out["reason_code"] in {"SYMLINK_ESCAPE", "LOCATOR_REJECTED"}


def test_depth_cap(root: Path):
    r = LocatorResolver()
    loc = "/".join(["d"] * 20) + "/f.txt"
    out = r.resolve(str(root), loc, posix_profile(max_depth=8))
    assert out["reason_code"] == "LOCATOR_REJECTED"


def test_non_nfc_rejected(root: Path):
    r = LocatorResolver()
    loc = "docs/cafe\u0301.txt"
    out = r.resolve(str(root), loc, posix_profile())
    assert out["status"] == "error"


def test_case_alias_rejected(root: Path):
    r = LocatorResolver()
    prof = LocatorProfile(
        dialect="posix",
        root_id="demo-root",
        case_policy="insensitive_reject",
        unicode_policy="nfc_only",
    )
    out = r.resolve(str(root), "Docs/manual.txt", prof)
    assert out["status"] == "error"
    assert out["reason_code"] == "LOCATOR_REJECTED"


def test_canonical_json_sorted_compact():
    payload = {"b": 1, "a": 2}
    raw = dumps_canonical(payload)
    assert raw == b'{"a":2,"b":1}'
    assert loads_strict(raw)["a"] == 2


def test_duplicate_json_key_rejected():
    with pytest.raises(Exception):
        loads_strict('{"a":1,"a":2}')


def test_loads_strict_rejects_nonfinite():
    with pytest.raises(Exception):
        loads_strict('{"x":NaN}')
    with pytest.raises(Exception):
        loads_strict('{"x":Infinity}')
    with pytest.raises(Exception):
        loads_strict('{"x":-Infinity}')
    nested = loads_strict('{"a":{"b":1}}')
    assert nested["a"]["b"] == 1
    with pytest.raises(Exception):
        dumps_canonical({"x": math.nan})


def test_expected_hash_mismatch(root: Path):
    r = LocatorResolver()
    out = r.resolve(str(root), "docs/manual.txt", posix_profile(), expected_sha256="0" * 64)
    assert out["reason_code"] == "HASH_MISMATCH"


def test_dot_and_double_sep_rejected(root: Path):
    r = LocatorResolver()
    for loc in ("docs/./manual.txt", "docs//manual.txt", "./docs/manual.txt"):
        out = r.resolve(str(root), loc, posix_profile())
        assert out["status"] == "error"
        assert out["reason_code"] == "LOCATOR_REJECTED"


def test_no_read_on_rejected_locator(root: Path):
    spy = DefaultFS()
    r = LocatorResolver(fs=spy)
    out = r.resolve(str(root), "../sentinel.txt", posix_profile())
    assert out["reason_code"] == "LOCATOR_REJECTED"
    assert spy.read_count == 0
    assert spy.open_count == 0


def test_validate_does_not_touch_fs(root: Path):
    r = LocatorResolver()
    ok = r.validate("docs/manual.txt", posix_profile())
    bad = r.validate("../x", posix_profile())
    assert ok["status"] == "ok"
    assert bad["reason_code"] == "LOCATOR_REJECTED"
