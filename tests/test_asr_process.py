"""Packaged ASR worker protocol tests (protocol v1).

All workers are python -c fakes: no native ASR, no model, no real media.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from backend import asr_process, main
from backend.transcript import TranscriptSegment


def _setup_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "workspace"
    task_dir = workspace / "task-1"
    task_dir.mkdir(parents=True)
    media = task_dir / "input.mp3"
    media.write_bytes(b"not-really-audio")
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", str(workspace))
    return workspace, task_dir, media


def _fake_child(script: str):
    return lambda: [sys.executable, "-c", script]


OK_SCRIPT = """
import json, sys
job = json.loads(sys.stdin.readline())
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print(json.dumps({"protocol": 1, "event": "progress", "done": 1.0, "total": 2.0}), flush=True)
print(json.dumps({"protocol": 1, "event": "done", "result": {
    "segments": [{"start": 0.0, "end": 1.5, "text": "你好 😀"},
                 {"start": 1.5, "end": 2.0, "text": job["model_name"]}],
    "language": "zh", "device": "cpu", "model": "base", "requested_model": "base",
    "duration": 2.0, "transcribe_seconds": 0.1,
}}), flush=True)
"""

CRASH_SCRIPT = "import os; os._exit(-1073741819)"

ERROR_SCRIPT = (
    "import json,sys; sys.stdin.readline();"
    "print(json.dumps({'protocol':1,'event':'started'}), flush=True);"
    "print(json.dumps({'protocol':1,'event':'error','code':'worker_error',"
    "'message':'RuntimeError: 模型文件损坏'}), flush=True)"
)

CANCEL_SCRIPT = """
import json, pathlib, sys
job = json.loads(sys.stdin.readline())
marker = pathlib.Path(job["media_path"]).parent / "cancel-seen.txt"
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
for line in sys.stdin:
    event = json.loads(line or "{}")
    if event.get("cmd") == "cancel":
        marker.write_text(json.dumps(event), encoding="utf-8")
        if event.get("protocol") != 1:
            print(json.dumps({"protocol": 1, "event": "error",
                              "code": "protocol_error",
                              "message": "cancel protocol missing"}), flush=True)
            sys.exit(4)
        print(json.dumps({"protocol": 1, "event": "cancelled"}), flush=True)
        break
"""

IGNORE_CANCEL_SCRIPT = """
import json, sys, time
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
time.sleep(30)
"""

HANG_AFTER_DONE_SCRIPT = """
import json, sys, time
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print(json.dumps({"protocol": 1, "event": "done", "result": {
    "segments": [{"start": 0.0, "end": 1.0, "text": "ok"}],
    "language": "zh", "device": "cpu", "model": "base", "requested_model": "base",
    "duration": 1.0,
}}), flush=True)
time.sleep(30)
"""

EOF_WITHOUT_TERMINAL_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
"""

MALFORMED_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print("{not json", flush=True)
"""

UNKNOWN_EVENT_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print(json.dumps({"protocol": 1, "event": "wat"}), flush=True)
"""

REVERSED_DONE_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print(json.dumps({"protocol": 1, "event": "done", "result": {
    "segments": [{"start": 5.0, "end": 1.0, "text": "bad"}],
    "language": "zh", "device": "cpu", "model": "base", "requested_model": "base",
    "duration": 1.0,
}}), flush=True)
"""

NO_START_SCRIPT = "import time; time.sleep(30)"

NOISE_THEN_OK_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print("native library banner", flush=True)
print(json.dumps({"protocol": 1, "event": "done", "result": {
    "segments": [{"start": 0.0, "end": 1.0, "text": "ok"}],
    "language": "zh", "device": "cpu", "model": "base", "requested_model": "base",
    "duration": 1.0,
}}), flush=True)
"""

TOO_MUCH_NOISE_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
for _ in range(20):
    print("native library banner", flush=True)
"""

NEGATIVE_PROGRESS_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print(json.dumps({"protocol": 1, "event": "progress", "done": -1, "total": 2}), flush=True)
"""

BAD_ERROR_CODE_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print(json.dumps({"protocol": 1, "event": "error", "code": "RuntimeError",
                  "message": "boom"}), flush=True)
"""

BAD_ERROR_MESSAGE_SCRIPT = """
import json, sys
sys.stdin.readline()
print(json.dumps({"protocol": 1, "event": "started"}), flush=True)
print(json.dumps({"protocol": 1, "event": "error", "code": "worker_error",
                  "message": 1}), flush=True)
"""


@pytest.mark.asyncio
async def test_run_in_child_streams_progress_and_decodes_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "child_command", _fake_child(OK_SCRIPT))
    seen: list[tuple[float, float]] = []

    result = await asr_process.run_in_child(
        media, "belle-turbo-zh", False, "某个视频", None,
        lambda done, total: seen.append((done, total)),
    )

    assert seen == [(1.0, 2.0)]
    assert result["model"] == "base"
    assert result["segments"] == [
        TranscriptSegment(0.0, 1.5, "你好 😀"),
        TranscriptSegment(1.5, 2.0, "belle-turbo-zh"),
    ]


@pytest.mark.asyncio
async def test_worker_error_event_becomes_worker_died(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "child_command", _fake_child(ERROR_SCRIPT))
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "模型文件损坏" in str(raised.value)
    assert "程序本身仍在运行" in str(raised.value)


@pytest.mark.asyncio
async def test_native_crash_uses_platform_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "child_command", _fake_child(CRASH_SCRIPT))
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    expected_code = 0xC0000005 if sys.platform == "win32" else 5
    assert asr_process.format_exit_code(expected_code) in str(raised.value)


@pytest.mark.asyncio
async def test_eof_without_terminal_reports_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        asr_process, "child_command", _fake_child(EOF_WITHOUT_TERMINAL_SCRIPT)
    )
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "退出码 0" in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "script, needle",
    [
        (MALFORMED_SCRIPT, "JSON"),
        (UNKNOWN_EVENT_SCRIPT, "未知事件"),
        (REVERSED_DONE_SCRIPT, "时间"),
    ],
)
async def test_bad_protocol_events_fail_only_the_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str, needle: str
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "child_command", _fake_child(script))
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "协议错误" in str(raised.value)
    assert needle in str(raised.value)


@pytest.mark.asyncio
async def test_small_stdout_noise_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        asr_process, "child_command", _fake_child(NOISE_THEN_OK_SCRIPT)
    )
    result = await asr_process.run_in_child(media, "small", False, "标题")
    assert result["segments"] == [TranscriptSegment(0.0, 1.0, "ok")]


@pytest.mark.asyncio
async def test_excess_stdout_noise_is_a_protocol_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        asr_process, "child_command", _fake_child(TOO_MUCH_NOISE_SCRIPT)
    )
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "噪音" in str(raised.value)


@pytest.mark.asyncio
async def test_negative_progress_is_a_protocol_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        asr_process, "child_command", _fake_child(NEGATIVE_PROGRESS_SCRIPT)
    )
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "进度" in str(raised.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "script", [BAD_ERROR_CODE_SCRIPT, BAD_ERROR_MESSAGE_SCRIPT]
)
async def test_invalid_error_events_are_protocol_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "child_command", _fake_child(script))
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "错误事件" in str(raised.value)


@pytest.mark.asyncio
async def test_oversized_event_is_a_protocol_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "MAX_EVENT_BYTES", 256)
    script = (
        "import json,sys; sys.stdin.readline();"
        "print(json.dumps({'protocol':1,'event':'started'}), flush=True);"
        "print('x'*2000, flush=True)"
    )
    monkeypatch.setattr(asr_process, "child_command", _fake_child(script))
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "协议错误" in str(raised.value)


@pytest.mark.asyncio
async def test_invalid_utf8_is_a_protocol_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    script = (
        "import json,sys; sys.stdin.readline();"
        "print(json.dumps({'protocol':1,'event':'started'}), flush=True);"
        "sys.stdout.buffer.write(b'{\\xff\\n'); sys.stdout.buffer.flush()"
    )
    monkeypatch.setattr(asr_process, "child_command", _fake_child(script))
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "UTF-8" in str(raised.value) or "协议错误" in str(raised.value)


@pytest.mark.asyncio
async def test_cancel_event_sends_cancel_and_raises_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "child_command", _fake_child(CANCEL_SCRIPT))
    cancel_event = threading.Event()
    cancel_event.set()
    with pytest.raises(asyncio.CancelledError):
        await asr_process.run_in_child(media, "small", False, "标题", cancel_event)
    received = json.loads(
        (task_dir / "cancel-seen.txt").read_text(encoding="utf-8")
    )
    assert received == {"protocol": 1, "cmd": "cancel"}


@pytest.mark.asyncio
async def test_parent_cancellation_sends_cancel_and_reaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "child_command", _fake_child(CANCEL_SCRIPT))
    task = asyncio.create_task(asr_process.run_in_child(media, "small", False, "标题"))
    for _ in range(100):
        if (task_dir / "cancel-seen.txt").exists():
            break
        await asyncio.sleep(0.02)
        if task.done():
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (task_dir / "cancel-seen.txt").is_file()


@pytest.mark.asyncio
async def test_ignored_cancel_is_killed_after_short_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "CANCEL_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(
        asr_process, "child_command", _fake_child(IGNORE_CANCEL_SCRIPT)
    )
    cancel_event = threading.Event()
    cancel_event.set()
    start = time.monotonic()
    with pytest.raises(asyncio.CancelledError):
        await asr_process.run_in_child(media, "small", False, "标题", cancel_event)
    assert time.monotonic() - start < 5


@pytest.mark.asyncio
async def test_terminal_done_still_kills_a_hanging_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "TERMINAL_EXIT_GRACE_SECONDS", 0.2)
    monkeypatch.setattr(
        asr_process, "child_command", _fake_child(HANG_AFTER_DONE_SCRIPT)
    )
    start = time.monotonic()
    result = await asr_process.run_in_child(media, "small", False, "标题")
    assert time.monotonic() - start < 5
    assert result["segments"] == [TranscriptSegment(0.0, 1.0, "ok")]


@pytest.mark.asyncio
async def test_start_handshake_timeout_fails_the_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, _task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(asr_process, "START_HANDSHAKE_SECONDS", 0.2)
    monkeypatch.setattr(asr_process, "child_command", _fake_child(NO_START_SCRIPT))
    with pytest.raises(asr_process.TranscriptionWorkerDied) as raised:
        await asr_process.run_in_child(media, "small", False, "标题")
    assert "启动" in str(raised.value)


def test_encode_decode_round_trip_and_strict_validation() -> None:
    payload = asr_process.encode_result(
        {"segments": [TranscriptSegment(1.0, 2.0, "字 😀")], "device": "cpu"}
    )
    assert payload["segments"] == [{"start": 1.0, "end": 2.0, "text": "字 😀"}]
    decoded = asr_process.decode_result(
        {
            **payload,
            "language": "zh",
            "device": "cpu",
            "model": "base",
            "requested_model": "base",
            "duration": 2.0,
        }
    )
    assert decoded["segments"] == [TranscriptSegment(1.0, 2.0, "字 😀")]

    for bad in (
        {"segments": "nope"},
        {"segments": [{"start": "0", "end": 1, "text": "x"}], "language": "zh",
         "device": "cpu", "model": "m", "requested_model": "m", "duration": 1},
        {"segments": [{"start": True, "end": 1, "text": "x"}], "language": "zh",
         "device": "cpu", "model": "m", "requested_model": "m", "duration": 1},
        {"segments": [{"start": 2, "end": 1, "text": "x"}], "language": "zh",
         "device": "cpu", "model": "m", "requested_model": "m", "duration": 1},
        {"segments": [], "language": "zh", "device": "cpu", "model": "m",
         "requested_model": "m", "duration": float("inf")},
        {"segments": [{"start": 0, "end": 1, "text": 1}], "language": "zh",
         "device": "cpu", "model": "m", "requested_model": "m", "duration": 1},
    ):
        with pytest.raises(ValueError):
            asr_process.decode_result(bad)


def _valid_job(**overrides):
    job = {
        "protocol": 1,
        "cmd": "transcribe",
        "task_id": "task-1",
        "media_path": "C:/x/input.mp3",
        "model_name": "base",
        "use_gpu": False,
        "title": None,
    }
    job.update(overrides)
    return job


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"use_gpu": "false"}, "use_gpu"),
        ({"use_gpu": 1}, "use_gpu"),
        ({"use_gpu": None}, "use_gpu"),
        ({"title": 123}, "title"),
        ({"model_name": "not-a-model"}, "模型"),
        ({"protocol": 2}, "协议"),
        ({"cmd": "other"}, "协议"),
        ({"task_id": 1}, "字段"),
    ],
)
def test_parse_job_rejects_invalid_fields(overrides: dict, needle: str) -> None:
    with pytest.raises(asr_process._InvalidJob) as raised:
        asr_process._parse_job(json.dumps(_valid_job(**overrides)))
    assert needle in str(raised.value)


def test_parse_job_accepts_valid_fields() -> None:
    job = asr_process._parse_job(json.dumps(_valid_job()))
    assert job["use_gpu"] is False
    assert job["title"] is None
    assert job["model_name"] == "base"


def test_child_command_and_frozen_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"D:\x\app.exe")
    assert asr_process.child_command() == [r"D:\x\app.exe", "--asr-child"]
    assert asr_process.use_child_process() is True

    monkeypatch.delattr(sys, "frozen", raising=False)
    assert asr_process.child_command() == [sys.executable, "-m", "backend.asr_process"]
    assert asr_process.use_child_process() is False


def test_format_exit_code() -> None:
    assert asr_process.format_exit_code(3221225477) == "0xC0000005"
    assert asr_process.format_exit_code(-11) == "0xFFFFFFF5"
    assert asr_process.format_exit_code(1) == "1"
    assert asr_process.format_exit_code(None) == "未知"


def test_creationflags_only_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asr_process.sys, "platform", "win32")
    assert asr_process._creationflags() == int(
        getattr(asr_process.subprocess, "CREATE_NO_WINDOW", 0)
    )
    monkeypatch.setattr(asr_process.sys, "platform", "linux")
    assert asr_process._creationflags() == 0


def test_stderr_is_inherited_or_devnull_never_piped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stderr", None)
    assert asr_process._stderr_target() == asyncio.subprocess.DEVNULL
    assert asr_process._stderr_target() != asyncio.subprocess.PIPE


def test_validate_media_accepts_only_safe_owned_task_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    resolved, task_id = asr_process._validate_media(media)
    assert resolved == media.resolve()
    assert task_id == "task-1"

    old = workspace / "old-task"
    old.mkdir()
    old_media = old / "audio.m4a"
    old_media.write_bytes(b"x")
    assert asr_process._validate_media(old_media)[1] == "old-task"

    outside = tmp_path / "outside"
    outside.mkdir()
    outside_media = outside / "input.mp3"
    outside_media.write_bytes(b"x")
    with pytest.raises(ValueError):
        asr_process._validate_media(outside_media)

    nested = task_dir / "nested" / "input.mp3"
    nested.parent.mkdir()
    nested.write_bytes(b"x")
    with pytest.raises(ValueError):
        asr_process._validate_media(nested)

    bad_id = workspace / "bad id"
    bad_id.mkdir()
    bad_media = bad_id / "input.mp3"
    bad_media.write_bytes(b"x")
    with pytest.raises(ValueError):
        asr_process._validate_media(bad_media)

    with pytest.raises(ValueError):
        asr_process._validate_media(task_dir / "missing.mp3")

    directory_media = task_dir / "input.wav"
    directory_media.mkdir()
    with pytest.raises(ValueError):
        asr_process._validate_media(directory_media)

    with pytest.raises(ValueError):
        asr_process._validate_media(task_dir / "input.mp3", expected_task_id="other")

    unowned = task_dir / "notes.mp3"
    unowned.write_bytes(b"x")
    with pytest.raises(ValueError):
        asr_process._validate_media(unowned)


def test_validate_media_rejects_symlinked_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace, task_dir, media = _setup_workspace(tmp_path, monkeypatch)
    link = task_dir / "input.wav"
    try:
        os.symlink(media, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted on this host")
    with pytest.raises(ValueError):
        asr_process._validate_media(link)


def test_use_utf8_pipes_reconfigures_existing_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp936"))
    asr_process.use_utf8_pipes()
    asr_process._emit({"event": "done", "text": "中文😀\ufffd\ud800"})
    payload = json.loads(raw.getvalue().decode("utf-8"))
    assert payload["protocol"] == 1
    assert payload["text"] == "中文😀\ufffd\ud800"


def test_emit_replaces_unencodable_isolated_surrogates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="utf-8", errors="strict")
    monkeypatch.setattr(sys, "stdout", stream)
    asr_process.use_utf8_pipes()
    asr_process._emit({"event": "done", "text": "孤立\ud800代理"})
    assert raw.getvalue().decode("utf-8")


@pytest.mark.asyncio
async def test_run_transcription_routes_frozen_to_child_and_source_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    async def fake_child(*args, **kwargs):
        calls.append("child")
        return {"segments": []}

    async def fake_local(*args, **kwargs):
        calls.append("local")
        return {"segments": []}

    monkeypatch.setattr(main.asr_process, "run_in_child", fake_child)
    monkeypatch.setattr(main, "run_transcription_local", fake_local)

    monkeypatch.setattr(main.asr_process, "use_child_process", lambda: True)
    await main.run_transcription(tmp_path / "a.mp3", "base", False, "标题", None)
    monkeypatch.setattr(main.asr_process, "use_child_process", lambda: False)
    await main.run_transcription(tmp_path / "a.mp3", "paraformer-zh", True, "标题", None)

    assert calls == ["child", "local"]
