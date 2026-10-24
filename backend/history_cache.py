"""Bounded, process-local projections used only by the history list.

The loader must be read-only and return a flat, already-projected dictionary. This
module does not read manifests, restore tasks, or replace artifact validation. A
writer must invalidate after replace and before returning, outside any cache
loader: lock order is repository -> cache. No multi-process consistency is implied.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import stat
import threading
import time
from typing import Any, Callable

from .media_retention import is_safe_task_id

DEFAULT_MAX_ENTRIES = 12_000
DEFAULT_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_ENTRY_BYTES = 64 * 1024
DEFAULT_TTL_SECONDS = 30.0

# Disk-only inputs to the summary reducer, never a full manifest/result.
_PROJECTION_FIELDS = frozenset({
    "title", "runtime_result_title", "output", "origin", "favorite",
    "template_name", "created_at", "finished_at", "status", "step_name",
    "progress", "elapsed_seconds", "platform", "needs_live_source",
    "has_uploaded_filename",
})


@dataclass(frozen=True, slots=True)
class _Snapshot:
    path: Path
    scope: tuple
    fingerprint: tuple | None
    readable: bool = True


@dataclass(frozen=True, slots=True)
class _Entry:
    fingerprint: tuple
    loaded_at: float
    encoded: bytes


@dataclass(frozen=True, slots=True)
class CacheInfo:
    """Counts only: no task names, paths, titles, or projected contents."""
    entries: int
    payload_bytes: int
    hits: int
    misses: int
    evictions: int


def _key(path: Path) -> str:
    # Deliberately lexical: invalidation must never perform filesystem IO.
    return os.path.normcase(os.path.abspath(path))


def _plain_stat(path: Path, *, directory: bool) -> tuple[tuple, bool]:
    info = path.lstat()
    attributes = getattr(info, "st_file_attributes", 0)
    kind_ok = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not kind_ok or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise OSError("history_cache_unsafe_path")
    if not directory and info.st_nlink != 1:
        raise OSError("history_cache_unsafe_path")
    identity = (getattr(info, "st_dev", None), getattr(info, "st_ino", None), info.st_mode, attributes)
    reliable = (
        all(type(value) is int for value in identity)
        and identity[0] >= 0 and identity[1] > 0
        and (os.name != "nt" or hasattr(info, "st_file_attributes"))
    )
    if directory:
        return identity, reliable
    fingerprint = (*identity[:3], info.st_nlink, attributes,
                   getattr(info, "st_size", None), getattr(info, "st_mtime_ns", None),
                   getattr(info, "st_ctime_ns", None))
    return fingerprint, reliable and all(type(value) is int for value in fingerprint)


def _snapshot(workspace: Path, task_id: str) -> _Snapshot | None:
    """Check current paths even on hits; unreliable identity disables admission.

    The supplied workspace must already be canonical and absolute. Reject aliases
    rather than following them to read data outside the caller's stated scope.
    These pathname checks are not an atomic filesystem security sandbox.
    """
    if not is_safe_task_id(task_id):
        return None
    try:
        root = Path(workspace)
        if not root.is_absolute():
            return None
        root_identity, root_reliable = _plain_stat(root, directory=True)
        if root.resolve() != root:
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    path = root / task_id / "task.json"
    scope = (_key(root), *root_identity)
    try:
        directory = root / task_id
        directory_identity, directory_reliable = _plain_stat(directory, directory=True)
        if directory.resolve() != directory:
            return _Snapshot(path, scope, None, readable=False)
        file_identity, file_reliable = _plain_stat(path, directory=False)
        fingerprint = (*directory_identity, *file_identity)
        return _Snapshot(path, scope,
                         fingerprint if root_reliable and directory_reliable and file_reliable else None)
    except (OSError, ValueError, RuntimeError):
        return _Snapshot(path, scope, None, readable=False)


def _encode_projection(value: Any) -> bytes | None:
    if not isinstance(value, dict) or not value or not value.keys() <= _PROJECTION_FIELDS:
        return None
    if any(type(item) not in {str, int, float, bool, type(None)} for item in value.values()):
        return None
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (ValueError, UnicodeError):
        return None


class HistorySummaryCache:
    """LRU with a fixed revalidation deadline, not sliding expiration.

    Byte limits cover encoded projection payloads, not Python object/RSS overhead.
    Unsupported/oversized projections are returned unchanged but never retained;
    the caller is responsible for its direct-path fallback/legacy semantics.
    """

    def __init__(self, *, max_entries: int = DEFAULT_MAX_ENTRIES,
                 max_bytes: int = DEFAULT_MAX_BYTES,
                 max_entry_bytes: int = DEFAULT_MAX_ENTRY_BYTES,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        if (any(type(value) is not int or value <= 0 for value in (max_entries, max_bytes, max_entry_bytes))
                or type(ttl_seconds) not in {int, float}
                or not math.isfinite(ttl_seconds) or ttl_seconds <= 0):
            raise ValueError("history_cache_limits_invalid")
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._max_entry_bytes = max_entry_bytes
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._scope: tuple | None = None
        self._bytes = self._hits = self._misses = self._evictions = 0

    def _clear(self) -> None:
        self._entries.clear()
        self._bytes = 0

    def clear(self) -> None:
        with self._lock:
            self._clear()
            self._scope = None

    def _discard(self, key: str) -> None:
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._bytes -= len(previous.encoded)

    def invalidate(self, manifest_path: Path) -> None:
        with self._lock:
            self._discard(_key(manifest_path))

    def info(self) -> CacheInfo:
        with self._lock:
            return CacheInfo(len(self._entries), self._bytes, self._hits, self._misses, self._evictions)

    def _now(self) -> float | None:
        value = self._clock()
        return value if type(value) in {int, float} and math.isfinite(value) else None

    def read(self, workspace: Path, task_id: str,
             loader: Callable[[Path], dict[str, Any]]) -> dict[str, Any]:
        if not is_safe_task_id(task_id):
            return {}
        with self._lock:
            before = _snapshot(workspace, task_id)
            if before is None:
                # An unavailable root may have been replaced, so retain no old scope.
                self._clear()
                self._scope = None
                return {}
            if self._scope != before.scope:
                self._clear()
                self._scope = before.scope
            key = _key(before.path)
            if not before.readable:
                self._discard(key)
                return {}
            entry = self._entries.get(key)
            now = self._now()
            if (entry is not None and before.fingerprint is not None
                    and entry.fingerprint == before.fingerprint and now is not None
                    and 0 <= now - entry.loaded_at < self._ttl):
                try:
                    decoded = json.loads(entry.encoded)
                    if _encode_projection(decoded) is None:
                        raise ValueError("history_cache_invalid_entry")
                except (TypeError, ValueError, UnicodeError):
                    self._clear()
                else:
                    self._hits += 1
                    self._entries.move_to_end(key)
                    return decoded
            self._misses += 1
            self._discard(key)
            # A moving file gets only one extra read. No stale-if-error or negative cache.
            for attempt in range(2):
                started = self._now()
                value = loader(before.path)
                after = _snapshot(workspace, task_id)
                if after is None or after.scope != before.scope:
                    self._clear()
                    self._scope = None
                    return {}
                if not after.readable:
                    return {}
                if after.fingerprint != before.fingerprint:
                    if attempt == 0:
                        before = after
                        continue
                    return value if isinstance(value, dict) else {}
                encoded = _encode_projection(value)
                finished = self._now()
                if (before.fingerprint is not None and encoded is not None
                        and started is not None and finished is not None
                        and 0 <= finished - started < self._ttl
                        and len(encoded) <= min(self._max_entry_bytes, self._max_bytes)):
                    while self._entries and (
                        len(self._entries) >= self._max_entries or self._bytes + len(encoded) > self._max_bytes
                    ):
                        _, evicted = self._entries.popitem(last=False)
                        self._bytes -= len(evicted.encoded)
                        self._evictions += 1
                    self._entries[key] = _Entry(before.fingerprint, started, encoded)
                    self._bytes += len(encoded)
                return value if isinstance(value, dict) else {}
            return {}  # All iterations above return; retained for static analysis.


# Resolve through the module in both readers and writers so they share one cache.
history_summaries = HistorySummaryCache()
