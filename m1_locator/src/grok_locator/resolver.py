"""Safe multi-dialect locator resolver. Containment via openat+O_NOFOLLOW."""
from __future__ import annotations

import errno
import hashlib
import os
import re
import stat
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Literal

from .canon import envelope

Dialect = Literal["posix", "windows"]
CasePolicy = Literal["sensitive", "insensitive_reject"]
UnicodePolicy = Literal["nfc_only", "reject_non_nfc"]

WIN_DEVICES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LocatorError(Exception):
    def __init__(self, reason_code: str, message: str = ""):
        super().__init__(message or reason_code)
        self.reason_code = reason_code
        self.message = message or reason_code


@dataclass(frozen=True)
class LocatorProfile:
    dialect: Dialect
    root_id: str
    case_policy: CasePolicy
    unicode_policy: UnicodePolicy
    max_depth: int = 16
    max_nodes: int = 256


class DefaultFS:
    """Injectable filesystem. Every component is opened with O_NOFOLLOW when available."""

    def __init__(self) -> None:
        self.read_count = 0
        self.open_count = 0

    def abspath(self, p: str) -> str:
        return os.path.abspath(p)

    def isdir(self, p: str) -> bool:
        return os.path.isdir(p)

    def has_nofollow(self) -> bool:
        return hasattr(os, "O_NOFOLLOW") and hasattr(os, "open")

    def openat(self, name: str, *, dir_fd: int | None, directory: bool) -> int:
        if not self.has_nofollow():
            raise LocatorError("LOCATOR_REJECTED", "containment-primitive-unavailable")
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if directory and hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        self.open_count += 1
        try:
            if dir_fd is None:
                return os.open(name, flags)
            return os.open(name, flags, dir_fd=dir_fd)
        except OSError as exc:
            if exc.errno in {errno.ELOOP, getattr(errno, "EMLINK", errno.ELOOP)}:
                raise LocatorError("SYMLINK_ESCAPE", "symlink-component") from exc
            if exc.errno == errno.ENOENT:
                raise LocatorError("LOCATOR_REJECTED", "not-found") from exc
            raise LocatorError("LOCATOR_REJECTED", f"open:{exc.errno}") from exc

    def listdir_fd(self, fd: int) -> list[str]:
        return os.listdir(fd)

    def lstat_at(self, name: str, dir_fd: int) -> os.stat_result:
        return os.lstat(name, dir_fd=dir_fd)

    def read_fd(self, fd: int) -> bytes:
        self.read_count += 1
        parts: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 64)
            if not chunk:
                break
            parts.append(chunk)
        return b"".join(parts)


def _require_profile(profile: LocatorProfile | None) -> LocatorProfile:
    if profile is None:
        raise LocatorError("INVALID_PROFILE", "profile is required")
    for field in ("dialect", "root_id", "case_policy", "unicode_policy"):
        if getattr(profile, field, None) in (None, ""):
            raise LocatorError("INVALID_PROFILE", f"missing {field}")
    if profile.dialect not in ("posix", "windows"):
        raise LocatorError("INVALID_PROFILE", "bad dialect")
    if profile.case_policy not in ("sensitive", "insensitive_reject"):
        raise LocatorError("INVALID_PROFILE", "bad case_policy")
    if profile.unicode_policy not in ("nfc_only", "reject_non_nfc"):
        raise LocatorError("INVALID_PROFILE", "bad unicode_policy")
    if profile.max_depth < 1 or profile.max_nodes < 1:
        raise LocatorError("INVALID_PROFILE", "caps")
    return profile


def _split_raw(locator: str, dialect: Dialect) -> list[str]:
    """Split on the dialect separator only. No PurePath — it would hide aliases."""
    if dialect == "posix":
        if "\\" in locator:
            raise LocatorError("LOCATOR_REJECTED", "separator-alias")
        if locator.startswith("/"):
            raise LocatorError("LOCATOR_REJECTED", "absolute")
        if locator.startswith("~"):
            raise LocatorError("LOCATOR_REJECTED", "home")
        if ":" in locator:
            raise LocatorError("LOCATOR_REJECTED", "ads")
        parts = locator.split("/")
    else:
        if locator.startswith(("\\\\", "//")):
            raise LocatorError("LOCATOR_REJECTED", "unc")
        if re.match(r"^[a-zA-Z]:", locator):
            raise LocatorError("LOCATOR_REJECTED", "drive")
        if locator.startswith("/") or locator.startswith("\\"):
            raise LocatorError("LOCATOR_REJECTED", "absolute")
        if ":" in locator:
            raise LocatorError("LOCATOR_REJECTED", "ads")
        if "/" in locator:
            raise LocatorError("LOCATOR_REJECTED", "separator-alias")
        parts = locator.split("\\")
    if not parts or any(p == "" for p in parts):
        raise LocatorError("LOCATOR_REJECTED", "empty-or-double-sep")
    return parts


def reject_syntax(locator: str, profile: LocatorProfile) -> list[str]:
    """Reject on the raw locator. Returns dialect-relative components. No I/O."""
    if locator is None or locator == "":
        raise LocatorError("LOCATOR_REJECTED", "empty")
    if not isinstance(locator, str):
        raise LocatorError("LOCATOR_REJECTED", "not-str")
    if CONTROL_RE.search(locator):
        raise LocatorError("LOCATOR_REJECTED", "control")
    if profile.unicode_policy in ("nfc_only", "reject_non_nfc"):
        if unicodedata.normalize("NFC", locator) != locator:
            raise LocatorError("LOCATOR_REJECTED", "non-nfc")
    parts = _split_raw(locator, profile.dialect)
    if len(parts) > profile.max_depth:
        raise LocatorError("LOCATOR_REJECTED", "depth-cap")
    if len(parts) > profile.max_nodes:
        raise LocatorError("LOCATOR_REJECTED", "node-cap")
    nodes = 0
    for part in parts:
        nodes += 1
        if nodes > profile.max_nodes:
            raise LocatorError("LOCATOR_REJECTED", "node-cap")
        if part in (".", ".."):
            raise LocatorError("LOCATOR_REJECTED", "traversal" if part == ".." else "dot-alias")
        stem = part.split(".")[0].upper()
        if stem in WIN_DEVICES:
            raise LocatorError("LOCATOR_REJECTED", "device")
        if part.endswith(" ") or part.endswith("."):
            raise LocatorError("LOCATOR_REJECTED", "ambiguous-alias")
    return parts


def canonical_relative(parts: list[str]) -> str:
    return "/".join(parts)


class LocatorResolver:
    def __init__(
        self,
        *,
        clock: Callable[[], int] | None = None,
        id_gen: Callable[[], str] | None = None,
        fs: DefaultFS | None = None,
    ) -> None:
        from .canon import SystemClock, UuidGen

        self._clock = clock or (lambda: SystemClock().now_ns())
        self._id = id_gen or (lambda: UuidGen().new_id())
        self._fs = fs or DefaultFS()

    def validate(self, locator: str, profile: LocatorProfile | None) -> dict[str, Any]:
        trace = self._id()
        try:
            prof = _require_profile(profile)
            parts = reject_syntax(locator, prof)
            return envelope(
                status="ok",
                reason_code="OK",
                trace_id=trace,
                extra={"relative_posix": canonical_relative(parts), "root_id": prof.root_id},
            )
        except LocatorError as exc:
            return envelope(status="error", reason_code=exc.reason_code, trace_id=trace)

    def resolve(
        self,
        root: str,
        locator: str,
        profile: LocatorProfile | None,
        expected_sha256: str | None = None,
    ) -> dict[str, Any]:
        """Open every component with O_NOFOLLOW from a held directory fd. Never follow aliases."""
        trace = self._id()
        held: list[int] = []
        try:
            prof = _require_profile(profile)
            parts = reject_syntax(locator, prof)
            if expected_sha256 is not None:
                if not isinstance(expected_sha256, str) or not SHA256_RE.match(expected_sha256.lower()):
                    raise LocatorError("HASH_MISMATCH", "bad-expected-hash")
            if not root or not self._fs.isdir(root):
                raise LocatorError("LOCATOR_REJECTED", "root-missing")
            root_abs = self._fs.abspath(root)

            root_fd = self._fs.openat(root_abs, dir_fd=None, directory=True)
            held.append(root_fd)
            cursor = root_fd
            depth = 0
            seen_inodes: set[tuple[int, int]] = set()
            try:
                st_root = os.fstat(root_fd)
                seen_inodes.add((st_root.st_dev, st_root.st_ino))
            except OSError:
                pass

            for i, seg in enumerate(parts):
                depth += 1
                if depth > prof.max_depth or len(seen_inodes) + 1 > prof.max_nodes:
                    raise LocatorError("LOCATOR_REJECTED", "graph-cap")
                if prof.case_policy == "insensitive_reject":
                    try:
                        names = self._fs.listdir_fd(cursor)
                    except OSError:
                        names = []
                    folded = [n for n in names if n.casefold() == seg.casefold()]
                    if folded and seg not in folded:
                        raise LocatorError("LOCATOR_REJECTED", "case-alias")
                    if len(set(folded)) > 1:
                        raise LocatorError("LOCATOR_REJECTED", "case-alias")
                last = i == len(parts) - 1
                try:
                    st = self._fs.lstat_at(seg, cursor)
                except OSError as exc:
                    if exc.errno == errno.ENOENT:
                        raise LocatorError("LOCATOR_REJECTED", "not-found") from exc
                    raise LocatorError("LOCATOR_REJECTED", "lstat") from exc
                if stat.S_ISLNK(st.st_mode):
                    raise LocatorError("SYMLINK_ESCAPE", "symlink-component")
                ident = (st.st_dev, st.st_ino)
                if ident in seen_inodes:
                    raise LocatorError("LOCATOR_REJECTED", "graph-cycle")
                seen_inodes.add(ident)
                nxt = self._fs.openat(seg, dir_fd=cursor, directory=not last and stat.S_ISDIR(st.st_mode))
                held.append(nxt)
                cursor = nxt

            data = self._fs.read_fd(cursor)
            digest = hashlib.sha256(data).hexdigest()
            if expected_sha256 is not None and digest != expected_sha256.lower():
                raise LocatorError("HASH_MISMATCH", "expected-hash")
            return envelope(
                status="ok",
                reason_code="OK",
                trace_id=trace,
                extra={
                    "relative_posix": canonical_relative(parts),
                    "root_id": prof.root_id,
                    "sha256": digest,
                    "size": len(data),
                    "reads": self._fs.read_count,
                },
            )
        except LocatorError as exc:
            return envelope(status="error", reason_code=exc.reason_code, trace_id=trace)
        except OSError:
            return envelope(status="error", reason_code="LOCATOR_REJECTED", trace_id=trace)
        finally:
            for fd in reversed(held):
                try:
                    os.close(fd)
                except OSError:
                    pass
