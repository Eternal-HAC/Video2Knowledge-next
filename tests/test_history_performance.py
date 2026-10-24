"""Deterministic IO/compatibility gates; no noisy elapsed-time CI threshold."""
import importlib
import json
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("history benchmarks must remain offline")
    class ForbiddenPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            forbidden()
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", ForbiddenPopen)


@pytest.fixture
def bench():
    return importlib.import_module("scripts.benchmark_history")


@pytest.fixture
def backend(tmp_path, monkeypatch):
    # No real workspace/dotenv read when this file is tested on its own.
    with patch("dotenv.load_dotenv", return_value=False):
        monkeypatch.setenv("VIDEO2KNOWLEDGE_WORKSPACE", str(tmp_path / "bootstrap"))
        main = importlib.import_module("backend.main")
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(main, "tasks", {})
    return main


def query(backend, **kwargs):
    bench = importlib.import_module("scripts.benchmark_history")
    return bench.run_query(backend, offset=0, limit=20, **kwargs)


@pytest.mark.parametrize("values,p50,p95", [([1], 1, 1), ([4, 1, 3, 2], 2, 4), (list(range(1, 21)), 10, 19)])
def test_nearest_rank_percentiles(bench, values, p50, p95):
    assert bench.percentile(values, 50) == p50
    assert bench.percentile(values, 95) == p95


@pytest.mark.parametrize("size", [0, -1, 10001, True])
def test_synthetic_size_bounded(bench, tmp_path, size):
    with pytest.raises(ValueError, match="benchmark_arguments_invalid"):
        bench.create_dataset(tmp_path / "invalid", size)
    assert not (tmp_path / "invalid").exists()


def test_dataset_is_deterministic_and_refuses_overwrite(bench, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    first, second = bench.create_dataset(a, 12), bench.create_dataset(b, 12)
    assert first == second and first["task_count"] == 12
    with pytest.raises(ValueError, match="benchmark_output_unavailable"):
        bench.create_dataset(a, 12)
    assert len(list(a.glob("*/task.json"))) == 12


def test_benchmark_reports_counts_not_bodies_or_paths(bench, backend, tmp_path):
    dataset = tmp_path / "synthetic"
    bench.create_dataset(dataset, 12)
    report = bench.measure_dataset(backend, dataset, 12, repeats=2)
    serialized = json.dumps(report)
    assert report["task_count"] == 12 and report["warm_repeats"] == 2
    assert report["startup"]["restored_tasks"] <= backend.TASK_HISTORY_LIMIT
    assert set(report["queries"]) == set(bench.QUERY_CASES)
    assert report["queries"]["all"]["reads"]["notes"] == 0
    assert report["queries"]["all"]["reads"]["transcripts"] == 0
    assert "合成课程" not in serialized and str(tmp_path) not in serialized
    assert "raw_ms" in report["queries"]["all"]


def test_default_benchmark_measures_production_reader(bench, backend, tmp_path, monkeypatch):
    root = tmp_path / "data"
    bench.create_dataset(root, 2)
    original = backend._list_history_task_record
    calls = []

    def recording(task_id):
        calls.append(task_id)
        return original(task_id)

    monkeypatch.setattr(backend, "_list_history_task_record", recording)
    bench.measure_dataset(backend, root, 2, repeats=2)
    assert set(calls) == {"g5-000000", "g5-000001"}
    assert backend._list_history_task_record is recording


def test_instrumentation_counts_real_reads_and_restores_patch(bench, tmp_path):
    target = tmp_path / "task.json"
    target.write_text("{}")
    original = Path.open
    with bench.count_reads(tmp_path) as counts:
        target.read_text()
        target.is_file()
    assert counts == {"manifests": 1, "notes": 0, "transcripts": 0, "other": 0}
    assert Path.open is original


def test_history_reads_each_manifest_once_per_request(bench, backend, tmp_path):
    bench.create_dataset(tmp_path / "data", 30)
    backend.WORKSPACE_DIR = (tmp_path / "data").resolve()
    with bench.count_reads(backend.WORKSPACE_DIR) as counts:
        result = query(backend)
    assert result["total"] > 0
    assert counts == {"manifests": 30, "notes": 0, "transcripts": 0, "other": 0}


@pytest.mark.parametrize("refresh", [False, True])
def test_default_list_bypasses_experimental_cache(bench, backend, tmp_path, monkeypatch, refresh):
    from backend import history_cache
    root = tmp_path / "data"
    bench.create_dataset(root, 8)
    backend.WORKSPACE_DIR = root.resolve()
    cache = history_cache.HistorySummaryCache()
    monkeypatch.setattr(history_cache, "history_summaries", cache)

    def forbidden(*args, **kwargs):
        pytest.fail("default history must not enter the regressed cache reader")

    monkeypatch.setattr(backend, "_cached_history_task_record", forbidden)
    monkeypatch.setattr(cache, "read", forbidden)
    previous = None
    for _ in range(2):
        with bench.count_reads(root) as reads, bench.count_metadata(root.resolve()) as metadata:
            current = query(backend, refresh=refresh)
        assert reads == {"manifests": 8, "notes": 0, "transcripts": 0, "other": 0}
        assert metadata["resolve"] == 8
        if previous is not None:
            assert current == previous
        previous = current
    assert cache.info().entries == 0


def test_history_visibility_and_live_precedence_unchanged(bench, backend, tmp_path):
    root = tmp_path / "data"
    bench.create_dataset(root, 20)
    backend.WORKSPACE_DIR = root.resolve()
    visible = query(backend)
    ids = {s["task_id"] for s in visible["tasks"]}
    for directory in root.iterdir():
        manifest = json.loads((directory / "task.json").read_text(encoding="utf-8"))
        hidden = manifest["output"] == "transcript" and manifest["origin"] != "web"
        assert (directory.name not in ids) == hidden
    task_id = "g5-000004"
    backend.tasks[task_id] = backend.new_task(status="processing", task_id=task_id)
    backend.tasks[task_id].update(output="note", result={"title": "内存标题"})
    assert query(backend, query="内存标题", status="active")["tasks"][0]["task_id"] == task_id
    assert "result" not in query(backend, query="内存标题")["tasks"][0]


def test_history_updates_and_deletions_are_visible_next_request(bench, backend, tmp_path):
    root = tmp_path / "data"
    bench.create_dataset(root, 5)
    backend.WORKSPACE_DIR = root.resolve()
    task_id = "g5-000000"
    path = root / task_id / "task.json"
    before = query(backend, favorite=True)["total"]
    backend.task_repository.merge(path, {"favorite": True})
    assert query(backend, favorite=True)["total"] == before + 1
    path.unlink()
    assert task_id not in {t["task_id"] for t in query(backend)["tasks"]}


def test_corrupt_manifest_and_memory_only_origin(bench, backend, tmp_path):
    bench.create_dataset(tmp_path / "data", 5)
    backend.WORKSPACE_DIR = (tmp_path / "data").resolve()
    (backend.WORKSPACE_DIR / "g5-000000" / "task.json").write_text("broken")
    backend.tasks["agent-only"] = backend.new_task("completed", "agent-only")
    backend.tasks["agent-only"].update(output="transcript", _origin="agent")
    backend.tasks["web-only"] = backend.new_task("completed", "web-only")
    backend.tasks["web-only"].update(output="transcript", _origin="web")
    with bench.count_reads(backend.WORKSPACE_DIR) as reads:
        result = query(backend)
    ids = {s["task_id"] for s in result["tasks"]}
    assert "g5-000000" not in ids and "agent-only" not in ids and "web-only" in ids
    assert reads["manifests"] == 5


def test_cli_rejects_invalid_arguments_without_echo(bench, capsys):
    with pytest.raises(SystemExit) as exc:
        bench.main(["--PRIVATE_SENTINEL"])
    assert exc.value.code == 2
    result = capsys.readouterr()
    assert "PRIVATE_SENTINEL" not in result.out + result.err


def test_bootstrap_refuses_loaded_backend(bench, backend, tmp_path):
    with pytest.raises(ValueError, match="benchmark_backend_already_loaded"):
        bench.load_isolated_backend(tmp_path)


def test_measurement_restores_backend_globals_on_failure(bench, backend, tmp_path, monkeypatch):
    old_workspace, old_tasks = backend.WORKSPACE_DIR, backend.tasks
    bench.create_dataset(tmp_path / "data", 2)
    def fail():
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(backend, "restore_tasks_from_workspace", fail)
    with pytest.raises(RuntimeError):
        bench.measure_dataset(backend, tmp_path / "data", 2, repeats=2)
    assert backend.WORKSPACE_DIR is old_workspace and backend.tasks is old_tasks


def test_origin_visibility_uses_same_manifest_as_summary(bench, backend, tmp_path, monkeypatch):
    root = tmp_path / "data"
    bench.create_dataset(root, 3)
    backend.WORKSPACE_DIR = root.resolve()
    original = backend.task_repository.read
    reads = 0
    def changing_read(path):
        nonlocal reads
        result = original(path)
        if path.parent.name == "g5-000002":
            reads += 1
            return {**result, "origin": "web" if reads == 1 else "agent"}
        return result
    monkeypatch.setattr(backend.task_repository, "read", changing_read)
    assert "g5-000002" in {t["task_id"] for t in query(backend)["tasks"]}
    assert reads == 1


def test_unsafe_directory_rejected_before_manifest_read(backend, monkeypatch):
    def reject(task_id):
        raise ValueError("unsafe")
    def forbidden(path):
        pytest.fail("unsafe directory reached manifest reader")
    monkeypatch.setattr(backend, "task_directory", reject)
    monkeypatch.setattr(backend.task_repository, "read", forbidden)
    assert backend.history_task_summary("unsafe") is None


def test_handler_suspension_fails_closed(bench):
    from types import SimpleNamespace
    class Suspend:
        def __await__(self):
            yield "not a synchronous history handler"
    async def route(**kwargs):
        await Suspend()
    with pytest.raises(RuntimeError, match="benchmark_handler_requires_event_loop"):
        bench.run_query(SimpleNamespace(list_recent_tasks=route), offset=0, limit=20)


def test_history_resolves_each_task_directory_once(bench, backend, tmp_path, monkeypatch):
    root = tmp_path / "data"
    bench.create_dataset(root, 8)
    backend.WORKSPACE_DIR = root.resolve()
    original = backend.task_directory
    calls = []
    def recording(task_id):
        calls.append(task_id)
        return original(task_id)
    monkeypatch.setattr(backend, "task_directory", recording)
    query(backend)
    assert len(calls) == 8 and len(set(calls)) == 8


def test_cache_profile_separates_modes_and_preserves_results(bench, backend, tmp_path):
    from backend import history_cache
    root = tmp_path / "data"
    bench.create_dataset(root, 8)
    previous = history_cache.history_summaries
    report = bench.measure_cache_dataset(backend, root, 8, repeats=2)
    assert history_cache.history_summaries is previous
    assert report["ttl_seconds"] == 30 and report["task_count"] == 8
    for query in report["queries"].values():
        assert set(query) == {"direct", "cache_empty", "hit", "refresh", "invalidated", "capacity"}
        assert len({mode["response_sha256"] for mode in query.values()}) == 1
        assert query["direct"]["reads"]["manifests"] == 8
        assert query["cache_empty"]["reads"]["manifests"] == 8
        assert query["hit"]["reads"]["manifests"] == 0
        assert query["refresh"]["reads"]["manifests"] == 8
        assert query["invalidated"]["reads"]["manifests"] == 1
        assert query["capacity"]["cache"]["entries"] <= 2
        for mode in query.values():
            assert len(mode["samples"]) == 2
            assert mode["reads"]["notes"] == mode["reads"]["transcripts"] == 0
            assert mode["metadata_calls"]["resolve"] > 0
            assert mode["prepare_and_query_python_peak_bytes"] > 0
    serialized = json.dumps(report)
    assert "合成课程" not in serialized and str(root) not in serialized
