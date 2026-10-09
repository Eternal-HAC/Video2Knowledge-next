"""失败/取消任务媒体的可选按天清理：纯磁盘合同测试。

不启动服务、不联网；所有操作只发生在 tmp_path 下的假任务目录。
默认永久保留由「未选择有限天数时前端不发起请求」+ 白名单校验共同保证。
"""
from __future__ import annotations

import errno
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.media_retention import cleanup_expired_task_media
from backend.media_retention import WARNING_MEDIA_DELETE
from backend import media_retention
from retention_support import IS_WINDOWS, assert_media_removed, assert_removed_count

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


def make_task(
    root: Path,
    task_id: str,
    *,
    status: str,
    finished_at: str | None,
    files: dict[str, str] | None = None,
) -> Path:
    directory = root / task_id
    directory.mkdir(parents=True)
    manifest = {"task_id": task_id, "runtime": {"status": status, "finished_at": finished_at}}
    (directory / "task.json").write_text(json.dumps(manifest), encoding="utf-8")
    for name, content in (files or {}).items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return directory


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def test_days_whitelist_rejects_invalid_values(tmp_path: Path) -> None:
    for bad in (0, -1, 2, 8, 999, "7", None, True):
        with pytest.raises(ValueError):
            cleanup_expired_task_media(tmp_path, days=bad, active_task_ids=set(), now=NOW)


def test_failed_task_older_than_cutoff_is_cleaned(tmp_path: Path) -> None:
    directory = make_task(
        tmp_path, "t-old-failed", status="failed", finished_at=iso(10),
        files={"audio.m4a": "x", "notes.md": "n", "transcript.md": "t"},
    )
    result = cleanup_expired_task_media(tmp_path, days=7, active_task_ids=set(), now=NOW)
    assert_media_removed(directory / "audio.m4a")
    assert (directory / "notes.md").exists()
    assert (directory / "transcript.md").exists()
    assert (directory / "task.json").exists()
    assert result["scanned"] == 1
    assert result["eligible"] == 1
    assert_removed_count(result, windows=1)
    if IS_WINDOWS:
        assert result["warnings"] == []


def test_exactly_at_cutoff_is_kept(tmp_path: Path) -> None:
    directory = make_task(
        tmp_path, "t-edge", status="failed", finished_at=iso(7),
        files={"audio.m4a": "x"},
    )
    result = cleanup_expired_task_media(tmp_path, days=7, active_task_ids=set(), now=NOW)
    assert (directory / "audio.m4a").exists(), "边界时刻必须保留（严格 older-than）"
    assert result["eligible"] == 0


def test_cancelled_task_is_cleaned(tmp_path: Path) -> None:
    directory = make_task(
        tmp_path, "t-cancelled", status="cancelled", finished_at=iso(30),
        files={"preview.mp4": "x"},
    )
    cleanup_expired_task_media(tmp_path, days=7, active_task_ids=set(), now=NOW)
    assert_media_removed(directory / "preview.mp4")


def test_non_terminal_and_uploaded_statuses_are_skipped(tmp_path: Path) -> None:
    for status in ("completed", "uploaded", "processing", "pending", "queued", "cancelling"):
        directory = make_task(
            tmp_path, f"t-{status}", status=status, finished_at=iso(30),
            files={"audio.m4a": "x"},
        )
        assert (directory / "audio.m4a").exists()
    result = cleanup_expired_task_media(tmp_path, days=7, active_task_ids=set(), now=NOW)
    assert result["eligible"] == 0
    for status in ("completed", "uploaded", "processing", "pending", "queued", "cancelling"):
        assert (tmp_path / f"t-{status}" / "audio.m4a").exists()


def test_active_task_is_never_touched(tmp_path: Path) -> None:
    directory = make_task(
        tmp_path, "t-active", status="failed", finished_at=iso(30),
        files={"audio.m4a": "x"},
    )
    result = cleanup_expired_task_media(tmp_path, days=7, active_task_ids={"t-active"}, now=NOW)
    assert (directory / "audio.m4a").exists()
    assert result["eligible"] == 0


def test_owned_names_sidecars_and_retained_files(tmp_path: Path) -> None:
    owned = {
        "input.mp4": "x", "audio.m4a": "x", "audio_p1.m4a": "x", "audio_p12.m4a": "x",
        "preview.mp4": "x", "audio.m4a.part": "x", "audio.m4a.ytdl": "x",
    }
    retained = {
        "audio_p0.m4a": "x", "audio_p-1.m4a": "x", "notes.md": "x",
        "transcript.md": "x", "unknown.bin": "x",
    }
    directory = make_task(
        tmp_path, "t-names", status="failed", finished_at=iso(30), files={**owned, **retained},
    )
    (directory / "frames").mkdir(exist_ok=True)
    (directory / "frames" / "f1.jpg").write_text("x", encoding="utf-8")
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    for name in owned:
        assert_media_removed(directory / name, f"应删除：{name}")
    for name in retained:
        assert (directory / name).exists(), f"应保留：{name}"
    assert (directory / "task.json").exists()
    assert (directory / "frames" / "f1.jpg").exists()
    assert_removed_count(result, windows=len(owned))


def test_symlink_media_is_kept_with_warning(tmp_path: Path) -> None:
    directory = make_task(
        tmp_path, "t-link", status="failed", finished_at=iso(30), files={"real.m4a": "x"},
    )
    link = directory / "audio.m4a"
    try:
        os.symlink(directory / "real.m4a", link)
    except (OSError, NotImplementedError):
        pytest.skip("当前平台不允许创建符号链接")
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert link.exists(), "符号链接必须 fail closed 保留"
    assert (directory / "real.m4a").exists()
    assert result["warnings"], "必须记录 warning"


def test_missing_or_corrupt_manifest_is_skipped(tmp_path: Path) -> None:
    bare = tmp_path / "t-nomanifest"
    bare.mkdir()
    (bare / "audio.m4a").write_text("x", encoding="utf-8")
    corrupt = tmp_path / "t-corrupt"
    corrupt.mkdir()
    (corrupt / "task.json").write_text("{not json", encoding="utf-8")
    (corrupt / "audio.m4a").write_text("x", encoding="utf-8")
    nofinish = make_task(
        tmp_path, "t-nofinish", status="failed", finished_at=None, files={"audio.m4a": "x"},
    )
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert (bare / "audio.m4a").exists()
    assert (corrupt / "audio.m4a").exists()
    assert (nofinish / "audio.m4a").exists()
    assert result["eligible"] == 0


def test_single_file_failure_degrades_to_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = make_task(
        tmp_path, "t-fragile", status="failed", finished_at=iso(30),
        files={"audio.m4a": "x", "input.mp4": "x"},
    )
    original_delete = media_retention._delete_opened

    def flaky_delete(path: Path, fd: int):
        if path.name == "audio.m4a":
            raise OSError("simulated lock")
        return original_delete(path, fd)

    monkeypatch.setattr(media_retention, "_delete_opened", flaky_delete)
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert (directory / "audio.m4a").exists(), "失败文件保留"
    assert result["warnings"], "必须降级为 warning 而不是中止"
    if IS_WINDOWS:
        assert not (directory / "input.mp4").exists(), "其他文件照常删除"
        assert result["removed_count"] == 1
    else:
        assert (directory / "input.mp4").exists(), "非 Windows 平台整体保守保留"
        assert result["removed_count"] == 0


def test_non_directory_and_symlinked_task_dirs_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "loose-file.txt").write_text("x", encoding="utf-8")
    real = make_task(tmp_path, "t-real", status="failed", finished_at=iso(30), files={"audio.m4a": "x"})
    linked = tmp_path / "t-linked"
    try:
        os.symlink(real, linked, target_is_directory=True)
    except (OSError, NotImplementedError):
        linked = None
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert_media_removed(real / "audio.m4a", "真实任务目录正常清理")
    if linked is not None:
        assert result["scanned"] == 1, "目录符号链接不计入扫描"


def test_hard_link_media_is_kept(tmp_path: Path) -> None:
    directory = make_task(tmp_path, "t-hard", status="failed", finished_at=iso(30))
    foreign = tmp_path / "foreign.bin"
    foreign.write_bytes(b"foreign")
    os.link(foreign, directory / "audio.m4a")
    result = cleanup_expired_task_media(tmp_path, days=7, active_task_ids=set(), now=NOW)
    assert (directory / "audio.m4a").exists()
    assert foreign.read_bytes() == b"foreign"
    assert result["removed_count"] == 0
    assert result["warnings"]


def test_replacement_before_open_is_kept(tmp_path: Path, monkeypatch) -> None:
    directory = make_task(tmp_path, "t-race", status="failed", finished_at=iso(30),
                          files={"audio.m4a": "owned"})
    original = media_retention._open_fd
    replaced = False

    def replace_then_open(path, *, directory=False, delete=False):
        nonlocal replaced
        if path.name == "audio.m4a" and not replaced:
            path.rename(path.with_name("retained-old.bin"))
            path.write_text("replacement", encoding="utf-8")
            replaced = True
        return original(path, directory=directory, delete=delete)

    monkeypatch.setattr(media_retention, "_open_fd", replace_then_open)
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert replaced
    assert (directory / "audio.m4a").read_text(encoding="utf-8") == "replacement"
    assert result["removed_count"] == 0
    assert result["warnings"]


@pytest.mark.parametrize("finished", ["2020-01-01T00:00:00", "invalid", 0, "9999-01-01T00:00:00+00:00"])
def test_unreliable_or_future_time_is_kept(tmp_path: Path, finished) -> None:
    directory = make_task(tmp_path, "t-time", status="failed", finished_at=finished,
                          files={"audio.m4a": "x"})
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert (directory / "audio.m4a").exists()
    assert result["eligible"] == 0


@pytest.mark.parametrize("days", [1, 7, 30])
def test_allowed_policy_and_no_recursive_scan(tmp_path: Path, days) -> None:
    directory = make_task(tmp_path, "t-direct", status="cancelled", finished_at=iso(days + 1),
                          files={"audio.m4a": "x"})
    nested = make_task(directory, "nested", status="failed", finished_at=iso(99),
                       files={"audio.m4a": "keep"})
    result = cleanup_expired_task_media(tmp_path, days=days, active_task_ids=set(), now=NOW)
    assert_media_removed(directory / "audio.m4a")
    assert (nested / "audio.m4a").exists()
    assert result["scanned"] == 1


def test_manifest_change_before_delete_is_kept(tmp_path, monkeypatch) -> None:
    directory = make_task(tmp_path, "t-state-race", status="failed", finished_at=iso(30),
                          files={"audio.m4a": "keep"})
    original = media_retention._open_fd

    def start_processing(path, *, directory=False, delete=False):
        if path.name == "audio.m4a":
            manifest = path.parent / "task.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["runtime"]["status"] = "processing"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
        return original(path, directory=directory, delete=delete)

    monkeypatch.setattr(media_retention, "_open_fd", start_processing)
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert (directory / "audio.m4a").exists()
    assert result["removed_count"] == 0
    assert result["warnings"]


@pytest.mark.skipif(os.name != "nt", reason="Windows handle locking contract")
def test_windows_locked_media_and_directory_cannot_be_replaced(tmp_path, monkeypatch) -> None:
    directory = make_task(tmp_path, "t-locked", status="failed", finished_at=iso(30),
                          files={"audio.m4a": "owned"})
    original = media_retention._delete_opened
    attempted = []

    def attempt_replacement(path, fd):
        for target in (path, path.parent):
            with pytest.raises(OSError):
                target.rename(target.with_name(target.name + "-replacement"))
            attempted.append(target.name)
        return original(path, fd)

    monkeypatch.setattr(media_retention, "_delete_opened", attempt_replacement)
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert attempted == ["audio.m4a", "t-locked"]
    assert result["removed_count"] == 1
    assert not (directory / "audio.m4a").exists()


def test_directory_replacement_before_lock_is_kept(tmp_path, monkeypatch) -> None:
    directory = make_task(tmp_path, "t-dir-race", status="failed", finished_at=iso(30),
                          files={"audio.m4a": "original"})
    original = media_retention._open_fd

    def swap_directory(path, *, directory=False, delete=False):
        if path.name == "t-dir-race":
            path.rename(path.with_name("old-dir"))
            make_task(path.parent, path.name, status="failed", finished_at=iso(30),
                      files={"audio.m4a": "replacement"})
        return original(path, directory=directory, delete=delete)

    monkeypatch.setattr(media_retention, "_open_fd", swap_directory)
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert (directory / "audio.m4a").read_text(encoding="utf-8") == "replacement"
    assert (tmp_path / "old-dir" / "audio.m4a").exists()
    assert result["removed_count"] == 0


def test_hard_link_manifest_and_mismatched_task_id_are_skipped(tmp_path) -> None:
    first = make_task(tmp_path, "t-first", status="failed", finished_at=iso(30),
                      files={"audio.m4a": "keep"})
    second = tmp_path / "t-second"
    second.mkdir()
    os.link(first / "task.json", second / "task.json")
    (second / "audio.m4a").write_bytes(b"keep")
    mismatch = make_task(tmp_path, "t-wrong", status="failed", finished_at=iso(30),
                         files={"audio.m4a": "keep"})
    manifest = mismatch / "task.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["task_id"] = "someone-else"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert result["removed_count"] == 0
    for path in (first, second, mismatch):
        assert (path / "audio.m4a").exists()


def test_unsupported_atomic_deletion_preserves_media(tmp_path, monkeypatch) -> None:
    path = tmp_path / "audio.m4a"
    path.write_bytes(b"keep")
    with path.open("rb") as handle:
        with monkeypatch.context() as patch:
            patch.setattr(media_retention.os, "name", "posix")
            with pytest.raises(OSError, match="原子身份删除"):
                media_retention._delete_opened(path, handle.fileno())
    assert path.read_bytes() == b"keep"


def test_workspace_non_task_directories_are_not_counted(tmp_path) -> None:
    for name in ("notes", "_model_cache", "note_templates"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "audio.m4a").write_bytes(b"keep")
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert result["scanned"] == 0
    assert result["removed_count"] == 0
    assert result["warnings"] == []


@pytest.mark.skipif(os.name != "nt", reason="Windows handle locking contract")
def test_windows_manifest_cannot_be_replaced_while_deleting(tmp_path, monkeypatch) -> None:
    """删除窗口内把 task.json replace 成 processing 必须被持锁句柄挡住。"""
    directory = make_task(
        tmp_path, "t-manifest-race", status="failed", finished_at=iso(30),
        files={"audio.m4a": "owned"},
    )
    manifest = directory / "task.json"
    original = media_retention._delete_opened
    replace_outcomes: list[str] = []

    def attempt_replace(path, fd):
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["runtime"]["status"] = "processing"
        staged = manifest.with_name("task.json.staged")
        staged.write_text(json.dumps(payload), encoding="utf-8")
        try:
            os.replace(staged, manifest)
            replace_outcomes.append("replaced")
        except OSError:
            replace_outcomes.append("blocked")
        return original(path, fd)

    monkeypatch.setattr(media_retention, "_delete_opened", attempt_replace)
    result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert replace_outcomes == ["blocked"], "持锁期间 task.json 必须不可替换"
    assert result["removed_count"] == 1
    assert not (directory / "audio.m4a").exists()
    assert json.loads(manifest.read_text(encoding="utf-8"))["runtime"]["status"] == "failed"


def test_retention_failures_log_stage_task_and_errno_without_paths(
    tmp_path, monkeypatch, caplog
) -> None:
    directory = make_task(
        tmp_path, "t-log", status="failed", finished_at=iso(30), files={"audio.m4a": "x"}
    )

    def failing_delete(path, fd):
        raise OSError(errno.EACCES, "raw exception text")

    monkeypatch.setattr(media_retention, "_delete_opened", failing_delete)
    with caplog.at_level(logging.WARNING, logger="backend.media_retention"):
        result = cleanup_expired_task_media(tmp_path, days=1, active_task_ids=set(), now=NOW)
    assert result["warnings"] == [WARNING_MEDIA_DELETE]
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "delete-media" in messages, "必须记录失败阶段"
    assert "t-log" in messages, "必须记录安全 task_id"
    assert "error=PermissionError" in messages, "必须记录异常类型"
    assert str(int(errno.EACCES)) in messages, "必须记录 errno 数字"
    assert "raw exception text" not in messages, "不得记录 str(exc)"
    assert str(tmp_path) not in messages, "不得记录绝对路径"
    assert str(directory) not in messages, "不得记录绝对路径"
