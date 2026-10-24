"""G5.1-A: standalone cache rules, synthetic files and an injected clock only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import importlib
import json
import math
from pathlib import Path
import socket
import stat
import subprocess
import threading

import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("history cache tests must remain offline")
    class ForbiddenPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            forbidden()
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", ForbiddenPopen)


@pytest.fixture
def module():
    return importlib.import_module("backend.history_cache")


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def cache(module, clock):
    return module.HistorySummaryCache(clock=clock)


def manifest(root, task_id="task-1", **values):
    directory = root / task_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "task.json"
    path.write_text(json.dumps({"title": "合成笔记", **values}, ensure_ascii=False), encoding="utf-8")
    return path


class Loader:
    def __init__(self):
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        return json.loads(path.read_text(encoding="utf-8"))


def test_defaults_and_hit_never_reads_body(module, cache, tmp_path, monkeypatch):
    path = manifest(tmp_path)
    (path.parent / "notes.md").write_text("private body", encoding="utf-8")
    loader = Loader()
    assert cache.read(tmp_path, "task-1", loader) == {"title": "合成笔记"}
    def forbidden(*args, **kwargs):
        pytest.fail("cache hit opened a file")
    monkeypatch.setattr(Path, "open", forbidden)
    assert cache.read(tmp_path, "task-1", loader) == {"title": "合成笔记"}
    assert loader.calls == [path]
    assert module.DEFAULT_MAX_ENTRIES == 12000
    assert module.DEFAULT_MAX_BYTES == 16 * 1024 * 1024
    assert module.DEFAULT_MAX_ENTRY_BYTES == 64 * 1024
    assert module.DEFAULT_TTL_SECONDS == 30
    assert (cache.info().hits, cache.info().misses, cache.info().entries) == (1, 1, 1)


def test_fixed_ttl_hit_does_not_extend_deadline(module, cache, clock, tmp_path, monkeypatch):
    manifest(tmp_path)
    original = module._snapshot(tmp_path, "task-1")
    monkeypatch.setattr(module, "_snapshot", lambda *args: original)
    values = {"title": "before"}
    calls = []
    def load(path):
        calls.append(path)
        return dict(values)
    cache.read(tmp_path, "task-1", load)
    values["title"] = "after"
    for now in (101, 129, 129.9):
        clock.now = now
        assert cache.read(tmp_path, "task-1", load)["title"] == "before"
    clock.now = 130
    assert cache.read(tmp_path, "task-1", load)["title"] == "after"
    assert len(calls) == 2


@pytest.mark.parametrize("field", range(12))
def test_each_fingerprint_component_invalidates(module, cache, tmp_path, monkeypatch, field):
    manifest(tmp_path)
    original = module._snapshot(tmp_path, "task-1")
    current = original
    monkeypatch.setattr(module, "_snapshot", lambda *args: current)
    loader = Loader()
    cache.read(tmp_path, "task-1", loader)
    # A fingerprint consists of a directory identity and the manifest stat tuple.
    fingerprint = list(original.fingerprint)
    assert len(fingerprint) == 12
    fingerprint[field] = (fingerprint[field], "changed")
    current = replace(original, fingerprint=tuple(fingerprint))
    cache.read(tmp_path, "task-1", loader)
    assert len(loader.calls) == 2


def test_external_replacement_delete_and_repair(cache, tmp_path):
    path = manifest(tmp_path)
    loader = Loader()
    cache.read(tmp_path, "task-1", loader)
    replacement = path.with_name("replacement.json")
    replacement.write_text('{"title":"replaced"}', encoding="utf-8")
    replacement.replace(path)
    assert cache.read(tmp_path, "task-1", loader)["title"] == "replaced"
    path.unlink()
    assert cache.read(tmp_path, "task-1", loader) == {}
    assert cache.info().entries == 0
    manifest(tmp_path, title="repaired")
    assert cache.read(tmp_path, "task-1", loader)["title"] == "repaired"


def test_workspace_switch_and_same_path_recreation(cache, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    path = manifest(a, title="A")
    manifest(b, title="B")
    loader = Loader()
    for root, expected in ((a, "A"), (b, "B"), (a, "A")):
        assert cache.read(root, "task-1", loader)["title"] == expected
    assert len(loader.calls) == 3
    # Keep the old root alive under another name so its inode cannot be reused.
    a.rename(tmp_path / "old-a")
    path = manifest(a, title="A-new")
    assert cache.read(a, "task-1", loader)["title"] == "A-new"
    assert cache.info().entries == 1 and loader.calls[-1] == path


def test_task_directory_replacement_invalidates(cache, tmp_path):
    path = manifest(tmp_path)
    loader = Loader()
    cache.read(tmp_path, "task-1", loader)
    path.parent.rename(tmp_path / "old-task")
    manifest(tmp_path, title="new directory")
    assert cache.read(tmp_path, "task-1", loader)["title"] == "new directory"
    assert len(loader.calls) == 2


def test_lru_entry_bound_and_recency(module, clock, tmp_path):
    cache = module.HistorySummaryCache(max_entries=2, clock=clock)
    for task_id in ("a", "b", "c"):
        manifest(tmp_path, task_id)
    loader = Loader()
    for task_id in ("a", "b", "a", "c", "a", "b"):
        cache.read(tmp_path, task_id, loader)
        assert cache.info().entries <= 2
    assert [p.parent.name for p in loader.calls] == ["a", "b", "c", "b"]
    assert cache.info().evictions == 2


def test_encoded_byte_bound_uses_utf8_and_exact_limit(module, clock, tmp_path):
    payload = {"title": "中文"}
    size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    cache = module.HistorySummaryCache(max_bytes=size * 2, max_entry_bytes=size, clock=clock)
    loader = Loader()
    for task_id in ("a", "b", "c"):
        manifest(tmp_path, task_id, **payload)
        cache.read(tmp_path, task_id, loader)
        assert cache.info().payload_bytes <= size * 2
    assert cache.info().entries == 2 and cache.info().payload_bytes == size * 2
    assert cache.info().evictions == 1


@pytest.mark.parametrize("limit_field", ["max_bytes", "max_entry_bytes"])
def test_oversized_projection_returned_intact_but_never_cached(module, clock, tmp_path, limit_field):
    cache = module.HistorySummaryCache(**{limit_field: 8}, clock=clock)
    path = manifest(tmp_path, title="Long title not truncated")
    loader = Loader()
    for _ in range(2):
        assert cache.read(tmp_path, "task-1", loader)["title"] == "Long title not truncated"
    assert loader.calls == [path, path] and cache.info().entries == 0


@pytest.mark.parametrize("values", [
    {}, {"title": "x", "api_key": "PRIVATE_KEY_SENTINEL"},
    {"title": "x", "source_url": "https://example.org/?token=PRIVATE"},
    {"title": "x", "runtime": {"logs": ["PRIVATE"]}},
    {"title": ["unsupported legacy value"]}, {"progress": math.nan},
    {"elapsed_seconds": math.inf}, {"title": "\ud800"},
])
def test_unsupported_or_empty_projection_never_retained(cache, tmp_path, values):
    manifest(tmp_path)
    calls = []
    def load(path):
        calls.append(path)
        return values
    for _ in range(2):
        cache.read(tmp_path, "task-1", load)
    assert len(calls) == 2 and cache.info().entries == 0
    assert "PRIVATE" not in repr(cache.info())


def test_loaded_and_returned_values_cannot_mutate_cache(cache, tmp_path):
    manifest(tmp_path)
    original = {"title": "original", "favorite": True}
    first = cache.read(tmp_path, "task-1", lambda path: original)
    original["title"] = "changed loader object"
    first["favorite"] = False
    second = cache.read(tmp_path, "task-1", lambda path: pytest.fail("hit missed"))
    second["title"] = "changed returned object"
    assert cache.read(tmp_path, "task-1", lambda path: {}) == {"title": "original", "favorite": True}


@pytest.mark.parametrize("bad_value", ["broken", "[]", "null"])
def test_corrupt_loader_failure_does_not_serve_stale_or_poison_repair(cache, tmp_path, bad_value):
    path = manifest(tmp_path)
    loader = Loader()
    cache.read(tmp_path, "task-1", loader)
    path.write_text(bad_value, encoding="utf-8")
    if bad_value == "broken":
        with pytest.raises(ValueError):
            cache.read(tmp_path, "task-1", loader)
    else:
        assert cache.read(tmp_path, "task-1", loader) == {}
    assert cache.info().entries == 0
    manifest(tmp_path, title="repaired")
    assert cache.read(tmp_path, "task-1", loader)["title"] == "repaired"


def test_loader_io_failure_is_not_cached(cache, tmp_path):
    manifest(tmp_path)
    def fail(path):
        raise OSError("synthetic failure")
    for _ in range(2):
        with pytest.raises(OSError):
            cache.read(tmp_path, "task-1", fail)
    assert cache.info().entries == 0
    assert cache.read(tmp_path, "task-1", Loader())["title"] == "合成笔记"


@pytest.mark.parametrize("task_id", ["../outside", "a/b", "", ".", "..", "a" * 129, None])
def test_unsafe_id_never_reaches_loader(cache, tmp_path, task_id):
    assert cache.read(tmp_path, task_id, lambda path: pytest.fail("unsafe loader")) == {}


@pytest.mark.parametrize("target,field,value", [
    ("file", "st_mode", stat.S_IFLNK), ("file", "st_mode", stat.S_IFDIR),
    ("file", "st_file_attributes", 0x400), ("file", "st_nlink", 2),
    ("directory", "st_file_attributes", 0x400), ("root", "st_file_attributes", 0x400),
])
def test_unsafe_metadata_invalidates_without_privileged_links(cache, tmp_path, monkeypatch, target, field, value):
    from types import SimpleNamespace
    path = manifest(tmp_path)
    cache.read(tmp_path, "task-1", Loader())
    selected = {"file": path, "directory": path.parent, "root": tmp_path}[target]
    original = Path.lstat
    def modified(self, *args, **kwargs):
        info = original(self, *args, **kwargs)
        if self != selected:
            return info
        fields = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
        fields[field] = value
        return SimpleNamespace(**fields)
    monkeypatch.setattr(Path, "lstat", modified)
    assert cache.read(tmp_path, "task-1", lambda path: pytest.fail("unsafe loader")) == {}
    assert cache.info().entries == 0


def test_unreliable_identity_bypasses_cache(module, cache, tmp_path, monkeypatch):
    manifest(tmp_path)
    snapshot = module._snapshot(tmp_path, "task-1")
    monkeypatch.setattr(module, "_snapshot", lambda *args: replace(snapshot, fingerprint=None))
    loader = Loader()
    cache.read(tmp_path, "task-1", loader)
    cache.read(tmp_path, "task-1", loader)
    assert len(loader.calls) == 2 and cache.info().entries == 0


def test_one_missing_or_unsafe_task_does_not_flush_unrelated_entries(cache, tmp_path):
    a, b = manifest(tmp_path, "a"), manifest(tmp_path, "b")
    loader = Loader()
    for task_id in ("a", "b"):
        cache.read(tmp_path, task_id, loader)
    assert cache.read(tmp_path, "missing", lambda path: pytest.fail("missing loader")) == {}
    assert cache.info().entries == 2
    a.unlink()
    assert cache.read(tmp_path, "a", lambda path: pytest.fail("deleted loader")) == {}
    assert cache.info().entries == 1
    assert cache.read(tmp_path, "b", loader)["title"] == "合成笔记"
    assert loader.calls == [a, b]


def test_internal_corrupt_entry_falls_back_to_loader(module, cache, tmp_path):
    path = manifest(tmp_path)
    loader = Loader()
    cache.read(tmp_path, "task-1", loader)
    key = module._key(path)
    cache._entries[key] = replace(cache._entries[key], encoded=b"broken cache bytes")
    assert cache.read(tmp_path, "task-1", loader)["title"] == "合成笔记"
    assert len(loader.calls) == 2 and cache.info().entries == 1
    assert cache.info().payload_bytes == len(cache._entries[key].encoded)


@pytest.mark.parametrize("target,field,value", [
    ("file", "st_ino", 0), ("file", "st_dev", None),
    ("file", "st_mtime_ns", None), ("file", "st_ctime_ns", None),
    ("file", "st_size", None), ("directory", "st_ino", 0),
    ("root", "st_ino", 0),
])
def test_actual_missing_identity_fields_read_fresh_without_admission(cache, tmp_path, monkeypatch, target, field, value):
    from types import SimpleNamespace
    path = manifest(tmp_path)
    selected = {"file": path, "directory": path.parent, "root": tmp_path}[target]
    original = Path.lstat
    def modified(self, *args, **kwargs):
        info = original(self, *args, **kwargs)
        if self != selected:
            return info
        fields = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
        fields[field] = value
        return SimpleNamespace(**fields)
    monkeypatch.setattr(Path, "lstat", modified)
    loader = Loader()
    for _ in range(2):
        assert cache.read(tmp_path, "task-1", loader)["title"] == "合成笔记"
    assert len(loader.calls) == 2 and cache.info().entries == 0


def test_noncanonical_workspace_and_task_alias_are_rejected(cache, tmp_path, monkeypatch):
    path = manifest(tmp_path)
    def forbidden(path):
        pytest.fail("alias reached loader")
    assert cache.read(Path("."), "task-1", forbidden) == {}
    inside = tmp_path / "unused"
    inside.mkdir()
    assert cache.read(inside / "..", "task-1", forbidden) == {}
    original = Path.resolve
    def aliased(self, *args, **kwargs):
        return tmp_path / "other-task" if self == path.parent else original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", aliased)
    assert cache.read(tmp_path, "task-1", forbidden) == {}


def test_file_becomes_unsafe_while_loading_drops_candidate_only(cache, tmp_path):
    a, b = manifest(tmp_path, "a"), manifest(tmp_path, "b")
    loader = Loader()
    cache.read(tmp_path, "b", loader)
    def removed(path):
        result = loader(path)
        path.unlink()
        return result
    assert cache.read(tmp_path, "a", removed) == {}
    assert cache.info().entries == 1
    cache.read(tmp_path, "b", loader)
    assert loader.calls == [b, a]


def test_unavailable_root_clears_old_scope(cache, tmp_path):
    root = tmp_path / "root"
    manifest(root)
    loader = Loader()
    cache.read(root, "task-1", loader)
    root.rename(tmp_path / "old-root")
    assert cache.read(root, "task-1", loader) == {}
    assert cache.info().entries == 0


def test_unrelated_directory_mtime_changes_do_not_invalidate(cache, tmp_path):
    path = manifest(tmp_path, "a")
    loader = Loader()
    cache.read(tmp_path, "a", loader)
    manifest(tmp_path, "b")
    (path.parent / "notes.md").write_text("synthetic body", encoding="utf-8")
    assert cache.read(tmp_path, "a", loader)["title"] == "合成笔记"
    assert loader.calls == [path]


def test_one_replacement_during_load_retries_once(cache, tmp_path):
    path = manifest(tmp_path)
    calls = []
    def load(target):
        calls.append(target)
        result = json.loads(target.read_text(encoding="utf-8"))
        if len(calls) == 1:
            other = target.with_name("replacement.json")
            other.write_text('{"title":"after replacement"}', encoding="utf-8")
            other.replace(target)
        return result
    assert cache.read(tmp_path, "task-1", load)["title"] == "after replacement"
    assert calls == [path, path] and cache.info().entries == 1


def test_continuous_changes_are_bounded_and_not_cached(cache, tmp_path):
    manifest(tmp_path)
    calls = []
    def load(path):
        calls.append(path)
        result = {"title": str(len(calls))}
        other = path.with_name("replacement.json")
        other.write_text(json.dumps(result), encoding="utf-8")
        other.replace(path)
        return result
    assert cache.read(tmp_path, "task-1", load) == {"title": "2"}
    assert len(calls) == 2 and cache.info().entries == 0


def test_clear_and_exact_invalidation_do_not_touch_files(cache, tmp_path, monkeypatch):
    a, b = manifest(tmp_path, "a"), manifest(tmp_path, "b")
    loader = Loader()
    for task_id in ("a", "b"):
        cache.read(tmp_path, task_id, loader)
    def forbidden(*args, **kwargs):
        pytest.fail("invalidation must not do IO")
    with monkeypatch.context() as patcher:
        patcher.setattr(Path, "lstat", forbidden)
        patcher.setattr(Path, "open", forbidden)
        cache.invalidate(tmp_path / "elsewhere" / "task.json")
        assert cache.info().entries == 2
        cache.invalidate(a)
        cache.invalidate(a)
        assert cache.info().entries == 1
    assert cache.read(tmp_path, "b", loader)["title"] == "合成笔记"
    cache.read(tmp_path, "a", loader)
    assert loader.calls == [a, b, a]
    cache.clear()
    assert cache.info().entries == 0 and cache.info().payload_bytes == 0
    cache.read(tmp_path, "b", loader)
    assert loader.calls[-1] == b


def test_invalidation_waits_for_inflight_load_then_removes_old_entry(cache, tmp_path):
    path = manifest(tmp_path, favorite=False)
    loaded, release, invalidating = threading.Event(), threading.Event(), threading.Event()
    def load(target):
        result = json.loads(target.read_text(encoding="utf-8"))
        loaded.set()
        assert release.wait(5), "coordinator did not release loader"
        return result
    def write_and_invalidate():
        assert loaded.wait(5)
        path.write_text('{"title":"new","favorite":true}', encoding="utf-8")
        invalidating.set()
        cache.invalidate(path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(cache.read, tmp_path, "task-1", load)
        writing = pool.submit(write_and_invalidate)
        try:
            assert invalidating.wait(5)
        finally:
            release.set()
        writing.result(timeout=5)
        reading.result(timeout=5)
    assert cache.info().entries == 0
    assert cache.read(tmp_path, "task-1", Loader())["favorite"] is True


@pytest.mark.parametrize("now", [99, math.nan, math.inf])
def test_unreliable_clock_does_not_serve_old_entry(cache, clock, tmp_path, now):
    manifest(tmp_path)
    loader = Loader()
    cache.read(tmp_path, "task-1", loader)
    clock.now = now
    cache.read(tmp_path, "task-1", loader)
    assert len(loader.calls) == 2
    if not math.isfinite(now):
        assert cache.info().entries == 0


def test_slow_load_does_not_get_a_new_ttl_after_finishing(cache, clock, tmp_path):
    manifest(tmp_path)
    def load(path):
        clock.now += 31
        return {"title": "slow"}
    assert cache.read(tmp_path, "task-1", load) == {"title": "slow"}
    assert cache.info().entries == 0


@pytest.mark.parametrize("kwargs", [
    {"max_entries": 0}, {"max_entries": True}, {"max_entries": 1.5},
    {"max_bytes": -1}, {"max_entry_bytes": 0}, {"ttl_seconds": 0},
    {"ttl_seconds": math.nan}, {"ttl_seconds": math.inf}, {"ttl_seconds": True},
])
def test_invalid_limits_rejected(module, kwargs):
    with pytest.raises(ValueError, match="history_cache_limits_invalid"):
        module.HistorySummaryCache(**kwargs)
