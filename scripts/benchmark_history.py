"""Offline synthetic history benchmark; never run inside a live backend process."""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import socket
import subprocess
import sys
import time
import tracemalloc
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from scripts.quality_io import SafeArgumentParser, checked_path, write_report
from scripts.release_evidence import environment_snapshot

QUERY_CASES = {
    "all": {},
    "filtered": {"query": "编程", "status": "completed", "output": "note", "platform": "local"},
    "favorites": {"favorite": True},
    "page_two": {"offset": 20},
}


def percentile(values: list[float], percent: int) -> float:
    """Nearest-rank estimate. Small sample p95 is descriptive, not an SLO."""
    if not values or not 0 < percent <= 100:
        raise ValueError("benchmark_arguments_invalid")
    return sorted(values)[max(0, math.ceil(len(values) * percent / 100) - 1)]


def _new_directory(path: Path) -> Path:
    try:
        target = checked_path(path, output=True)
        target.mkdir()  # Exclusive; never adopt or empty an existing directory.
        return target
    except (ValueError, OSError):
        raise ValueError("benchmark_output_unavailable") from None


def create_dataset(root: Path, size: int) -> dict:
    if type(size) is not int or not 1 <= size <= 10000:
        raise ValueError("benchmark_arguments_invalid")
    root = _new_directory(root)
    digest = hashlib.sha256()
    manifest_bytes = 0
    total_bytes = 0
    epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    note = "# 合成课程\n\n" + "这段公开合成文字只用于历史读取基准。\n" * 80
    transcript = json.dumps({"language": "zh", "source": "subtitle_import", "segments": [
        {"start": 0, "end": 5, "text": "合成开场"},
        {"start": 10, "end": 15, "text": "合成讲解"},
        {"start": 20, "end": 25, "text": "合成尾段"},
    ]}, ensure_ascii=False)
    for index in range(size):
        task_id = f"g5-{index:06d}"
        directory = root / task_id
        directory.mkdir()
        created = (epoch + timedelta(seconds=index // 3)).isoformat()
        output = "transcript" if index % 5 == 2 else "note"
        status = ("completed", "completed", "completed", "failed", "cancelled")[index % 5]
        manifest = {
            "task_id": task_id, "created_at": created, "output": output,
            "title": f"合成课程 {'编程' if index % 4 == 0 else '学习'} {index:06d}",
            "origin": "agent" if index % 10 == 2 else "web", "source": "local",
            "subtitle_import": output == "transcript", "uploaded_filename": "synthetic.srt",
            "favorite": index % 7 == 1 and output == "note" and status == "completed",
            "note_template_snapshot": {"id": "builtin-general-structured", "name": "通用结构化笔记",
                                       "instructions": "仅基于合成材料整理，不补充外部内容。" * 35,
                                       "layout": "# {{title}}\n\n{{content}}", "version": 1, "built_in": True},
            "runtime": {"status": status, "created_at": created, "finished_at": created,
                        "elapsed_seconds": 3, "progress": 100 if status == "completed" else 50,
                        "logs": ["合成阶段完成"] * 5},
        }
        contents = {"task.json": json.dumps(manifest, ensure_ascii=False, indent=2), "transcript.json": transcript}
        if output == "note" and status == "completed":
            contents["notes.md"] = note
        for name, text in contents.items():
            encoded = text.encode("utf-8")
            with (directory / name).open("xb") as stream:
                stream.write(encoded)
            digest.update(task_id.encode("ascii") + b"\0" + name.encode("ascii") + b"\0" + encoded)
            total_bytes += len(encoded)
            if name == "task.json":
                manifest_bytes += len(encoded)
    return {"task_count": size, "dataset_sha256": digest.hexdigest(),
            "manifest_bytes": manifest_bytes, "file_content_bytes": total_bytes}


@contextmanager
def count_reads(root: Path):
    """Successful Python Path.open read handles, not stat calls or physical IO."""
    counts = {"manifests": 0, "notes": 0, "transcripts": 0, "other": 0}
    original = Path.open
    names = {"task.json": "manifests", "notes.md": "notes", "transcript.json": "transcripts"}
    root = Path(os.path.abspath(root))

    def counted(path, mode="r", *args, **kwargs):
        if "r" in mode or "+" in mode:
            if root not in Path(os.path.abspath(path)).parents:
                raise RuntimeError("benchmark_access_denied")
            handle = original(path, mode, *args, **kwargs)
            counts[names.get(path.name, "other")] += 1
            return handle
        raise RuntimeError("benchmark_write_denied")

    with patch.object(Path, "open", counted):
        yield counts


def _timed(call):
    started = time.perf_counter()
    result = call()
    return result, round((time.perf_counter() - started) * 1000, 3)


def _python_peak(call) -> int:
    if tracemalloc.is_tracing():
        raise ValueError("benchmark_trace_already_active")
    tracemalloc.start()
    try:
        call()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _signature(result) -> str:
    return hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()


def run_query(backend, **options):
    # The current async route has no await: execute the real handler to return,
    # without creating Windows asyncio's loopback self-pipe or any HTTP socket.
    # Fail explicitly if a future handler begins suspending.
    coroutine = backend.list_recent_tasks(**options)
    try:
        try:
            coroutine.send(None)
        except StopIteration as completed:
            return completed.value
        raise RuntimeError("benchmark_handler_requires_event_loop")
    finally:
        coroutine.close()


def measure_dataset(backend, root: Path, size: int, repeats: int = 7) -> dict:
    if type(repeats) is not int or not 2 <= repeats <= 31:
        raise ValueError("benchmark_arguments_invalid")
    queries = {}
    with patch.object(backend, "WORKSPACE_DIR", root.resolve()), patch.object(backend, "tasks", {}):
        _, startup_ms = _timed(backend.restore_tasks_from_workspace)
        restored = len(backend.tasks)
        for name, config in QUERY_CASES.items():
            options = {"offset": 0, "limit": 20, **config}
            call = lambda: run_query(backend, **options)
            first, first_ms = _timed(call)
            signature = _signature(first)
            raw = []
            for _ in range(repeats):
                current, elapsed = _timed(call)
                if _signature(current) != signature:
                    raise RuntimeError("benchmark_response_changed")
                raw.append(elapsed)
            with count_reads(root) as reads:
                counted_result = call()
            if _signature(counted_result) != signature:
                raise RuntimeError("benchmark_response_changed")
            queries[name] = {"first_ms": first_ms, "raw_ms": raw,
                             "p50_ms": percentile(raw, 50), "p95_ms": percentile(raw, 95),
                             "reads": reads, "total_matches": first["total"], "page_items": len(first["tasks"]),
                             "response_sha256": signature}
        # Separate profiled runs; never include instrumentation in raw_ms.
        call_all = lambda: run_query(backend, offset=0, limit=20)
        query_peak = _python_peak(call_all)
        with patch.object(backend, "tasks", {}):
            with count_reads(root) as startup_reads:
                backend.restore_tasks_from_workspace()
        with patch.object(backend, "tasks", {}):
            startup_peak = _python_peak(backend.restore_tasks_from_workspace)
        return {"task_count": size, "warm_repeats": repeats,
                "preload_limit": backend.TASK_HISTORY_LIMIT,
                "startup": {"restore_ms": startup_ms, "restored_tasks": restored,
                            "reads": startup_reads, "python_traced_peak_bytes": startup_peak},
                "all_query_python_traced_peak_bytes": query_peak, "queries": queries}


@contextmanager
def count_metadata(root: Path):
    """Python Path method entries, including nested stat/lstat, not OS syscalls."""
    counts = {name: 0 for name in ("stat", "lstat", "resolve", "iterdir")}
    originals = {name: getattr(Path, name) for name in counts}
    def wrapper(name):
        def counted(path, *args, **kwargs):
            lexical = Path(os.path.abspath(path))
            if lexical == root or root in lexical.parents:
                counts[name] += 1
            return originals[name](path, *args, **kwargs)
        return counted
    from contextlib import ExitStack
    with ExitStack() as stack:
        for name in counts:
            stack.enter_context(patch.object(Path, name, wrapper(name)))
        yield counts


def measure_cache_dataset(backend, root: Path, size: int, repeats: int = 7) -> dict:
    """Paired modes on identical terminal inputs; real TTL, no timing instrumentation."""
    from backend import history_cache
    if type(repeats) is not int or not 2 <= repeats <= 31:
        raise ValueError("benchmark_arguments_invalid")
    queries = {}
    root = root.resolve()
    with patch.object(backend, "WORKSPACE_DIR", root), patch.object(backend, "tasks", {}):
        backend.restore_tasks_from_workspace()
        for name, config in QUERY_CASES.items():
            options = {"offset": 0, "limit": 20, **config}
            modes = {}
            signature = None
            for mode in ("direct", "cache_empty", "hit", "refresh", "invalidated", "capacity"):
                capacity = max(1, size // 4) if mode == "capacity" else history_cache.DEFAULT_MAX_ENTRIES
                cache = history_cache.HistorySummaryCache(max_entries=capacity)
                reader = backend._history_task_record if mode == "direct" else backend._cached_history_task_record
                with (patch.object(history_cache, "history_summaries", cache),
                      patch.object(backend, "_list_history_task_record", reader)):
                    call = lambda: run_query(backend, refresh=mode == "refresh", **options)
                    def prepare():
                        cache.clear()
                        if mode in {"hit", "refresh", "invalidated", "capacity"}:
                            run_query(backend, **options)
                        if mode == "invalidated":
                            # Real replace + invalidation, unchanged content/response.
                            backend.task_repository.update(root / "g5-000000" / "task.json", lambda value: None)
                    samples = []
                    for _ in range(repeats):
                        prepare()
                        before = asdict(cache.info())
                        started = time.monotonic()
                        result, elapsed = _timed(call)
                        ended = time.monotonic()
                        after = asdict(cache.info())
                        current_signature = _signature(result)
                        if signature is None:
                            signature = current_signature
                        if current_signature != signature:
                            raise RuntimeError("benchmark_response_changed")
                        delta = {key: after[key] - before[key] for key in ("hits", "misses", "evictions")}
                        samples.append({"ms": elapsed, "monotonic_start": started, "monotonic_end": ended,
                                        "cache_delta": delta,
                                        "pure_hit": mode == "hit" and delta["misses"] == 0 and delta["hits"] == size})
                    prepare()
                    before = asdict(cache.info())
                    with count_reads(root) as reads, count_metadata(root) as metadata:
                        counted = call()
                    if _signature(counted) != signature:
                        raise RuntimeError("benchmark_response_changed")
                    io_delta = {key: asdict(cache.info())[key] - before[key] for key in ("hits", "misses", "evictions")}
                    peak = _python_peak(lambda: (prepare(), call()))
                    raw = [sample["ms"] for sample in samples]
                    modes[mode] = {"samples": samples, "p50_ms": percentile(raw, 50), "p95_ms": percentile(raw, 95),
                                   "response_sha256": signature, "reads": reads, "metadata_calls": metadata,
                                   "io_cache_delta": io_delta, "cache": asdict(cache.info()),
                                   "capacity_entries": capacity, "prepare_and_query_python_peak_bytes": peak}
                print(json.dumps({"event": "cache_mode_complete", "task_count": size, "query": name,
                                  "mode": mode, "p95_ms": modes[mode]["p95_ms"]}), flush=True)
            queries[name] = modes
    return {"task_count": size, "warm_repeats": repeats, "ttl_seconds": history_cache.DEFAULT_TTL_SECONDS,
            "max_bytes": history_cache.DEFAULT_MAX_BYTES, "max_entry_bytes": history_cache.DEFAULT_MAX_ENTRY_BYTES,
            "queries": queries}


def load_isolated_backend(root: Path):
    if "backend.main" in sys.modules:
        raise ValueError("benchmark_backend_already_loaded")
    bootstrap = _new_directory(root / "bootstrap")
    # Do not inspect .env or the user's workspace/config/cache on import.
    overrides = {"VIDEO2KNOWLEDGE_WORKSPACE": str(bootstrap), "VIDEOTONOTES_WORKSPACE": str(bootstrap),
                 "WHISPER_CACHE_DIR": str(bootstrap / "_model_cache"), "TASK_HISTORY_LIMIT": "100"}
    with patch.dict(os.environ, overrides), patch("dotenv.load_dotenv", return_value=False):
        backend, elapsed = _timed(lambda: importlib.import_module("backend.main"))
    return backend, elapsed


@contextmanager
def offline_guard():
    def forbidden(*args, **kwargs):
        raise RuntimeError("benchmark_external_call_blocked")
    class ForbiddenPopen(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            forbidden()
    # yt-dlp subclasses Popen during import, so retain a class-shaped guard.
    with patch.object(socket, "create_connection", forbidden), patch.object(socket.socket, "connect", forbidden), patch.object(subprocess, "Popen", ForbiddenPopen):
        yield


def main(argv=None) -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", choices=(100, 1000, 10000), default=[100, 1000, 10000])
    parser.add_argument("--repeats", type=int, choices=range(2, 32), default=7)
    parser.add_argument("--cache", action="store_true", help="Measure six explicitly labeled G5.1 cache modes")
    args = parser.parse_args(argv)
    try:
        if len(set(args.sizes)) != len(args.sizes):
            raise ValueError("benchmark_arguments_invalid")
        if "backend.main" in sys.modules:
            raise ValueError("benchmark_backend_already_loaded")
        root = _new_directory(args.output_dir)
        with offline_guard():
            backend, import_ms = load_isolated_backend(root)
            results = []
            for size in args.sizes:
                print(json.dumps({"event": "dataset_start", "task_count": size}), flush=True)
                dataset = root / f"tasks-{size}"
                identity = create_dataset(dataset, size)
                result = (measure_cache_dataset if args.cache else measure_dataset)(backend, dataset, size, args.repeats)
                results.append({**identity, **result})
                print(json.dumps({"event": "dataset_complete", "task_count": size,
                                  "all_p95_ms": result["queries"]["all"]["hit"]["p95_ms"] if args.cache else result["queries"]["all"]["p95_ms"]}), flush=True)
                if args.cache and size == 1000:
                    paired = result["queries"]["all"]
                    if paired["hit"]["p95_ms"] >= paired["direct"]["p95_ms"]:
                        print(json.dumps({"event": "larger_sizes_stopped", "reason": "no_1000_task_hit_benefit"}), flush=True)
                        break
            repo = Path(__file__).absolute().parents[1]
            report = {"schema_version": 2 if args.cache else 1, "environment": environment_snapshot(),
                      "cache_mode": "six_paired_modes" if args.cache else "production_direct",
                      "requested_sizes": args.sizes,
                      "cache_sha256": hashlib.sha256((repo / "backend/history_cache.py").read_bytes()).hexdigest(),
                      "backend_main_sha256": hashlib.sha256((repo / "backend/main.py").read_bytes()).hexdigest(),
                      "repository_sha256": hashlib.sha256((repo / "backend/task_repository.py").read_bytes()).hexdigest(),
                      "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "measurement": "direct_handler_no_http_no_os_cache_eviction",
                      "memory": "separate_python_tracemalloc_not_rss",
                      "reads": "separate_successful_path_open_not_stat_or_physical_io",
                      "empty_backend_import_ms": import_ms, "results": results}
            write_report(report, root / "report.json")
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        code = str(exc) if str(exc) in {"benchmark_output_unavailable", "benchmark_arguments_invalid", "benchmark_backend_already_loaded"} else "benchmark_failed"
        write_report({"passed": False, "error_code": code})
        return 1


if __name__ == "__main__":
    sys.exit(main())
