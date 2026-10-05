"""Obsidian 检测与飞书发布的合同测试。

所有 lark-cli 调用都走 fake runner：测试绝不触发真实云端写入。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import note_integrations as ni


# ---------------------------------------------------------------------------
# Obsidian Vault 检测（只读）
# ---------------------------------------------------------------------------

def _write_obsidian_config(appdata: Path, payload: str) -> None:
    config_dir = appdata / "obsidian"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "obsidian.json").write_text(payload, encoding="utf-8")


def test_detect_obsidian_returns_valid_vaults_only(tmp_path: Path) -> None:
    vault_a = tmp_path / "VaultA"
    vault_a.mkdir()
    vault_b = tmp_path / "VaultB"
    vault_b.mkdir()
    appdata = tmp_path / "appdata"
    _write_obsidian_config(
        appdata,
        json.dumps(
            {
                "vaults": {
                    "aa": {"path": str(vault_a), "ts": 1, "open": True},
                    "bb": {"path": str(vault_b), "ts": 2},
                    "cc": {"path": str(tmp_path / "missing"), "ts": 3},   # 不存在
                    "dd": {"path": str(vault_a), "ts": 4},               # 重复
                    "ee": {"path": "relative/vault", "ts": 5},           # 相对路径
                    "ff": {"path": "", "ts": 6},                         # 空路径
                    "gg": "not-a-dict",                                  # 畸形条目
                }
            },
            ensure_ascii=False,
        ),
    )
    result = ni.detect_obsidian(env={"APPDATA": str(appdata)}, platform="win32")
    assert result["status"] == "ok"
    paths = [vault["path"] for vault in result["vaults"]]
    assert paths == [str(vault_a), str(vault_b)]
    first = result["vaults"][0]
    assert first["label"] == "VaultA"
    assert first["open"] is True
    assert first["suggested_destination"] == str(vault_a / "Video2Knowledge")
    assert result["vaults"][1]["open"] is False


def test_detect_obsidian_missing_config_is_not_an_error(tmp_path: Path) -> None:
    result = ni.detect_obsidian(env={"APPDATA": str(tmp_path)}, platform="win32")
    assert result == {"status": "missing", "vaults": []}


def test_detect_obsidian_corrupt_config_is_not_an_error(tmp_path: Path) -> None:
    appdata = tmp_path / "appdata"
    _write_obsidian_config(appdata, "{ not json")
    result = ni.detect_obsidian(env={"APPDATA": str(appdata)}, platform="win32")
    assert result == {"status": "corrupt", "vaults": []}


def test_detect_obsidian_non_windows_is_unsupported() -> None:
    result = ni.detect_obsidian(env={}, platform="darwin")
    assert result == {"status": "unsupported", "vaults": []}


# ---------------------------------------------------------------------------
# 飞书目标归一：只接受 folder token 或 /drive/folder/<token> 链接
# ---------------------------------------------------------------------------

def test_normalize_feishu_folder_accepts_token_and_folder_url() -> None:
    token = "ABCdef1234567890"
    assert ni.normalize_feishu_folder(token) == token
    assert ni.normalize_feishu_folder(f"https://example.feishu.cn/drive/folder/{token}") == token
    assert ni.normalize_feishu_folder(f"https://example.feishu.cn/drive/folder/{token}/") == token
    assert ni.normalize_feishu_folder(f"  {token}  ") == token


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "short",
        "has space in token",
        "token'quote",
        'token"double',
        "token;rm -rf",
        "https://example.feishu.cn/drive/folder/ABCdef1234567890?x=1",  # query string
        "https://example.feishu.cn/wiki/ABCdef1234567890",              # wiki 目标不支持
        "https://evil.example/ABCdef1234567890",                        # 非 folder 链接
        "../ABCdef1234567890",
    ],
)
def test_normalize_feishu_folder_rejects_unsafe_shapes(value: str) -> None:
    with pytest.raises(ni.FeishuInputError):
        ni.normalize_feishu_folder(value)


# ---------------------------------------------------------------------------
# lark-cli 就绪检测（fake runner，无真实进程）
# ---------------------------------------------------------------------------

def _fake_runner_factory(responses: list[dict]):
    calls: list[dict] = []

    def runner(argv, *, cwd=None, timeout=None):
        calls.append({"argv": list(argv), "cwd": cwd, "timeout": timeout})
        if not responses:
            raise AssertionError("unexpected extra CLI call")
        return responses.pop(0)

    return runner, calls


def _auth_payload(identity="user", status="ready", scopes=None) -> str:
    return json.dumps(
        {
            "ok": True,
            "data": {
                "identity": identity,
                "status": status,
                "scopes": scopes if scopes is not None else list(ni.REQUIRED_SCOPES),
            },
        }
    )


def test_readiness_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ni, "_resolve_cli", lambda: None)
    result = ni.check_feishu_readiness()
    assert result["installed"] is False
    assert result["capable"] is False
    assert result["auth"] == "missing"
    assert result["scopes_ready"] is False


def test_readiness_when_capabilities_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, _ = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": "usage: lark-cli im ...", "stderr": "", "timed_out": False},
            {"exit_code": 0, "stdout": _auth_payload(), "stderr": "", "timed_out": False},
        ]
    )
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.check_feishu_readiness()
    assert result["installed"] is True
    assert result["capable"] is False


def test_readiness_user_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, calls = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": "markdown drive im", "stderr": "", "timed_out": False},
            {"exit_code": 0, "stdout": _auth_payload(), "stderr": "", "timed_out": False},
        ]
    )
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.check_feishu_readiness()
    assert result == {
        "installed": True,
        "capable": True,
        "auth": "ready",
        "scopes_ready": True,
    }
    # auth 检查是只读命令，且不会把原始输出带出
    assert calls[1]["argv"][:2] == ["auth", "status"]
    # scope 明细不带出，只保留布尔就绪位
    assert "drive:file:upload" not in json.dumps(result)


@pytest.mark.parametrize(
    "payload, expected_auth",
    [
        (_auth_payload(status="expired"), "expired"),
        (_auth_payload(identity="bot"), "missing"),   # bot-only 绝不算就绪
        ("{ not json", "error"),
    ],
)
def test_readiness_auth_states(
    monkeypatch: pytest.MonkeyPatch, payload: str, expected_auth: str
) -> None:
    runner, _ = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": "markdown drive", "stderr": "", "timed_out": False},
            {"exit_code": 0, "stdout": payload, "stderr": "", "timed_out": False},
        ]
    )
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(ni, "_run_cli", runner)
    assert ni.check_feishu_readiness()["auth"] == expected_auth


def test_readiness_auth_timeout_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, _ = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": "markdown drive", "stderr": "", "timed_out": False},
            {"exit_code": None, "stdout": "", "stderr": "", "timed_out": True},
        ]
    )
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(ni, "_run_cli", runner)
    assert ni.check_feishu_readiness()["auth"] == "error"


def test_readiness_missing_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, _ = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": "markdown drive", "stderr": "", "timed_out": False},
            {"exit_code": 0, "stdout": _auth_payload(scopes=["other:scope"]), "stderr": "", "timed_out": False},
        ]
    )
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.check_feishu_readiness()
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is False


# ---------------------------------------------------------------------------
# 发布编排：argv、cwd、串行顺序、失败降级与脱敏
# ---------------------------------------------------------------------------

def _real_auth_payload(identity="user", status="ready", available=True, verified=True, scope=None) -> str:
    """真实 lark-cli auth status --json --verify 的顶层形态（2026-10 实测）。"""
    return json.dumps(
        {
            "identity": identity,
            "identities": {
                "user": {
                    "status": status,
                    "available": available,
                    "verified": verified,
                    "scope": scope if scope is not None else " ".join(ni.REQUIRED_SCOPES),
                }
            },
        }
    )


def _readiness_with_payload(monkeypatch: pytest.MonkeyPatch, payload: str) -> dict:
    runner, _ = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": "markdown drive", "stderr": "", "timed_out": False},
            {"exit_code": 0, "stdout": payload, "stderr": "", "timed_out": False},
        ]
    )
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(ni, "_run_cli", runner)
    return ni.check_feishu_readiness()


def test_readiness_parses_real_toplevel_format(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _readiness_with_payload(monkeypatch, _real_auth_payload())
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is True
    # 原始 scope 字符串不带出
    assert "drive:file:upload" not in json.dumps(result)


def test_readiness_needs_refresh_verified_available_counts_as_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI 明示下一次 user API 会自动刷新：verified+available 的 needs_refresh 判 ready。"""
    result = _readiness_with_payload(monkeypatch, _real_auth_payload(status="needs_refresh"))
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is True


def test_readiness_real_format_inside_envelope_still_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enveloped = json.dumps({"ok": True, "data": json.loads(_real_auth_payload())})
    result = _readiness_with_payload(monkeypatch, enveloped)
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is True


@pytest.mark.parametrize(
    "payload, expected_auth",
    [
        (_real_auth_payload(status="needs_refresh", verified=False), "error"),
        (_real_auth_payload(status="needs_refresh", available=False), "error"),
        (_real_auth_payload(status="expired"), "expired"),
    ],
)
def test_readiness_real_format_auth_states(
    monkeypatch: pytest.MonkeyPatch, payload: str, expected_auth: str
) -> None:
    assert _readiness_with_payload(monkeypatch, payload)["auth"] == expected_auth


def test_readiness_real_format_missing_metadata_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _readiness_with_payload(
        monkeypatch, _real_auth_payload(scope="drive:file:upload")
    )
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is False


def test_readiness_user_block_outranks_toplevel_bot_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """顶层默认身份是 bot 不应遮蔽就绪的 user 块：上传始终显式 --as user。"""
    result = _readiness_with_payload(monkeypatch, _real_auth_payload(identity="bot"))
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is True


def test_readiness_bot_only_without_user_block_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"identity": "bot"})
    result = _readiness_with_payload(monkeypatch, payload)
    assert result["auth"] == "missing"
    assert result["scopes_ready"] is False

def _ok_envelope(**data) -> dict:
    return {
        "exit_code": 0,
        "stdout": json.dumps({"ok": True, "data": data}),
        "stderr": "",
        "timed_out": False,
    }


def _note_dir(tmp_path: Path) -> Path:
    task_dir = tmp_path / "task"
    frames = task_dir / "frames"
    frames.mkdir(parents=True)
    (frames / "f1.jpg").write_bytes(b"jpg")
    return task_dir


def test_publish_markdown_only_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    runner, calls = _fake_runner_factory([_ok_envelope(file_token="mdtok", name="n")])
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# 笔记\n\n正文",
        task_dir=task_dir,
        title="我的 视频",
        folder_token="ABCdef1234567890",
        bundle_builder=lambda text, td, name: None,  # 正文无截图引用
    )
    assert result["status"] == "uploaded"
    assert result["markdown"]["token"] == "mdtok"
    assert result["zip"] is None
    assert result["error"] is None
    assert len(calls) == 1
    argv = calls[0]["argv"]
    assert argv[:3] == ["markdown", "+create", "--as"]
    assert "user" in argv
    assert "bot" not in argv
    assert "ABCdef1234567890" in argv
    # 相对路径 + 受控 cwd + 有界超时
    file_arg = argv[argv.index("--file") + 1]
    assert not Path(file_arg).is_absolute()
    assert file_arg.endswith(".md")
    assert ".." not in Path(file_arg).parts
    assert calls[0]["cwd"] is not None
    assert calls[0]["timeout"] and calls[0]["timeout"] > 0
    # 暂存目录必须清理
    assert not any(task_dir.glob(".feishu-stage-*"))


def test_publish_screenshot_note_uploads_zip_after_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    note_text = "# 笔记\n\n![截图 1](./frames/f1.jpg)"
    runner, calls = _fake_runner_factory(
        [_ok_envelope(file_token="mdtok"), _ok_envelope(file_token="ziptok")]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text=note_text,
        task_dir=task_dir,
        title="带截图",
        folder_token="ABCdef1234567890",
        bundle_builder=lambda text, td, name: b"PK-fake-zip",
    )
    assert result["status"] == "uploaded"
    assert result["markdown"]["token"] == "mdtok"
    assert result["zip"]["token"] == "ziptok"
    assert len(calls) == 2
    assert calls[0]["argv"][:2] == ["markdown", "+create"]
    assert calls[1]["argv"][:2] == ["drive", "+upload"]
    # 同一归一 token、同一身份、串行
    for call in calls:
        assert "ABCdef1234567890" in call["argv"]
        assert "user" in call["argv"]
        assert "bot" not in call["argv"]
    zip_arg = calls[1]["argv"][calls[1]["argv"].index("--file") + 1]
    assert zip_arg.endswith(".zip")


def test_publish_markdown_failure_skips_zip_and_sanitizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    raw_stderr = "Error: access_token=SECRET123 open_id=ou_xxxx"
    runner, calls = _fake_runner_factory(
        [{"exit_code": 1, "stdout": "", "stderr": raw_stderr, "timed_out": False}]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# 笔记\n\n![截图 1](./frames/f1.jpg)",
        task_dir=task_dir,
        title="x",
        folder_token="ABCdef1234567890",
        bundle_builder=lambda text, td, name: b"PK-fake-zip",
    )
    assert result["status"] == "failed"
    assert result["markdown"] is None
    assert result["zip"] is None
    assert len(calls) == 1  # 第一条失败就不再上传 ZIP
    assert result["error"]["code"]
    assert result["error"]["message"]
    # 原始 stderr / token / open_id 不得进入结果
    blob = json.dumps(result, ensure_ascii=False)
    assert "SECRET123" not in blob
    assert "ou_xxxx" not in blob
    assert "access_token" not in blob


def test_publish_zip_failure_keeps_markdown_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory(
        [
            _ok_envelope(file_token="mdtok"),
            {"exit_code": 1, "stdout": "", "stderr": "permission denied", "timed_out": False},
        ]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# 笔记\n\n![截图 1](./frames/f1.jpg)",
        task_dir=task_dir,
        title="x",
        folder_token="ABCdef1234567890",
        bundle_builder=lambda text, td, name: b"PK-fake-zip",
    )
    assert result["status"] == "failed"
    assert result["markdown"]["token"] == "mdtok"  # 已成功的步骤保留记录
    assert result["zip"] is None
    assert result["error"]["code"] == "permission_denied"


def test_publish_timeout_maps_to_timeout_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory(
        [{"exit_code": None, "stdout": "", "stderr": "", "timed_out": True}]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# 笔记",
        task_dir=task_dir,
        title="x",
        folder_token="ABCdef1234567890",
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "timeout"


# ---------------------------------------------------------------------------
# cmd 注入面：暂存文件名必须是 cmd.exe 无法解释的纯标识形态
# ---------------------------------------------------------------------------

def test_stage_name_replaces_cmd_metacharacters() -> None:
    hostile = 'x&whoami|<>^%!()"' + "'\n\r:*?\\"
    name = ni._stage_name(hostile, ".md")
    assert name.endswith(".md")
    for char in '&|<>^%!()"\'\n\r:*?/':
        assert char not in name
    # 只保留 Unicode 字母数字、空格、点、横线、下划线
    stem = name[:-3]
    assert all(char.isalnum() or char in " .-_" for char in stem)
    assert stem.strip(" .")  # 不允许退化成空名或纯占位符


def test_stage_name_preserves_normal_unicode_titles() -> None:
    assert ni._stage_name("我的 视频-笔记_v2.1", ".zip") == "我的 视频-笔记_v2.1.zip"


def test_publish_with_hostile_title_sends_only_safe_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    runner, calls = _fake_runner_factory([_ok_envelope(file_token="mdtok")])
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# 笔记",
        task_dir=task_dir,
        title="x&whoami|<>^%!()",
        folder_token="ABCdef1234567890",
    )
    assert result["status"] == "uploaded"
    file_arg = calls[0]["argv"][calls[0]["argv"].index("--file") + 1]
    for char in '&|<>^%!()"':
        assert char not in file_arg


# ---------------------------------------------------------------------------
# 发布异常隔离：任何发布阶段异常都必须降级为脱敏 failed，绝不抛出
# ---------------------------------------------------------------------------

def test_publish_bundle_builder_exception_is_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory([_ok_envelope(file_token="mdtok")])
    monkeypatch.setattr(ni, "_run_cli", runner)

    def boom(*_args, **_kwargs):
        raise OSError(f"disk exploded at {task_dir}")

    result = ni.publish_note(
        note_text="# 笔记",
        task_dir=task_dir,
        title="x",
        folder_token="ABCdef1234567890",
        bundle_builder=boom,
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "upload_failed"
    blob = json.dumps(result, ensure_ascii=False)
    assert "disk exploded" not in blob
    assert str(task_dir) not in blob
    # Markdown 已成功的记录保留；暂存目录仍被清理
    assert result["markdown"]["token"] == "mdtok"
    assert not any(task_dir.glob(".feishu-stage-*"))


def test_publish_staging_failure_is_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError(f"no space at {task_dir}")

    monkeypatch.setattr(ni.tempfile, "mkdtemp", boom)
    result = ni.publish_note(
        note_text="# 笔记",
        task_dir=task_dir,
        title="x",
        folder_token="ABCdef1234567890",
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "upload_failed"
    blob = json.dumps(result, ensure_ascii=False)
    assert "no space" not in blob
    assert str(task_dir) not in blob
