"""Shared crash-safe filesystem primitives (used by adopt, bootstrap, …)."""

import os
import stat
import tempfile
from pathlib import Path


def fsync_dir(dir_path: Path) -> None:
    fd = os.open(dir_path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_all(fd: int, data: bytes) -> None:
    """os.write may short-write; loop until every byte is down."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def mode_of(path: Path, default: int = 0o644) -> int:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return default


def fsynced_temp(dir_path: Path, name_hint: str, data: bytes, mode: int) -> Path:
    """Unique same-dir temp file, fully written + fsync'd + mode set.

    Caller owns cleanup (or it happens here on exception). Unique names mean a
    crashed previous attempt can never collide with—or be mistaken for—this one.
    """
    fd, tmp_name = tempfile.mkstemp(dir=dir_path, prefix=f".{name_hint}.", suffix=".qd-tmp")
    tmp = Path(tmp_name)
    try:
        write_all(fd, data)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        tmp.unlink(missing_ok=True)
        raise
    os.close(fd)
    os.chmod(tmp, mode)
    return tmp


def atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    """Unique temp + write-all + fsync + os.replace + dir fsync; preserves file mode."""
    final_mode = mode if mode is not None else mode_of(path)
    tmp = fsynced_temp(path.parent, path.name, data, final_mode)
    try:
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    fsync_dir(path.parent)


def publish_no_clobber(path: Path, data: bytes, mode: int) -> bool:
    """Atomically publish a file only if absent (os.link no-clobber). True if published."""
    if path.exists():
        return False
    tmp = fsynced_temp(path.parent, path.name, data, mode)
    try:
        os.link(tmp, path)
        return True
    except FileExistsError:
        return False
    finally:
        tmp.unlink(missing_ok=True)
        fsync_dir(path.parent)
