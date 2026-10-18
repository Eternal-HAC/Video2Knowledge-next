"""Packaged-mode ASR worker process (protocol v1, UTF-8 NDJSON).

faster-whisper (CTranslate2) and sherpa-onnx are native libraries. In a packaged
build they can terminate the whole process; running them in a child keeps the
API, tray and other queued tasks alive. Source checkouts keep transcribing
in-process.

Parent -> child, first line:
    {"protocol":1,"cmd":"transcribe","task_id":...,"media_path":...,
     "model_name":...,"use_gpu":...,"title":...}
Later lines: {"cmd":"cancel"}

Child -> parent, one JSON object per line:
    {"protocol":1,"event":"started"}
    {"protocol":1,"event":"progress","done":N,"total":N}
    {"protocol":1,"event":"done","result":{...}}
    {"protocol":1,"event":"cancelled"}
    {"protocol":1,"event":"error","code":...,"message":...}
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from .media_retention import is_owned_media_name, is_safe_task_id
from .transcript import TranscriptSegment

PROTOCOL_VERSION = 1
# Parent-initiated cancellation: how long to wait for the worker before killing it.
CANCEL_GRACE_SECONDS = 60.0
# After a terminal event (done/error/cancelled) the worker should exit promptly.
TERMINAL_EXIT_GRACE_SECONDS = 5.0
# A worker that never sends "started" is broken; do not wait forever.
START_HANDSHAKE_SECONDS = 10.0
MAX_EVENT_BYTES = 64 * 1024 * 1024
# A few native libraries occasionally print a banner to stdout. Ignore a small,
# fixed number of non-JSON lines; more than this is a broken protocol.
MAX_STDOUT_NOISE_LINES = 16

_REPARSE_POINT = 0x400


class TranscriptionWorkerDied(RuntimeError):
    """The worker crashed, reported a protocol error, or exited without a result."""


def child_command() -> list[str]:
    """Frozen builds reuse the executable; source checkouts run this module."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--asr-child"]
    return [sys.executable, "-m", "backend.asr_process"]


def use_child_process() -> bool:
    return bool(getattr(sys, "frozen", False))


def _creationflags() -> int:
    if sys.platform == "win32":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def format_exit_code(code: int | None) -> str:
    """Render NTSTATUS-style exit codes as 32-bit hex."""
    if code is None:
        return "未知"
    if code < 0 or code >= 0xC0000000:
        return f"0x{code & 0xFFFFFFFF:08X}"
    return str(code)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_finite(value: Any) -> bool:
    return _is_number(value) and math.isfinite(float(value))


def encode_result(result: dict[str, Any]) -> dict[str, Any]:
    """Convert TranscriptSegment objects to plain dicts without coercing other values."""
    if not isinstance(result, dict):
        raise ValueError("result 不是对象")
    data = dict(result)
    segments = result.get("segments")
    if segments is None:
        segments = []
    if not isinstance(segments, (list, tuple)):
        raise ValueError("segments 不是数组")
    encoded: list[dict[str, Any]] = []
    for segment in segments:
        if isinstance(segment, TranscriptSegment):
            encoded.append(segment.to_dict())
        elif isinstance(segment, dict):
            encoded.append(dict(segment))
        else:
            raise ValueError("segment 类型非法")
    data["segments"] = encoded
    return data


def decode_result(payload: Any) -> dict[str, Any]:
    """Validate a done payload strictly; never coerce types."""
    if not isinstance(payload, dict):
        raise ValueError("result 不是对象")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise ValueError("segments 不是数组")
    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            raise ValueError("segment 不是对象")
        start = item.get("start")
        end = item.get("end")
        text = item.get("text")
        if not _is_finite(start) or not _is_finite(end):
            raise ValueError("segment 时间不是有限数字")
        if start < 0 or end < start:
            raise ValueError("segment 时间顺序非法")
        if not isinstance(text, str):
            raise ValueError("segment 文本不是字符串")
        segments.append(TranscriptSegment(float(start), float(end), text))

    result: dict[str, Any] = {"segments": segments}
    for key in ("language", "device", "model", "requested_model"):
        value = payload.get(key)
        if not isinstance(value, str):
            raise ValueError(f"{key} 不是字符串")
        result[key] = value

    duration = payload.get("duration")
    if not _is_finite(duration) or duration < 0:
        raise ValueError("duration 不是非负有限数字")
    result["duration"] = float(duration)

    text = payload.get("text")
    if text is not None:
        if not isinstance(text, str):
            raise ValueError("text 不是字符串")
        result["text"] = text
    for key in (
        "language_probability",
        "duration_after_vad",
        "model_load_seconds",
        "transcribe_seconds",
    ):
        value = payload.get(key)
        if value is None:
            continue
        if not _is_finite(value) or value < 0:
            raise ValueError(f"{key} 不是非负有限数字")
        result[key] = float(value)
    note = payload.get("fallback_note")
    if note is not None:
        if not isinstance(note, str):
            raise ValueError("fallback_note 不是字符串")
        result["fallback_note"] = note
    return result


def _workspace_root() -> Path | None:
    raw = os.environ.get("VIDEOTONOTES_WORKSPACE")
    if not raw:
        return None
    try:
        return Path(raw).resolve(strict=True)
    except OSError:
        return None


def _validate_media(
    media_path: Path, expected_task_id: str | None = None
) -> tuple[Path, str]:
    """Validate a media file belongs to a direct, safe task directory.

    The path is resolved and then re-checked with a non-following stat. Symlinks,
    junctions, hard links, nested paths and unowned names are rejected. A TOCTOU
    window remains between this check and the worker opening the file; the child
    repeats the same checks.
    """
    root = _workspace_root()
    if root is None:
        raise ValueError("工作区未配置")
    original = Path(media_path)
    try:
        link_info = original.lstat()
    except OSError:
        raise ValueError("媒体文件不存在") from None
    if stat.S_ISLNK(link_info.st_mode) or (
        getattr(link_info, "st_file_attributes", 0) & _REPARSE_POINT
    ):
        raise ValueError("媒体是链接")
    try:
        path = original.resolve(strict=True)
        info = path.stat(follow_symlinks=False)
    except OSError:
        raise ValueError("媒体文件不存在") from None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("媒体不是普通文件")
    if getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
        raise ValueError("媒体是链接")
    if info.st_nlink != 1:
        raise ValueError("媒体有多重链接")
    parent = path.parent
    if parent.parent != root:
        raise ValueError("媒体不在任务目录")
    task_id = parent.name
    if not is_safe_task_id(task_id):
        raise ValueError("任务标识非法")
    if expected_task_id is not None and task_id != expected_task_id:
        raise ValueError("任务标识不一致")
    if not is_owned_media_name(path.name):
        raise ValueError("媒体文件名不合规")
    return path, task_id


def _stderr_target() -> Any:
    """Inherit a real log stream; otherwise use DEVNULL. Never PIPE."""
    stream = getattr(sys, "stderr", None)
    if stream is None:
        return asyncio.subprocess.DEVNULL
    try:
        stream.fileno()
    except (AttributeError, OSError, ValueError):
        return asyncio.subprocess.DEVNULL
    return None


async def _pump(reader: asyncio.StreamReader, events: asyncio.Queue) -> None:
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            if len(line) > MAX_EVENT_BYTES:
                await events.put(("protocol", "事件超过大小上限"))
                break
            await events.put(("line", line))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await events.put(("protocol", f"读取工人输出失败（{type(exc).__name__}）"))
    finally:
        await events.put(("eof", None))


def _parse_event(line: bytes | str) -> dict[str, Any]:
    if isinstance(line, bytes):
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("工人输出不是 UTF-8") from None
    else:
        text = line
    if not text.strip():
        raise ValueError("工人输出了空行")
    try:
        event = json.loads(text)
    except ValueError:
        raise ValueError("工人输出不是 JSON") from None
    if not isinstance(event, dict):
        raise ValueError("工人事件不是对象")
    if event.get("protocol") != PROTOCOL_VERSION:
        raise ValueError("工人协议版本不匹配")
    return event


async def _send_cancel(writer: Any, state: dict[str, bool]) -> None:
    if state.get("sent"):
        return
    state["sent"] = True
    try:
        writer.write(b'{"protocol":1,"cmd":"cancel"}\n')
        await writer.drain()
    except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
        return


async def _watch_cancel(
    process: asyncio.subprocess.Process,
    writer: Any,
    cancel_event: Any,
    state: dict[str, bool],
) -> None:
    if cancel_event is None:
        return
    while process.returncode is None:
        if cancel_event.is_set():
            state["requested"] = True
            await _send_cancel(writer, state)
            try:
                await asyncio.wait_for(process.wait(), timeout=CANCEL_GRACE_SECONDS)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            return
        await asyncio.sleep(0.5)


async def _close_writer(writer: Any) -> None:
    if writer is None:
        return
    close = getattr(writer, "close", None)
    if close is not None:
        try:
            close()
        except Exception:
            pass
    wait_closed = getattr(writer, "wait_closed", None)
    if wait_closed is not None:
        try:
            await wait_closed()
        except Exception:
            pass


async def _shutdown(
    process: asyncio.subprocess.Process,
    writer: Any,
    pump_task: asyncio.Task | None,
    cancel_state: dict[str, bool],
    *,
    request_cancel: bool,
    grace: float,
) -> int | None:
    if request_cancel and process.returncode is None:
        await _send_cancel(writer, cancel_state)
    if process.returncode is None:
        try:
            await asyncio.wait_for(process.wait(), timeout=grace)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
    await _close_writer(writer)
    if pump_task is not None:
        pump_task.cancel()
        await asyncio.gather(pump_task, return_exceptions=True)
    return process.returncode


async def _shielded_cleanup(
    process: asyncio.subprocess.Process,
    writer: Any,
    pump_task: asyncio.Task | None,
    watch_task: asyncio.Task | None,
    cancel_state: dict[str, bool],
    *,
    request_cancel: bool,
    grace: float,
) -> None:
    """Run shutdown to completion even if the caller is being cancelled."""
    if watch_task is not None:
        watch_task.cancel()
        await asyncio.gather(watch_task, return_exceptions=True)

    async def cleanup() -> None:
        try:
            await _shutdown(
                process,
                writer,
                pump_task,
                cancel_state,
                request_cancel=request_cancel,
                grace=grace,
            )
        except Exception:
            pass

    task = asyncio.create_task(cleanup())
    while True:
        try:
            await asyncio.shield(task)
            return
        except asyncio.CancelledError:
            if task.done():
                return
            continue


async def _consume(
    process: asyncio.subprocess.Process,
    writer: Any,
    events: asyncio.Queue,
    cancel_state: dict[str, bool],
    pump_task: asyncio.Task,
    watch_task: asyncio.Task | None,
    progress_callback: Callable[[float, float], None] | None,
) -> dict[str, Any]:
    payload: Any = None
    failure: str | None = None
    failure_code = "worker_error"
    cancelled = False
    protocol_error: str | None = None
    started = False
    noise_lines = 0
    loop = asyncio.get_running_loop()
    deadline = loop.time() + START_HANDSHAKE_SECONDS
    try:
        while True:
            if not started:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    protocol_error = "转写工人未在启动时限内响应"
                    break
                try:
                    kind, value = await asyncio.wait_for(events.get(), remaining)
                except asyncio.TimeoutError:
                    protocol_error = "转写工人未在启动时限内响应"
                    break
            else:
                kind, value = await events.get()
            if kind == "eof":
                break
            if kind == "protocol":
                protocol_error = str(value)
                break
            raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
            stripped = raw.strip()
            if not stripped:
                continue
            if not stripped.startswith(b"{"):
                noise_lines += 1
                if noise_lines > MAX_STDOUT_NOISE_LINES:
                    protocol_error = (
                        f"工人 stdout 噪音超过 {MAX_STDOUT_NOISE_LINES} 行"
                    )
                    break
                continue
            try:
                event = _parse_event(raw)
            except ValueError as exc:
                protocol_error = str(exc)
                break
            name = event.get("event")
            if name == "started":
                if started:
                    protocol_error = "重复的启动信号"
                    break
                started = True
                continue
            if name == "error":
                code = event.get("code")
                message = event.get("message")
                if code not in {"worker_error", "invalid_job", "protocol_error"}:
                    protocol_error = "错误事件 code 非法"
                    break
                if not isinstance(message, str) or not message:
                    protocol_error = "错误事件 message 非法"
                    break
                failure = message
                failure_code = code
                break
            if not started:
                protocol_error = "转写工人在启动信号前发送了事件"
                break
            if name == "progress":
                done = event.get("done")
                total = event.get("total")
                if (
                    not _is_finite(done)
                    or not _is_finite(total)
                    or done < 0
                    or total < 0
                ):
                    protocol_error = "进度事件格式错误"
                    break
                if progress_callback:
                    progress_callback(float(done), float(total))
            elif name == "done":
                payload = event.get("result")
                break
            elif name == "cancelled":
                cancelled = True
                break
            else:
                protocol_error = "未知事件类型"
                break
    finally:
        if watch_task is not None:
            watch_task.cancel()
            await asyncio.gather(watch_task, return_exceptions=True)

    exit_code = await _shutdown(
        process,
        writer,
        pump_task,
        cancel_state,
        request_cancel=(cancelled or protocol_error is not None),
        grace=TERMINAL_EXIT_GRACE_SECONDS,
    )

    if cancelled or cancel_state.get("requested"):
        raise asyncio.CancelledError("转写已取消")
    if payload is not None:
        try:
            return decode_result(payload)
        except ValueError as exc:
            raise TranscriptionWorkerDied(
                f"语音转写进程协议错误（{exc}）；本次任务已停止，程序本身仍在运行，"
                "可换一个转写档位重试"
            ) from None
    if protocol_error is not None:
        raise TranscriptionWorkerDied(
            f"语音转写进程协议错误（{protocol_error}）；本次任务已停止，程序本身仍在运行，"
            "可换一个转写档位重试"
        )
    if failure is not None:
        raise TranscriptionWorkerDied(
            f"语音转写进程报告失败（{failure_code}: {failure}）；"
            "本次任务已停止，程序本身仍在运行，"
            "可换一个转写档位重试"
        )
    raise TranscriptionWorkerDied(
        f"语音转写进程异常退出（退出码 {format_exit_code(exit_code)}）；"
        "本次任务已停止，程序本身仍在运行，可换一个转写档位重试"
    )


async def run_in_child(
    media_path: Path,
    model_name: str,
    use_gpu: bool,
    title: str | None,
    cancel_event: Any = None,
    progress_callback: Callable[[float, float], None] | None = None,
) -> dict[str, Any]:
    """Run one transcription job in a child process and return the decoded result."""
    try:
        path, task_id = _validate_media(Path(media_path))
    except ValueError as exc:
        raise TranscriptionWorkerDied(
            f"转写任务参数不安全（{exc}）；本次任务已停止，程序本身仍在运行"
        ) from None

    job = {
        "protocol": PROTOCOL_VERSION,
        "cmd": "transcribe",
        "task_id": task_id,
        "media_path": str(path),
        "model_name": model_name,
        "use_gpu": bool(use_gpu),
        "title": title,
    }
    kwargs: dict[str, Any] = {
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": _stderr_target(),
        "limit": MAX_EVENT_BYTES,
    }
    flags = _creationflags()
    if flags:
        kwargs["creationflags"] = flags
    try:
        process = await asyncio.create_subprocess_exec(*child_command(), **kwargs)
    except OSError as exc:
        raise TranscriptionWorkerDied(
            f"无法启动语音转写进程（{type(exc).__name__}）；本次任务已停止，程序本身仍在运行"
        ) from None

    writer = process.stdin
    events: asyncio.Queue = asyncio.Queue()
    cancel_state: dict[str, bool] = {"sent": False}
    pump_task: asyncio.Task | None = None
    watch_task: asyncio.Task | None = None
    try:
        assert writer is not None and process.stdout is not None
        writer.write(
            (json.dumps(job, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        )
        await writer.drain()
        pump_task = asyncio.create_task(_pump(process.stdout, events))
        watch_task = asyncio.create_task(
            _watch_cancel(process, writer, cancel_event, cancel_state)
        )
        return await _consume(
            process, writer, events, cancel_state, pump_task, watch_task, progress_callback
        )
    except asyncio.CancelledError:
        await _shielded_cleanup(
            process,
            writer,
            pump_task,
            watch_task,
            cancel_state,
            request_cancel=True,
            grace=CANCEL_GRACE_SECONDS,
        )
        raise
    except Exception:
        await _shielded_cleanup(
            process,
            writer,
            pump_task,
            watch_task,
            cancel_state,
            request_cancel=True,
            grace=TERMINAL_EXIT_GRACE_SECONDS,
        )
        raise


# --------------------------------------------------------------------------
# Worker side
# --------------------------------------------------------------------------

_write_lock = threading.Lock()


def _emit(payload: dict[str, Any]) -> None:
    if sys.stdout is None:
        use_utf8_pipes()
    event = dict(payload)
    event.setdefault("protocol", PROTOCOL_VERSION)
    line = json.dumps(event, ensure_ascii=False, allow_nan=False)
    with _write_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def use_utf8_pipes() -> None:
    """Pin stdin/stdout to UTF-8, including noconsole handles and lone surrogates."""
    for name, fd, mode in (("stdin", 0, "r"), ("stdout", 1, "w")):
        stream = getattr(sys, name, None)
        if stream is None:
            if mode == "w":
                stream = open(
                    fd,
                    "w",
                    encoding="utf-8",
                    buffering=1,
                    closefd=False,
                    errors="backslashreplace",
                )
                reconfigure = getattr(stream, "reconfigure", None)
                if reconfigure is not None:
                    reconfigure(
                        encoding="utf-8",
                        errors="backslashreplace",
                        line_buffering=True,
                        write_through=True,
                    )
            else:
                stream = open(fd, "r", encoding="utf-8", closefd=False)
            setattr(sys, name, stream)
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if mode == "w":
                reconfigure(
                    encoding="utf-8",
                    errors="backslashreplace",
                    line_buffering=True,
                    write_through=True,
                )
            else:
                reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            continue


def _watch_stdin_cancel(flag: threading.Event) -> None:
    try:
        for line in sys.stdin:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if (
                isinstance(event, dict)
                and event.get("protocol") == PROTOCOL_VERSION
                and event.get("cmd") == "cancel"
            ):
                flag.set()
                return
    except (OSError, ValueError):
        return


def _invalid_job(reason: str) -> int:
    _emit({"event": "error", "code": "invalid_job", "message": reason})
    return 2


class _InvalidJob(ValueError):
    """The first-line job failed validation."""


def _parse_job(job_line: str) -> dict[str, Any]:
    """Validate the worker job strictly; never coerce field types."""
    if not job_line.strip():
        raise _InvalidJob("没有收到任务")
    try:
        job = json.loads(job_line)
    except ValueError:
        raise _InvalidJob("任务描述无法解析") from None
    if (
        not isinstance(job, dict)
        or job.get("protocol") != PROTOCOL_VERSION
        or job.get("cmd") != "transcribe"
    ):
        raise _InvalidJob("任务协议不匹配")
    task_id = job.get("task_id")
    media_value = job.get("media_path")
    model_name = job.get("model_name")
    if (
        not isinstance(task_id, str)
        or not isinstance(media_value, str)
        or not isinstance(model_name, str)
    ):
        raise _InvalidJob("任务字段缺失")
    from .main import ASR_MODELS

    if model_name not in ASR_MODELS:
        raise _InvalidJob("模型名称不受支持")
    use_gpu = job.get("use_gpu")
    if type(use_gpu) is not bool:
        raise _InvalidJob("use_gpu 不是布尔值")
    title = job.get("title")
    if title is not None and not isinstance(title, str):
        raise _InvalidJob("title 不是字符串")
    return {
        "task_id": task_id,
        "media_path": media_value,
        "model_name": model_name,
        "use_gpu": use_gpu,
        "title": title,
    }


def child_main() -> int:
    """Read one job, run it in-process here, and stream protocol events back."""
    use_utf8_pipes()
    job_line = sys.stdin.readline()
    try:
        job = _parse_job(job_line)
    except _InvalidJob as exc:
        return _invalid_job(str(exc))
    task_id = job["task_id"]
    try:
        media_path, derived_task_id = _validate_media(
            Path(job["media_path"]), expected_task_id=task_id
        )
    except ValueError as exc:
        return _invalid_job(f"媒体路径不可用（{exc}）")
    if derived_task_id != task_id:
        return _invalid_job("任务标识不一致")

    _emit({"event": "started"})
    cancel_event = threading.Event()
    threading.Thread(
        target=_watch_stdin_cancel, args=(cancel_event,), daemon=True
    ).start()

    def report(done: float, total: float) -> None:
        _emit({"event": "progress", "done": done, "total": total})

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        from .main import run_transcription_local

        try:
            result = loop.run_until_complete(
                run_transcription_local(
                    media_path,
                    job["model_name"],
                    job["use_gpu"],
                    job["title"],
                    cancel_event,
                    report,
                )
            )
        except asyncio.CancelledError:
            _emit({"event": "cancelled"})
            return 3
        except Exception as exc:
            # Some transcriber implementations use their own cancellation type.
            try:
                from .whisper_asr import TranscriptionCancelledError
            except ImportError:
                TranscriptionCancelledError = ()  # type: ignore[assignment]
            if isinstance(exc, TranscriptionCancelledError):
                _emit({"event": "cancelled"})
                return 3
            _emit(
                {
                    "event": "error",
                    "code": "worker_error",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            return 1
        try:
            encoded = encode_result(result)
        except (TypeError, ValueError) as exc:
            _emit(
                {
                    "event": "error",
                    "code": "protocol_error",
                    "message": f"结果编码失败: {type(exc).__name__}",
                }
            )
            return 1
        _emit({"event": "done", "result": encoded})
        return 0
    finally:
        loop.close()


if __name__ == "__main__":
    raise SystemExit(child_main())
