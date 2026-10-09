"""Opt-in cleanup of failed/cancelled task media; task state is never changed."""
from __future__ import annotations

import json
import logging
import os
import re
import stat
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ALLOWED_RETENTION_DAYS = {1, 7, 30}
_OWNED_MEDIA_RE = re.compile(r"^(input|audio|preview|audio_p[0-9]+)\..+$")
_TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

logger = logging.getLogger(__name__)

# 面向客户端的 warning 固定脱敏：细节只进 logger（阶段、安全 task_id、异常类型、
# errno/winerror 数字），不含路径、不含 str(exc)。
WARNING_MEDIA_DELETE = "任务媒体未能安全清理，已保留"
WARNING_TASK_SKIPPED = "任务清单或目录不可用，已跳过"
WARNING_ROOT_UNAVAILABLE = "任务根目录不可用或身份不可靠，未执行清理"


def is_safe_task_id(name: Any) -> bool:
    """任务目录名是否为可安全引用的 task_id（与清理扫描同一约束）。"""
    return isinstance(name, str) and _TASK_ID_RE.fullmatch(name) is not None


def _log_retention_failure(stage: str, task_id: str | None, exc: BaseException) -> None:
    """只记录阶段、安全 task_id、异常类型与 errno/winerror 数字。"""
    logger.warning(
        "media-retention stage=%s task=%s error=%s errno=%s winerror=%s",
        stage,
        task_id if is_safe_task_id(task_id) else "-",
        type(exc).__name__,
        getattr(exc, "errno", None),
        getattr(exc, "winerror", None),
    )


def is_owned_media_name(name: str) -> bool:
    match = _OWNED_MEDIA_RE.fullmatch(name)
    if not match:
        return False
    stem = match.group(1)
    return bool(stem[len("audio_p"):].strip("0")) if stem.startswith("audio_p") else True


def validate_retention_days(days: Any) -> int:
    if type(days) is not int or days not in ALLOWED_RETENTION_DAYS:
        raise ValueError("保留天数只允许 1、7、30")
    return days


def _parse_finished_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _snapshot(path: Path, *, directory: bool = False) -> os.stat_result:
    info = path.stat(follow_symlinks=False)
    kind_ok = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    # Reparse points include Junctions even when is_symlink() is false.
    if not kind_ok or getattr(info, "st_file_attributes", 0) & 0x400 or not info.st_ino:
        raise OSError("无法确认路径身份")
    if not directory and info.st_nlink != 1:
        raise OSError("保留多重链接文件")
    return info


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return bool(left.st_ino) and (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _open_fd(path: Path, *, directory: bool = False, delete: bool = False) -> int:
    if os.name != "nt":
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        if directory:
            flags |= getattr(os, "O_DIRECTORY", 0)
        return os.open(path, flags)
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    access = 0x80 if directory else 0x80000000  # attributes / GENERIC_READ
    if delete:
        access |= 0x10000  # DELETE
    flags = 0x00200000 | (0x02000000 if directory else 0)  # OPEN_REPARSE_POINT / BACKUP_SEMANTICS
    # Exclude FILE_SHARE_DELETE: locked files/directories cannot be replaced.
    handle = create(str(path), access, 3, None, 3, flags, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        close = kernel.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close(handle)
        raise


@contextmanager
def _locked_path(path: Path, expected: os.stat_result, *, directory: bool = False,
                 delete: bool = False):
    fd = _open_fd(path, directory=directory, delete=delete)
    try:
        opened = os.fstat(fd)
        current = _snapshot(path, directory=directory)
        if not _same_identity(expected, opened) or not _same_identity(opened, current):
            raise OSError("路径已被替换")
        if not directory and opened.st_nlink != 1:
            raise OSError("保留多重链接文件")
        yield fd
    finally:
        os.close(fd)


def _delete_opened(path: Path, fd: int) -> None:
    if os.name != "nt":
        # A pathname unlink after stat cannot atomically verify the target inode.
        # Keep media on unsupported hosts instead of weakening the deletion contract.
        raise OSError("当前平台不支持原子身份删除，保留媒体")
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = [("DeleteFile", wintypes.BOOLEAN)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    dispose = kernel.SetFileInformationByHandle
    dispose.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    dispose.restype = wintypes.BOOL
    info = FileDispositionInfo(1)
    if not dispose(msvcrt.get_osfhandle(fd), 4, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    # Close completes deletion of the verified handle, not a fresh name lookup.


def _read_manifest_fd(fd: int, info: os.stat_result) -> dict[str, Any] | None:
    """从已持有并校验过身份的句柄读取 manifest，不按路径重新查找。"""
    if info.st_size > 4 * 1024 * 1024:
        return None
    os.lseek(fd, 0, os.SEEK_SET)
    remaining = info.st_size
    chunks: list[bytes] = []
    while remaining > 0:
        chunk = os.read(fd, min(remaining, 65536))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    try:
        manifest = json.loads(b"".join(chunks).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return manifest if isinstance(manifest, dict) else None


def cleanup_expired_task_media(tasks_root: Path, *, days: int, active_task_ids: set[str],
                               now: datetime | None = None) -> dict[str, Any]:
    """Scan direct children using persisted terminal status and aware finished_at.

    Existing layout: WORKSPACE_DIR/<task_id>, shared with task_directory() and
    restore_tasks_from_workspace(); do not introduce a new tasks layer.
    """
    days = validate_retention_days(days)
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    summary: dict[str, Any] = {
        "scanned": 0, "eligible": 0, "removed_count": 0, "removed": [], "warnings": [],
    }
    try:
        root = tasks_root.absolute()
        for ancestor in (root, *root.parents):
            _snapshot(ancestor, directory=True)
        expected_root = _snapshot(root, directory=True)
        with _locked_path(root, expected_root, directory=True):
            for child in sorted(root.iterdir(), key=lambda path: path.name):
                if not _TASK_ID_RE.fullmatch(child.name):
                    continue
                try:
                    expected_dir = _snapshot(child, directory=True)
                    # The workspace also contains notes/model/template directories.
                    # Only direct children with a safe task manifest are task candidates.
                    expected_manifest = _snapshot(child / "task.json")
                except OSError:
                    continue
                summary["scanned"] += 1
                task_id = child.name
                if task_id in active_task_ids:
                    continue
                try:
                    with _locked_path(child, expected_dir, directory=True):
                        # 持锁验证并全程持有 task.json 句柄：Windows 上该句柄不共享
                        # FILE_SHARE_DELETE，重试任务无法在最终检查后把它 replace 成
                        # non-terminal 状态，删除期间清单保持已确认的终态。
                        with _locked_path(child / "task.json", expected_manifest) as manifest_fd:
                            manifest = _read_manifest_fd(manifest_fd, expected_manifest)
                            if not manifest or manifest.get("task_id") != task_id:
                                continue
                            runtime = manifest.get("runtime")
                            if not isinstance(runtime, dict) or runtime.get("status") not in {"failed", "cancelled"}:
                                continue
                            finished_at = _parse_finished_at(runtime.get("finished_at"))
                            if finished_at is None or finished_at >= cutoff:
                                continue
                            summary["eligible"] += 1
                            for member in sorted(child.iterdir(), key=lambda path: path.name):
                                if not is_owned_media_name(member.name):
                                    continue
                                try:
                                    expected = _snapshot(member)
                                    with _locked_path(member, expected, delete=True) as fd:
                                        if not _same_identity(expected_dir, _snapshot(child, directory=True)):
                                            raise OSError("任务目录已被替换")
                                        if _read_manifest_fd(manifest_fd, expected_manifest) != manifest:
                                            raise OSError("任务清单已改变")
                                        if not _same_identity(expected, _snapshot(member)):
                                            raise OSError("媒体已被替换")
                                        _delete_opened(member, fd)
                                    summary["removed"].append(f"{task_id}/{member.name}")
                                    summary["removed_count"] += 1
                                except (OSError, ValueError, TypeError) as exc:
                                    _log_retention_failure("delete-media", task_id, exc)
                                    summary["warnings"].append(WARNING_MEDIA_DELETE)
                except (OSError, ValueError, TypeError) as exc:
                    _log_retention_failure("scan-task", task_id, exc)
                    summary["warnings"].append(WARNING_TASK_SKIPPED)
    except OSError as exc:
        _log_retention_failure("scan-root", None, exc)
        summary["warnings"].append(WARNING_ROOT_UNAVAILABLE)
    return summary
