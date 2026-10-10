"""Obsidian 检测与飞书发布的合同测试。

所有 lark-cli 调用都走 fake runner：测试绝不触发真实云端写入。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend import main
from backend import media_retention
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
                    "cc": {"path": str(tmp_path / "missing"), "ts": 3},
                    "dd": {"path": str(vault_a), "ts": 4},
                    "ee": {"path": "relative/vault", "ts": 5},
                    "ff": {"path": "", "ts": 6},
                    "gg": "not-a-dict",
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
        "https://example.feishu.cn/drive/folder/ABCdef1234567890?x=1",
        "https://example.feishu.cn/wiki/ABCdef1234567890",
        "https://evil.example/ABCdef1234567890",
        "../ABCdef1234567890",
    ],
)
def test_normalize_feishu_folder_rejects_unsafe_shapes(value: str) -> None:
    with pytest.raises(ni.FeishuInputError):
        ni.normalize_feishu_folder(value)


# ---------------------------------------------------------------------------
# lark-cli 就绪检测（fake runner，无真实进程）
# ---------------------------------------------------------------------------

NARROW_SCOPES = (
    "docx:document:create",
    "docx:document:write_only",
    "docs:document.media:upload",
)


def _fake_runner_factory(responses: list):
    calls: list = []

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
                "scopes": scopes if scopes is not None else list(NARROW_SCOPES),
            },
        }
    )


def _real_auth_payload(identity="user", status="ready", available=True, verified=True, scope=None) -> str:
    return json.dumps(
        {
            "identity": identity,
            "identities": {
                "user": {
                    "status": status,
                    "available": available,
                    "verified": verified,
                    "scope": scope if scope is not None else " ".join(NARROW_SCOPES),
                }
            },
        }
    )


def _readiness_with_payload(monkeypatch: pytest.MonkeyPatch, payload: str, help_text="docs sheets") -> dict:
    runner, _ = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": help_text, "stderr": "", "timed_out": False},
            {"exit_code": 0, "stdout": payload, "stderr": "", "timed_out": False},
        ]
    )
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(ni, "_run_cli", runner)
    return ni.check_feishu_readiness()


def test_readiness_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ni, "_resolve_cli", lambda: None)
    result = ni.check_feishu_readiness()
    assert result["installed"] is False
    assert result["capable"] is False
    assert result["auth"] == "missing"
    assert result["scopes_ready"] is False


def test_readiness_requires_docs_command_not_markdown_or_drive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    runner, _ = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": "markdown drive im", "stderr": "", "timed_out": False},
            {"exit_code": 0, "stdout": _auth_payload(), "stderr": "", "timed_out": False},
        ]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    assert ni.check_feishu_readiness()["capable"] is False


def test_readiness_docs_command_is_capable(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _readiness_with_payload(monkeypatch, _auth_payload())
    assert result == {
        "installed": True,
        "capable": True,
        "auth": "ready",
        "scopes_ready": True,
    }


def test_readiness_never_leaks_scope_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _readiness_with_payload(monkeypatch, _auth_payload())
    blob = json.dumps(result)
    for scope in NARROW_SCOPES:
        assert scope not in blob
    assert "docx:document" not in blob


@pytest.mark.parametrize(
    "payload, expected_auth",
    [
        (_auth_payload(status="expired"), "expired"),
        (_auth_payload(identity="bot"), "missing"),
        ("{ not json", "error"),
    ],
)
def test_readiness_auth_states(
    monkeypatch: pytest.MonkeyPatch, payload: str, expected_auth: str
) -> None:
    assert _readiness_with_payload(monkeypatch, payload)["auth"] == expected_auth


def test_readiness_auth_timeout_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, _ = _fake_runner_factory(
        [
            {"exit_code": 0, "stdout": "docs", "stderr": "", "timed_out": False},
            {"exit_code": None, "stdout": "", "stderr": "", "timed_out": True},
        ]
    )
    monkeypatch.setattr(ni, "_resolve_cli", lambda: "lark-cli")
    monkeypatch.setattr(ni, "_run_cli", runner)
    assert ni.check_feishu_readiness()["auth"] == "error"


def test_readiness_real_toplevel_format(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _readiness_with_payload(monkeypatch, _real_auth_payload())
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is True


def test_readiness_needs_refresh_verified_available_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _readiness_with_payload(monkeypatch, _real_auth_payload(status="needs_refresh"))
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is True


def test_readiness_real_format_inside_envelope_still_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enveloped = json.dumps({"ok": True, "data": json.loads(_real_auth_payload())})
    assert _readiness_with_payload(monkeypatch, enveloped)["scopes_ready"] is True


def test_readiness_narrow_three_scopes_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _real_auth_payload(scope=" ".join(NARROW_SCOPES))
    assert _readiness_with_payload(monkeypatch, payload)["scopes_ready"] is True


def test_readiness_wide_docx_document_covers_create_and_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _real_auth_payload(scope="docx:document docs:document.media:upload")
    assert _readiness_with_payload(monkeypatch, payload)["scopes_ready"] is True


@pytest.mark.parametrize(
    "scope",
    [
        "docx:document:create docx:document:write_only",
        "docs:document.media:upload",
        "docx:document:create docs:document.media:upload",
        "docx:document:write_only docs:document.media:upload",
        "other:scope",
    ],
)
def test_readiness_requires_every_scope_group(
    monkeypatch: pytest.MonkeyPatch, scope: str
) -> None:
    result = _readiness_with_payload(monkeypatch, _real_auth_payload(scope=scope))
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is False


def test_readiness_bot_only_without_user_block_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _readiness_with_payload(monkeypatch, json.dumps({"identity": "bot"}))
    assert result["auth"] == "missing"
    assert result["scopes_ready"] is False


# ---------------------------------------------------------------------------
# 发布编排：单次 docs +create、argv、cwd、内联图片、失败降级与脱敏
# ---------------------------------------------------------------------------

def _doc_envelope(**document) -> dict:
    return {
        "exit_code": 0,
        "stdout": json.dumps({"ok": True, "data": {"document": document}}),
        "stderr": "",
        "timed_out": False,
    }


def _capturing_runner_factory(responses: list):
    calls: list = []

    def runner(argv, *, cwd=None, timeout=None):
        record = {"argv": list(argv), "cwd": cwd, "timeout": timeout, "content": None}
        if "--content" in argv:
            ref = argv[argv.index("--content") + 1]
            if isinstance(ref, str) and ref.startswith("@") and cwd:
                path = Path(cwd) / ref[1:]
                if path.is_file():
                    record["content"] = path.read_text(encoding="utf-8")
        calls.append(record)
        if not responses:
            raise AssertionError("unexpected extra CLI call")
        return responses.pop(0)

    return runner, calls


def _note_dir(tmp_path: Path) -> Path:
    task_dir = tmp_path / "task"
    frames = task_dir / "frames"
    frames.mkdir(parents=True)
    (frames / "f1.jpg").write_bytes(b"jpg")
    return task_dir


def _frame_task(tmp_path: Path, images: dict) -> Path:
    task_dir = tmp_path / "task"
    frames = task_dir / "frames"
    frames.mkdir(parents=True)
    for name, data in images.items():
        (frames / name).write_bytes(data)
    return task_dir


def _note(lines: list) -> str:
    return "\n".join(lines)


def test_publish_creates_native_docx_with_single_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    runner, calls = _capturing_runner_factory(
        [_doc_envelope(document_id="doxcnX", name="我的笔记", url="https://x.feishu.cn/docx/doxcnX")]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text=_note(["# 笔记", "", "正文"]),
        task_dir=task_dir,
        title="我的 视频",
        folder_token="ABCdef1234567890",
    )
    assert result["status"] == "uploaded"
    assert result["format"] == "native_docx"
    assert result["document"]["name"] == "我的笔记"
    assert result["document"]["url"] == "https://x.feishu.cn/docx/doxcnX"
    assert result["error"] is None
    assert "markdown" not in result
    assert "zip" not in result
    assert len(calls) == 1
    argv = calls[0]["argv"]
    assert argv[:4] == ["docs", "+create", "--as", "user"]
    assert "bot" not in argv
    assert "media-insert" not in argv
    assert "ABCdef1234567890" in argv
    assert argv[argv.index("--doc-format") + 1] == "markdown"
    content_arg = argv[argv.index("--content") + 1]
    assert content_arg.startswith("@")
    rel = content_arg[1:]
    assert not Path(rel).is_absolute()
    assert rel.endswith(".md")
    assert ".." not in Path(rel).parts
    assert calls[0]["cwd"] is not None
    assert calls[0]["timeout"] and calls[0]["timeout"] > 0
    assert not any(task_dir.glob(".feishu-stage-*"))


def test_publish_missing_document_id_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory([_doc_envelope(name="n")])
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "failed"
    assert result["format"] == "native_docx"
    assert result["document"] is None
    assert result["error"]["code"]
    assert not any(task_dir.glob(".feishu-stage-*"))


def test_publish_non_ok_envelope_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory(
        [{"exit_code": 0, "stdout": json.dumps({"ok": False, "error": "bad"}), "stderr": "", "timed_out": False}]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "failed"
    assert result["document"] is None


def test_publish_nonzero_exit_sanitizes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    raw = "Error: access_token=SECRET123 open_id=ou_xxxx"
    runner, _ = _fake_runner_factory(
        [{"exit_code": 1, "stdout": "", "stderr": raw, "timed_out": False}]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "failed"
    blob = json.dumps(result, ensure_ascii=False)
    assert "SECRET123" not in blob
    assert "ou_xxxx" not in blob
    assert "access_token" not in blob


def test_publish_timeout_maps_to_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory(
        [{"exit_code": None, "stdout": "", "stderr": "", "timed_out": True}]
    )
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "timeout"


@pytest.mark.parametrize("bad_url", ["http://x.feishu.cn/docx/d", "javascript:alert(1)", "not a url", ""])
def test_publish_drops_unsafe_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_url: str
) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory([_doc_envelope(document_id="d1", name="n", url=bad_url)])
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "uploaded"
    assert result["document"]["url"] is None


def test_publish_screenshot_note_single_call_with_inline_frames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _frame_task(tmp_path, {"n1.jpg": b"a", "n2.png": b"b"})
    note_text = _note(
        ["# n", "", "![one](./frames/n1.jpg)", "", "![two](./frames/n2.png)", "", "![dup](./frames/n1.jpg)"]
    )
    runner, calls = _capturing_runner_factory([_doc_envelope(document_id="d1", name="n")])
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text=note_text,
        task_dir=task_dir,
        title="t",
        folder_token="ABCdef1234567890",
        staging_builder=main.build_feishu_docx_staging,
    )
    assert result["status"] == "uploaded"
    assert len(calls) == 1
    content = calls[0]["content"]
    assert content is not None
    assert "![one](<@./frames/image-001.jpg>)" in content
    assert "![two](<@./frames/image-002.png>)" in content
    assert content.count("@./frames/image-001.jpg") == 2
    assert not any(task_dir.glob(".feishu-stage-*"))


def test_publish_maps_media_error_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    runner, calls = _fake_runner_factory([_doc_envelope(document_id="d1")])
    monkeypatch.setattr(ni, "_run_cli", runner)

    def builder(*_args, **_kwargs):
        raise ni.FeishuMediaError("image_too_large")

    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890",
        staging_builder=builder,
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "image_too_large"
    assert calls == []


def test_publish_staging_builder_exception_is_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory([_doc_envelope(document_id="d1")])
    monkeypatch.setattr(ni, "_run_cli", runner)

    def boom(*_args, **_kwargs):
        raise OSError("disk exploded at " + str(task_dir))

    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890",
        staging_builder=boom,
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "upload_failed"
    blob = json.dumps(result, ensure_ascii=False)
    assert "disk exploded" not in blob
    assert str(task_dir) not in blob
    assert not any(task_dir.glob(".feishu-stage-*"))


def test_publish_staging_failure_is_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("no space at " + str(task_dir))

    monkeypatch.setattr(ni.tempfile, "mkdtemp", boom)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "upload_failed"
    blob = json.dumps(result, ensure_ascii=False)
    assert "no space" not in blob


def test_publish_invalid_folder_returns_invalid_folder_without_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    called: list = []
    monkeypatch.setattr(ni, "_run_cli", lambda *a, **k: called.append(a) or {})
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="not a token!"
    )
    assert result["status"] == "failed"
    assert result["error"]["code"] == "invalid_folder"
    assert called == []


# ---------------------------------------------------------------------------
# 飞书 docx 暂存构建：Frontmatter、图片编号、边界与格式/大小校验
# ---------------------------------------------------------------------------

def _build(tmp_path: Path, note_text: str, images: dict) -> str:
    task_dir = _frame_task(tmp_path, images)
    staging = tmp_path / "stage"
    staging.mkdir()
    main.build_feishu_docx_staging(note_text, task_dir, staging, "note.md")
    return (staging / "note.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "note_text, images, expected",
    [
        (_note(["# n", "", "![a](./frames/a.jpg)"]), {"a.jpg": b"x"}, "![a](<@./frames/image-001.jpg>)"),
        (_note(["# n", "", "![a](./images/a.jpg)"]), {"a.jpg": b"x"}, "![a](<@./frames/image-001.jpg>)"),
    ],
)
def test_staging_rewrites_refs_inline(
    tmp_path: Path, note_text: str, images: dict, expected: str
) -> None:
    assert expected in _build(tmp_path, note_text, images)


def test_staging_numbers_by_first_appearance(tmp_path: Path) -> None:
    content = _build(
        tmp_path,
        _note(["![b](./frames/b.png)", "", "![a](./frames/a.jpg)"]),
        {"a.jpg": b"a", "b.png": b"b"},
    )
    assert content.index("image-001.png") < content.index("image-002.jpg")


def test_staging_dedupes_repeated_references(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {"a.jpg": b"a"})
    staging = tmp_path / "stage"
    staging.mkdir()
    main.build_feishu_docx_staging(
        _note(["![x](./frames/a.jpg)", "", "![y](./images/a.jpg)"]), task_dir, staging, "note.md"
    )
    staged = sorted(p.name for p in (staging / "frames").iterdir())
    assert staged == ["image-001.jpg"]


def test_staging_strips_leading_frontmatter(tmp_path: Path) -> None:
    content = _build(
        tmp_path,
        _note(["---", "title: 秘密标题", "tags: [a]", "---", "# 正文", "", "内容"]),
        {},
    )
    assert "秘密标题" not in content
    assert content.lstrip().startswith("# 正文")


@pytest.mark.parametrize(
    "note_text",
    [
        _note(["---", "title: x", "# 无闭合分隔符"]),
        _note(["# 首行不是分隔符", "---", "key: value", "---", "正文"]),
    ],
)
def test_staging_keeps_malformed_or_non_leading_frontmatter(tmp_path: Path, note_text: str) -> None:
    content = _build(tmp_path, note_text, {})
    assert content == note_text  # 畸形或非首行 Frontmatter 必须原样保留


def test_staging_rejects_unsupported_image_format(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {"a.bmp": b"x"})
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(ni.FeishuMediaError) as excinfo:
        main.build_feishu_docx_staging("![a](./frames/a.bmp)", task_dir, staging, "note.md")
    assert excinfo.value.code == "unsupported_image"


def test_staging_rejects_oversized_image(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {})
    big = task_dir / "frames" / "big.jpg"
    with big.open("wb") as handle:
        handle.truncate(main.FEISHU_MAX_IMAGE_BYTES + 1)
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(ni.FeishuMediaError) as excinfo:
        main.build_feishu_docx_staging("![a](./frames/big.jpg)", task_dir, staging, "note.md")
    assert excinfo.value.code == "image_too_large"


def test_staging_rejects_missing_referenced_image(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {})
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(ni.FeishuMediaError) as excinfo:
        main.build_feishu_docx_staging("![a](./frames/nope.jpg)", task_dir, staging, "note.md")
    assert excinfo.value.code == "unsupported_image"


def test_staging_rejects_escaping_reference(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {})
    (task_dir / "secret.jpg").write_bytes(b"s")
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(ni.FeishuMediaError):
        main.build_feishu_docx_staging("![a](./frames/../secret.jpg)", task_dir, staging, "note.md")


def test_staging_does_not_touch_original_artifacts(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {"a.jpg": b"a"})
    staging = tmp_path / "stage"
    staging.mkdir()
    main.build_feishu_docx_staging("![a](./frames/a.jpg)", task_dir, staging, "note.md")
    assert (task_dir / "frames" / "a.jpg").read_bytes() == b"a"
    assert (staging / "note.md").read_text(encoding="utf-8").count("image-001.jpg") == 1


# ---------------------------------------------------------------------------
# cmd 注入面：暂存文件名必须是 cmd.exe 无法解释的纯标识形态
# ---------------------------------------------------------------------------

def test_stage_name_replaces_cmd_metacharacters() -> None:
    hostile = "x&whoami|<>^%!()" + '"' + "'" + chr(10) + chr(13) + ":*?" + chr(92)
    name = ni._stage_name(hostile, ".md")
    assert name.endswith(".md")
    for char in '&|<>^%!()"\'\n\r:*?/':
        assert char not in name
    stem = name[:-3]
    assert all(char.isalnum() or char in " .-_" for char in stem)
    assert stem.strip(" .")


def test_stage_name_preserves_normal_unicode_titles() -> None:
    assert ni._stage_name("我的 视频-笔记_v2.1", ".zip") == "我的 视频-笔记_v2.1.zip"


def test_publish_with_hostile_title_sends_only_safe_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _note_dir(tmp_path)
    runner, calls = _fake_runner_factory([_doc_envelope(document_id="d1")])
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x&whoami|<>^%!()", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "uploaded"
    argv = calls[0]["argv"]
    for value in (argv[argv.index("--title") + 1], argv[argv.index("--content") + 1]):
        for char in '&|<>^%!()"':
            assert char not in value


def test_production_source_never_uses_forbidden_commands() -> None:
    source = Path(ni.__file__).read_text(encoding="utf-8")
    assert "+media-insert" not in source
    assert "+upload" not in source
    assert '"markdown", "+create"' not in source
    assert '"drive", "+upload"' not in source


def test_sanitized_failure_uses_native_docx_contract() -> None:
    failure = ni.sanitized_failure("timeout")
    assert failure["status"] == "failed"
    assert failure["format"] == "native_docx"
    assert failure["document"] is None
    assert failure["error"]["code"] == "timeout"
    assert "markdown" not in failure
    assert "zip" not in failure


def _doc_envelope_with_warnings(warnings, document_id="d1", name="n") -> dict:
    return {
        "exit_code": 0,
        "stdout": json.dumps(
            {"ok": True, "data": {"document": {"document_id": document_id, "name": name}, "warnings": warnings}}
        ),
        "stderr": "",
        "timed_out": False,
    }


def test_readiness_user_block_outranks_toplevel_bot_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _readiness_with_payload(monkeypatch, _real_auth_payload(identity="bot"))
    assert result["auth"] == "ready"
    assert result["scopes_ready"] is True


def test_publish_surfaces_redacted_partial_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    raw = "block token=SECRET leaked path C:/Users/secret/private"
    runner, _ = _fake_runner_factory([_doc_envelope_with_warnings([raw])])
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "uploaded"
    assert result["warning"]["code"] == "partial_publication"
    assert result["warning"]["message"]
    blob = json.dumps(result, ensure_ascii=False)
    assert "SECRET" not in blob
    assert raw not in blob
    assert "C:/Users/secret" not in blob


def test_publish_without_warnings_has_null_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    runner, _ = _fake_runner_factory([_doc_envelope(document_id="d1", name="n")])
    monkeypatch.setattr(ni, "_run_cli", runner)
    result = ni.publish_note(
        note_text="# n", task_dir=task_dir, title="x", folder_token="ABCdef1234567890"
    )
    assert result["status"] == "uploaded"
    assert result["warning"] is None


def test_sanitized_failure_has_null_warning() -> None:
    assert ni.sanitized_failure("timeout")["warning"] is None


def test_safe_document_title_keeps_unicode_punctuation() -> None:
    title = ni._safe_document_title("课程：第一章（入门）")
    for token in ("课程", "第一章", "：", "（", "）"):
        assert token in title


def test_safe_document_title_strips_cmd_metacharacters() -> None:
    raw = "a&b|c<d>e^f%g!h(i)j" + '"' + chr(10) + chr(13)
    title = ni._safe_document_title(raw)
    for char in '&|<>^%!()"\n\r':
        assert char not in title
    assert title


def test_safe_document_title_fallbacks_and_length() -> None:
    assert ni._safe_document_title("   ") == "video-notes"
    assert ni._safe_document_title("") == "video-notes"
    assert len(ni._safe_document_title("x" * 200)) <= 80


def test_publish_keeps_unicode_title_in_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    task_dir = _note_dir(tmp_path)
    runner, calls = _fake_runner_factory([_doc_envelope(document_id="d1")])
    monkeypatch.setattr(ni, "_run_cli", runner)
    ni.publish_note(
        note_text="# n", task_dir=task_dir, title="课程：第一章（入门）", folder_token="ABCdef1234567890"
    )
    title_arg = calls[0]["argv"][calls[0]["argv"].index("--title") + 1]
    assert "：" in title_arg and "（" in title_arg


def test_staging_ignores_frontmatter_only_images(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {"a.jpg": b"x"})
    staging = tmp_path / "stage"
    staging.mkdir()
    note = _note(["---", "cover: ![a](./frames/a.jpg)", "---", "# 正文", "", "没有图片"])
    main.build_feishu_docx_staging(note, task_dir, staging, "note.md")
    content = (staging / "note.md").read_text(encoding="utf-8")
    assert "frames/a.jpg" not in content
    assert "image-" not in content
    frames = staging / "frames"
    assert not frames.exists() or not any(frames.iterdir())


def test_staging_frontmatter_missing_image_does_not_fail(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {})
    staging = tmp_path / "stage"
    staging.mkdir()
    note = _note(["---", "cover: ![x](./frames/missing.jpg)", "---", "# 正文"])
    main.build_feishu_docx_staging(note, task_dir, staging, "note.md")
    assert "missing.jpg" not in (staging / "note.md").read_text(encoding="utf-8")


def test_staging_rejects_hardlinked_referenced_image(tmp_path: Path) -> None:
    task_dir = _frame_task(tmp_path, {})
    external = tmp_path / "external.jpg"
    external.write_bytes(b"external")
    os.link(external, task_dir / "frames" / "a.jpg")
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(ni.FeishuMediaError):
        main.build_feishu_docx_staging("![a](./frames/a.jpg)", task_dir, staging, "note.md")
    assert external.read_bytes() == b"external"


def test_staging_rejects_replaced_image_and_does_not_copy_attacker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_dir = _frame_task(tmp_path, {"a.jpg": b"original"})
    staging = tmp_path / "stage"
    staging.mkdir()
    original_open = media_retention._open_fd

    def swap_then_open(path, *, directory=False, delete=False):
        if path.name == "a.jpg":
            path.rename(path.with_name("swapped.bin"))
            path.write_bytes(b"attacker")
        return original_open(path, directory=directory, delete=delete)

    monkeypatch.setattr(media_retention, "_open_fd", swap_then_open)
    with pytest.raises(ni.FeishuMediaError):
        main.build_feishu_docx_staging("![a](./frames/a.jpg)", task_dir, staging, "note.md")
    frames = staging / "frames"
    staged = list(frames.iterdir()) if frames.exists() else []
    assert all(p.read_bytes() != b"attacker" for p in staged)
