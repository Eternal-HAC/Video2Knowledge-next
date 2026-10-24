"""Atomic task-manifest merges for a single backend process.

Striped reentrant locks bound memory regardless of history size. A lock covers the
whole read/change/replace operation; callers keep directory and task-ID validation.
This is not a multi-process workspace lock or a replacement for task artifacts.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from . import history_cache

_LOCKS = tuple(threading.RLock() for _ in range(128))


def _check_file(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        or info.st_nlink > 1
    ):
        raise OSError("任务清单不是独立普通文件")


def _load(path: Path) -> dict[str, Any]:
    _check_file(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError) as exc:
        raise OSError("任务清单损坏，已保留原文件") from exc
    if not isinstance(payload, dict):
        raise OSError("任务清单必须是对象，已保留原文件")
    return payload


def read(path: Path) -> dict[str, Any]:
    """Historical browsing tolerates unreadable/corrupt manifests without repair."""
    try:
        return _load(path)
    except OSError:
        return {}


def update(path: Path, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Apply a synchronous mutation to the latest manifest, preserving other keys."""
    lock = _LOCKS[hash(os.path.normcase(os.path.abspath(path))) % len(_LOCKS)]
    with lock:
        payload = _load(path)
        change(payload)
        # Serialize before creating the temporary file so invalid values leave no debris.
        encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=".task-", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            _check_file(path)
            os.replace(temporary, path)
            # Keep repository -> cache lock order. Loaders use lock-free read(),
            # never update(): a concurrent old load cannot survive this write.
            history_cache.history_summaries.invalidate(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return payload


def merge(path: Path, fields: dict[str, Any]) -> dict[str, Any]:
    return update(path, lambda payload: payload.update(fields))
