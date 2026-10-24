"""Explicit experimental list-cache integration, not the production default."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
from pathlib import Path
import socket
import subprocess
import threading
from unittest.mock import patch

import pytest

from backend import history_cache
from scripts import benchmark_history as bench


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("history integration must remain offline")
    class ForbiddenPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            forbidden()
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", ForbiddenPopen)


@pytest.fixture
def backend(tmp_path, monkeypatch):
    with patch("dotenv.load_dotenv", return_value=False):
        monkeypatch.setenv("VIDEO2KNOWLEDGE_WORKSPACE", str(tmp_path / "bootstrap"))
        main = importlib.import_module("backend.main")
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path.resolve())
    monkeypatch.setattr(main, "tasks", {})
    monkeypatch.setattr(main, "running_jobs", {})
    monkeypatch.setattr(main, "task_elapsed_seconds", lambda task: float(task.get("elapsed_seconds", 0)))
    monkeypatch.setattr(main, "_list_history_task_record", main._cached_history_task_record)
    monkeypatch.setattr(history_cache, "history_summaries",
                        history_cache.HistorySummaryCache(clock=lambda: 100), raising=False)
    return main


def finish(coroutine):
    try:
        try:
            coroutine.send(None)
        except StopIteration as done:
            return done.value
        pytest.fail("handler unexpectedly suspended")
    finally:
        coroutine.close()


def query(backend, **kwargs):
    return bench.run_query(backend, offset=0, limit=50, **kwargs)


def manifest(root, task_id="sample", **patches):
    payload = {"title": "磁盘标题", "output": "note", "origin": "web", "source": "local",
               "favorite": False, "created_at": "2026-01-01", "uploaded_filename": "source.wav",
               "note_template_snapshot": {"name": "模板", "instructions": "not retained"},
               "runtime": {"status": "completed", "progress": 100, "elapsed_seconds": 5,
                           "step_name": "完成", "created_at": "2026-01-02", "finished_at": "2026-01-03",
                           "result": {"title": "运行标题"}, "logs": ["not retained"]}, **patches}
    directory = root / task_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "task.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def freeze_fingerprints(monkeypatch):
    """Mask all stat changes to prove repository invalidation, not timestamp luck."""
    original = history_cache._snapshot
    snapshots = {}
    def frozen(workspace, task_id):
        key = (workspace, task_id)
        if key not in snapshots:
            snapshots[key] = original(workspace, task_id)
        return snapshots[key]
    monkeypatch.setattr(history_cache, "_snapshot", frozen)


@pytest.mark.parametrize("patches,live,expected", [
    ({}, None, {"title": "运行标题", "progress": 100, "platform": "local"}),
    ({}, {"result": {}}, {"title": "磁盘标题"}),
    ({}, {"result": {"title": "内存标题"}, "progress": 0}, {"title": "内存标题", "progress": 0}),
    ({"title": "", "uploaded_filename": "file.srt", "runtime": {}}, None, {"title": "file.srt", "status": "failed"}),
    ({"title": "", "uploaded_filename": "", "runtime": {}}, None, {"title": "未命名任务"}),
    ({"favorite": "true"}, {"favorite": True}, {"favorite": False}),
    ({"favorite": True}, {"favorite": False}, {"favorite": True}),
    ({"subtitle_import": True, "source_url": "https://youtube.com/x"}, None, {"platform": "subtitle"}),
    ({"source_url": "https://www.youtube.com/x"}, None, {"platform": "youtube"}),
    ({"source_url": "invalid", "source": "bilibili"}, None, {"platform": "other"}),
    ({"source": ""}, {"result": {"source": "douyin"}}, {"platform": "douyin"}),
    ({"source": "unrecognized"}, {"result": {"source": "douyin"}}, {"platform": "local"}),
    ({"source": "", "uploaded_filename": ""}, {"result": {"source": "invalid"}}, {"platform": "other"}),
    ({"note_template_snapshot": []}, None, {"template_name": ""}),
    ({"title": {"legacy": 1}}, {"result": {}}, {"title": "{'legacy': 1}"}),
    ({"runtime": {"progress": [1, 2], "status": "failed"}}, None, {"progress": [1, 2]}),
])
def test_legacy_precedence_cold_and_hit(backend, tmp_path, patches, live, expected):
    manifest(tmp_path, **patches)
    if live is not None:
        backend.tasks["sample"] = live
    direct = backend.history_task_summary("sample")
    assert all(direct[key] == value for key, value in expected.items())
    for _ in range(2):
        assert query(backend)["tasks"] == [direct]


@pytest.mark.parametrize("kwargs", [{}, {"favorite": True}, {"offset": 20},
                                      {"query": "编程", "status": "completed", "output": "note", "platform": "local"}])
def test_identical_queries_and_warm_zero_manifest_reads(backend, tmp_path, kwargs):
    bench.create_dataset(tmp_path / "data", 35)
    backend.WORKSPACE_DIR = (tmp_path / "data").resolve()
    options = {"offset": 0, "limit": 20, **kwargs}
    with bench.count_reads(backend.WORKSPACE_DIR) as first_reads:
        cold = bench.run_query(backend, **options)
    with bench.count_reads(backend.WORKSPACE_DIR) as hit_reads:
        warm = bench.run_query(backend, **options)
    assert cold == warm
    assert first_reads == {"manifests": 35, "notes": 0, "transcripts": 0, "other": 0}
    assert hit_reads == {"manifests": 0, "notes": 0, "transcripts": 0, "other": 0}
    assert backend.tasks == {}


def test_repository_update_and_favorite_endpoint_invalidate_even_same_fingerprint(backend, tmp_path, monkeypatch):
    path = manifest(tmp_path)
    freeze_fingerprints(monkeypatch)
    assert query(backend, favorite=True)["total"] == 0
    result = finish(backend.set_task_favorite("sample", backend.FavoritePayload(favorite=True)))
    assert result == {"task_id": "sample", "favorite": True}
    assert query(backend, favorite=True)["total"] == 1
    backend.task_repository.update(path, lambda value: value["runtime"].update(status="failed"))
    assert query(backend, status="failed")["total"] == 1


def test_failed_repository_replace_preserves_warm_cache_and_disk(backend, tmp_path, monkeypatch):
    path = manifest(tmp_path)
    before = query(backend)
    def fail(*args):
        raise OSError("synthetic replace failure")
    monkeypatch.setattr(backend.task_repository.os, "replace", fail)
    with pytest.raises(OSError):
        backend.task_repository.merge(path, {"favorite": True})
    with bench.count_reads(tmp_path) as counts:
        assert query(backend) == before
    assert counts["manifests"] == 0
    assert json.loads(path.read_text(encoding="utf-8"))["favorite"] is False


def test_uncached_summary_and_favorite_eligibility_ignore_stale_list(backend, tmp_path, monkeypatch):
    path = manifest(tmp_path)
    freeze_fingerprints(monkeypatch)
    assert query(backend)["tasks"][0]["status"] == "completed"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runtime"]["status"] = "failed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert backend.history_task_summary("sample")["status"] == "failed"
    with pytest.raises(backend.HTTPException) as caught:
        finish(backend.set_task_favorite("sample", backend.FavoritePayload(favorite=True)))
    assert caught.value.status_code == 409


def test_live_changes_elapsed_and_transcript_presence_not_frozen(backend, tmp_path):
    path = manifest(tmp_path)
    live = {"status": "processing", "result": {}, "progress": 0, "elapsed_seconds": 1}
    backend.tasks["sample"] = live
    assert query(backend)["tasks"][0]["elapsed_seconds"] == 1
    live.update(result={"title": "changed"}, elapsed_seconds=7, status="completed", progress=100)
    (path.parent / "transcript.json").write_text("{}", encoding="utf-8")
    updated = query(backend)["tasks"][0]
    assert (updated["title"], updated["elapsed_seconds"], updated["has_transcript"]) == ("changed", 7, True)
    (path.parent / "transcript.json").unlink()
    assert query(backend)["tasks"][0]["has_transcript"] is False


def test_origin_visibility_updates_and_no_private_fields_returned(backend, tmp_path):
    path = manifest(tmp_path, output="transcript", origin="agent")
    backend.tasks["sample"] = {"_origin": "web"}
    assert query(backend)["total"] == 0
    backend.task_repository.merge(path, {"origin": "web"})
    item = query(backend)["tasks"][0]
    assert set(item) == {"task_id", "status", "step_name", "progress", "output", "title", "created_at",
                         "finished_at", "elapsed_seconds", "platform", "template_name", "favorite", "has_transcript"}


def test_external_add_delete_corrupt_repair_and_workspace_switch(backend, tmp_path):
    path = manifest(tmp_path)
    assert query(backend)["total"] == 1
    manifest(tmp_path, "new")
    assert query(backend)["total"] == 2
    path.write_text("broken", encoding="utf-8")
    assert query(backend)["total"] == 1
    manifest(tmp_path, title="fixed")
    assert query(backend)["total"] == 2
    path.unlink()
    assert query(backend)["total"] == 1
    manifest(tmp_path / "other", "other-task")
    backend.WORKSPACE_DIR = (tmp_path / "other").resolve()
    assert [t["task_id"] for t in query(backend)["tasks"]] == ["other-task"]


def test_only_whitelisted_projection_retained(backend, tmp_path):
    manifest(tmp_path, source_url="https://youtube.com/x?token=PRIVATE_SENTINEL", api_key="PRIVATE_SENTINEL",
             note_template_snapshot={"name": "模板", "instructions": "PRIVATE_SENTINEL"},
             runtime={"status": "completed", "result": {"title": "clean", "markdown": "PRIVATE_SENTINEL"},
                      "logs": ["PRIVATE_SENTINEL"], "error": "PRIVATE_SENTINEL"})
    query(backend)
    assert history_cache.history_summaries.info().entries == 1
    encoded = b"".join(e.encoded for e in history_cache.history_summaries._entries.values())
    assert b"PRIVATE_SENTINEL" not in encoded and b"source_url" not in encoded


def test_delete_success_invalidates_exact_entry(backend, tmp_path, monkeypatch):
    manifest(tmp_path)
    backend.tasks["sample"] = {"status": "failed"}
    query(backend)
    assert history_cache.history_summaries.info().entries == 1
    async def cleanup(task_id):
        (tmp_path / task_id / "task.json").unlink()
    monkeypatch.setattr(backend.video_processor, "cleanup", cleanup)
    finish(backend.delete_task("sample"))
    assert history_cache.history_summaries.info().entries == 0
    assert query(backend)["total"] == 0


def test_repository_write_races_load_and_invalidates_before_return(backend, tmp_path, monkeypatch):
    path = manifest(tmp_path)
    freeze_fingerprints(monkeypatch)
    loaded, replaced, release = threading.Event(), threading.Event(), threading.Event()
    original_read = backend.task_repository.read
    original_replace = backend.task_repository.os.replace
    def blocked_read(target):
        payload = original_read(target)
        if not loaded.is_set():
            loaded.set()
            assert release.wait(5)
        return payload
    def signaled_replace(*args):
        original_replace(*args)
        replaced.set()
    monkeypatch.setattr(backend.task_repository, "read", blocked_read)
    monkeypatch.setattr(backend.task_repository.os, "replace", signaled_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reading = pool.submit(query, backend)
        assert loaded.wait(5)
        writing = pool.submit(backend.task_repository.merge, path, {"favorite": True})
        try:
            assert replaced.wait(5)
        finally:
            release.set()
        reading.result(timeout=5)
        writing.result(timeout=5)
    assert query(backend, favorite=True)["total"] == 1


@pytest.mark.parametrize("failure", ["change", "serialize"])
def test_failed_change_or_serialization_keeps_cached_snapshot(backend, tmp_path, monkeypatch, failure):
    path = manifest(tmp_path)
    before = query(backend)
    invalidations = []
    monkeypatch.setattr(history_cache.history_summaries, "invalidate", invalidations.append)
    def change(value):
        value["favorite"] = True
        if failure == "change":
            raise ValueError("synthetic change failure")
        value["invalid"] = float("nan")
    with pytest.raises(ValueError):
        backend.task_repository.update(path, change)
    assert invalidations == []
    assert list(path.parent.iterdir()) == [path]
    with bench.count_reads(tmp_path) as counts:
        assert query(backend) == before
    assert counts["manifests"] == 0
    assert json.loads(path.read_text(encoding="utf-8"))["favorite"] is False


def test_delete_failure_does_not_invalidate_or_remove_live_task(backend, tmp_path, monkeypatch):
    manifest(tmp_path)
    backend.tasks["sample"] = {"status": "failed"}
    before = query(backend)
    async def fail(task_id):
        raise OSError("synthetic cleanup failure")
    monkeypatch.setattr(backend.video_processor, "cleanup", fail)
    with pytest.raises(OSError):
        finish(backend.delete_task("sample"))
    assert "sample" in backend.tasks
    assert history_cache.history_summaries.info().entries == 1
    assert query(backend) == before


@pytest.mark.parametrize("runtime", [{"progress": [1, 2]}, {"result": {"title": {"legacy": 1}}}])
def test_nonflat_legacy_values_are_read_directly_not_retained(backend, tmp_path, runtime):
    manifest(tmp_path, runtime=runtime)
    expected = backend.history_task_summary("sample")
    for _ in range(2):
        with bench.count_reads(tmp_path) as counts:
            assert query(backend)["tasks"] == [expected]
        assert counts["manifests"] == 1
        assert history_cache.history_summaries.info().entries == 0


def test_corrupt_warm_manifest_uses_live_fallback_without_negative_cache(backend, tmp_path):
    path = manifest(tmp_path)
    query(backend)
    path.write_text("{broken", encoding="utf-8")
    backend.tasks["sample"] = {"status": "failed", "result": {"title": "live"}}
    for _ in range(2):
        with bench.count_reads(tmp_path) as counts:
            assert query(backend)["tasks"][0]["title"] == "live"
        assert counts["manifests"] == 1
        assert history_cache.history_summaries.info().entries == 0
    assert path.read_text(encoding="utf-8") == "{broken"


def test_list_declined_cache_still_uses_legacy_repository_reader(backend, tmp_path, monkeypatch):
    manifest(tmp_path)
    expected = backend.history_task_summary("sample")
    monkeypatch.setattr(history_cache, "_snapshot", lambda *args: None)
    with bench.count_reads(tmp_path) as counts:
        assert query(backend)["tasks"] == [expected]
    assert counts["manifests"] == 1
    assert history_cache.history_summaries.info().entries == 0


def test_repository_invalidates_only_the_written_manifest(backend, tmp_path):
    first = manifest(tmp_path, "first")
    manifest(tmp_path, "second")
    query(backend)
    backend.task_repository.merge(first, {"favorite": True})
    assert history_cache.history_summaries.info().entries == 1
    with bench.count_reads(tmp_path) as counts:
        assert query(backend, favorite=True)["total"] == 1
    assert counts["manifests"] == 1


def test_external_same_fingerprint_is_revalidated_at_fixed_deadline(backend, tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(history_cache, "history_summaries",
                        history_cache.HistorySummaryCache(clock=lambda: now[0]))
    path = manifest(tmp_path)
    freeze_fingerprints(monkeypatch)
    query(backend)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["favorite"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    now[0] = 129.9
    assert query(backend, favorite=True)["total"] == 0
    now[0] = 130.0
    assert query(backend, favorite=True)["total"] == 1


def test_safety_sensitive_readers_do_not_consult_list_cache(backend, tmp_path, monkeypatch):
    path = manifest(tmp_path, source_url="https://www.youtube.com/watch?v=synthetic")
    (path.parent / "notes.md").write_text("# synthetic body", encoding="utf-8")
    transcript = path.parent / "transcript.json"
    transcript.write_text(json.dumps({"segments": [{"start": 0, "end": 2, "text": "合成转录"}]}), encoding="utf-8")
    query(backend)
    def forbidden(*args):
        pytest.fail("non-list reader consulted history cache")
    monkeypatch.setattr(history_cache.history_summaries, "read", forbidden)
    assert backend.history_task_summary("sample")["title"] == "运行标题"
    inspected = finish(backend.inspect_source(backend.SourceInspectPayload(
        video_url="https://www.youtube.com/watch?v=synthetic")))
    assert inspected["reusable_task"]["task_id"] == "sample"
    transcript.write_text("broken", encoding="utf-8")
    assert finish(backend.inspect_source(backend.SourceInspectPayload(
        video_url="https://www.youtube.com/watch?v=synthetic")))["reusable_task"] is None
    restored = backend.restore_task_on_demand("sample")
    assert restored["result"]["markdown"] == "# synthetic body"
    assert finish(backend.get_task_status("sample"))["status"] == "completed"


@pytest.mark.parametrize("kwargs", [{}, {"favorite": True}, {"offset": 20},
                                      {"query": "编程", "status": "completed", "output": "note", "platform": "local"}])
def test_explicit_refresh_matches_cold_and_hit_without_writing(backend, tmp_path, kwargs):
    root = tmp_path / "data"
    bench.create_dataset(root, 35)
    backend.WORKSPACE_DIR = root.resolve()
    options = {"offset": 0, "limit": 20, **kwargs}
    before = {p: p.read_bytes() for p in root.glob("*/task.json")}
    cold = bench.run_query(backend, **options)
    assert bench.run_query(backend, **options) == cold
    with bench.count_reads(root) as counts:
        assert bench.run_query(backend, refresh=True, **options) == cold
    assert counts == {"manifests": 35, "notes": 0, "transcripts": 0, "other": 0}
    assert {p: p.read_bytes() for p in before} == before
    assert backend.tasks == {}


def test_explicit_refresh_rereads_external_same_fingerprint_change(backend, tmp_path, monkeypatch):
    path = manifest(tmp_path)
    freeze_fingerprints(monkeypatch)
    assert query(backend, favorite=True)["total"] == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["favorite"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert query(backend, favorite=True)["total"] == 0
    assert query(backend, favorite=True, refresh=True)["total"] == 1
