"""Obsidian Vault 检测与飞书发布（见 .omx/plans/obsidian-feishu-destination-milestone.md）。

边界：
- Obsidian 只读检测：不启动应用、不改配置、不创建 Vault。
- 飞书默认关闭；发布只走 lark-cli 的 --as user，绝不回退 bot，绝不自动登录。
- 不持久化 token/auth 原始输出、用户身份字段或完整 scopes；错误一律脱敏成
  稳定的 code + 通用文案。
- 子进程只用 argv 列表，不拼接 shell 字符串；Windows 的 .cmd shim 走
  cmd.exe 有界启动（CREATE_NO_WINDOW），参数全部来自已校验值。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DEFAULT_VAULT_SUBFOLDER = "Video2Knowledge"

# 创建原生 Markdown、读取目标文件夹元数据与普通文件上传所需的最小 scope。
REQUIRED_SCOPES: tuple[str, ...] = ("drive:file:upload", "drive:drive.metadata:readonly")

CLI_TIMEOUT_SECONDS = 30

_FOLDER_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{8,64}$")
_FOLDER_URL_RE = re.compile(r"^https?://[^/]+/drive/folder/([A-Za-z0-9]{8,64})/?$")


class FeishuInputError(ValueError):
    """飞书目标输入不合法；文案稳定，可直接展示给用户。"""


# ---------------------------------------------------------------------------
# Obsidian 只读检测
# ---------------------------------------------------------------------------

def detect_obsidian(
    env: dict[str, str] | None = None, platform: str | None = None
) -> dict[str, Any]:
    """读取 %APPDATA%\\obsidian\\obsidian.json，返回仍存在的 Vault 列表。

    缺失 / 损坏 / 非 Windows 都不是错误：返回稳定状态，前端据此降级为手动填写。
    """
    platform = platform if platform is not None else sys.platform
    if platform != "win32":
        return {"status": "unsupported", "vaults": []}
    env = os.environ if env is None else env
    appdata = env.get("APPDATA")
    if not appdata:
        return {"status": "missing", "vaults": []}
    config = Path(appdata) / "obsidian" / "obsidian.json"
    if not config.is_file():
        return {"status": "missing", "vaults": []}
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"status": "corrupt", "vaults": []}
    vaults = data.get("vaults") if isinstance(data, dict) else None
    if not isinstance(vaults, dict):
        return {"status": "corrupt", "vaults": []}
    seen: set[str] = set()
    found: list[dict[str, Any]] = []
    for entry in vaults.values():
        if not isinstance(entry, dict):
            continue
        raw = entry.get("path")
        if not isinstance(raw, str) or not raw.strip():
            continue
        path = Path(raw)
        if not path.is_absolute() or not path.is_dir():
            continue
        try:
            key = os.path.normcase(str(path.resolve()))
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "label": path.name or str(path),
                "path": str(path),
                "open": bool(entry.get("open")),
                "suggested_destination": str(path / DEFAULT_VAULT_SUBFOLDER),
            }
        )
    return {"status": "ok", "vaults": found}


# ---------------------------------------------------------------------------
# 飞书目标归一
# ---------------------------------------------------------------------------

def normalize_feishu_folder(value: str) -> str:
    """只接受裸 folder token 或 /drive/folder/<token> 链接，归一成 token。

    拒绝空白、引号、query、shell 元字符、wiki 等一切其他形态——token 随后
    会作为 argv 参数传给 CLI，必须是无歧义的纯标识符。
    """
    cleaned = (value or "").strip()
    if _FOLDER_TOKEN_RE.fullmatch(cleaned):
        return cleaned
    match = _FOLDER_URL_RE.fullmatch(cleaned)
    if match:
        return match.group(1)
    raise FeishuInputError(
        "飞书目标必须是 Drive 文件夹 token 或 /drive/folder/<token> 链接"
    )


# ---------------------------------------------------------------------------
# lark-cli 有界执行
# ---------------------------------------------------------------------------

def _resolve_cli() -> str | None:
    names = ("lark-cli.cmd", "lark-cli.exe", "lark-cli") if sys.platform == "win32" else ("lark-cli",)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def _run_cli(
    argv_tail: list[str], *, cwd: str | None = None, timeout: int | None = None
) -> dict[str, Any]:
    """以 argv 列表执行 lark-cli；绝不拼接 shell 字符串，绝不抛异常。

    返回 {"exit_code", "stdout", "stderr", "timed_out"}。stdout/stderr 只用于
    当次判断与错误归类，调用方不得把它们持久化。
    """
    cli = _resolve_cli()
    if cli is None:
        return {"exit_code": None, "stdout": "", "stderr": "cli missing", "timed_out": False}
    timeout = timeout or CLI_TIMEOUT_SECONDS
    if sys.platform == "win32" and cli.lower().endswith(".cmd"):
        argv = ["cmd.exe", "/d", "/s", "/c", cli, *argv_tail]
        kwargs: dict[str, Any] = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    else:
        argv = [cli, *argv_tail]
        kwargs = {}
    env = dict(os.environ)
    # 抑制 CLI 的升级/skills 提示，保持 stdout 可解析
    env.setdefault("NO_UPDATE_NOTIFIER", "1")
    env.setdefault("LARK_CLI_NO_UPDATE_NOTIFIER", "1")
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "stdout": "", "stderr": "timeout", "timed_out": True}
    except OSError as exc:
        return {"exit_code": None, "stdout": "", "stderr": f"os error: {type(exc).__name__}", "timed_out": False}
    return {
        "exit_code": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
        "timed_out": False,
    }


def _parse_envelope(stdout: str) -> dict[str, Any] | None:
    """解析 lark-cli 的 JSON 信封；成功以 ok == true 为准（不是 code == 0）。"""
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _extract_auth_data(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """兼容两种 auth status 输出：真实的顶层对象，以及 {ok, data} 信封。

    真实格式（2026-10 实测）：顶层 identity + identities.user{status, available,
    verified, scope（空格分隔字符串）}。信封格式把同一对象包在 data 里。
    """
    if payload is None:
        return None
    if "ok" in payload:
        if payload.get("ok") is not True:
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else None
    if "identity" in payload or "identities" in payload:
        return payload
    return None


def _auth_state(data: dict[str, Any]) -> tuple[str, bool]:
    """从 auth status 对象推导（auth 状态, scope 是否就绪）；绝不回退 bot。"""
    identities = data.get("identities") if isinstance(data.get("identities"), dict) else {}
    user = identities.get("user") if isinstance(identities.get("user"), dict) else None
    identity = data.get("identity")
    if user is None:
        # legacy/envelope 没有 user 身份块时，才按顶层 identity 判断：
        # bot-only 或未登录都视为 user 不可用，绝不回退 bot
        if identity != "user":
            return "missing", False
    # 真实格式存在 identities.user 时只看 user 块：上传始终显式 --as user，
    # 顶层默认身份是 bot 并不遮蔽一个就绪的 user 身份（这不算 bot fallback）
    info = user if user is not None else data
    state = str(info.get("status") or data.get("status") or "")
    if state in {"expired", "invalid", "revoked"}:
        return "expired", False
    # needs_refresh：CLI 明示下一次 user API 调用会自动刷新，verified+available
    # 即可视为就绪；不会在这里触发刷新（本函数只读）。
    available = info.get("available", True) is not False
    verified = info.get("verified", True) is not False
    if state not in {"ready", "needs_refresh"} or not (available and verified):
        return "error", False
    raw = info.get("scope")
    if raw is None:
        raw = data.get("scopes", data.get("scope"))
    if isinstance(raw, str):
        granted = set(raw.split())
    elif isinstance(raw, list):
        granted = {str(item) for item in raw}
    else:
        granted = set()
    return "ready", all(scope in granted for scope in REQUIRED_SCOPES)


def check_feishu_readiness() -> dict[str, Any]:
    """只读就绪检测：CLI 安装、命令能力、user 身份与最小 scope。

    只用 --help 与 auth status（--json --verify），不登录、不做任何写操作。
    返回值不含原始输出、token、open_id、用户名或 scope 明细。
    """
    unavailable = {"installed": False, "capable": False, "auth": "missing", "scopes_ready": False}
    if _resolve_cli() is None:
        return unavailable
    help_result = _run_cli(["--help"])
    help_text = help_result["stdout"] + "\n" + help_result["stderr"]
    capable = (
        help_result["exit_code"] == 0
        and "markdown" in help_text
        and "drive" in help_text
    )
    auth: str = "error"
    scopes_ready = False
    status_result = _run_cli(["auth", "status", "--json", "--verify"])
    if status_result["timed_out"] or status_result["exit_code"] != 0:
        auth = "error"
    else:
        data = _extract_auth_data(_parse_envelope(status_result["stdout"]))
        if data is None:
            auth = "error"
        else:
            auth, scopes_ready = _auth_state(data)
    return {
        "installed": True,
        "capable": capable,
        "auth": auth,
        "scopes_ready": scopes_ready,
    }


# ---------------------------------------------------------------------------
# 发布：原生 Markdown（+ 截图 ZIP）串行上传到指定 folder
# ---------------------------------------------------------------------------

_ERROR_MESSAGES = {
    "auth_expired": "飞书登录已过期或权限不足，请重新授权后重试",
    "invalid_folder": "飞书目标文件夹无效或不可访问",
    "permission_denied": "没有该飞书文件夹的写入权限",
    "rate_limit": "飞书接口限流，请稍后重试",
    "timeout": "飞书上传超时（远端结果不确定，重试可能产生重复文件）",
    "upload_failed": "飞书上传失败，请稍后重试",
}


def _classify_error(result: dict[str, Any]) -> str:
    """把 CLI 失败归类成稳定错误码；原始输出只用于当次匹配，不落盘。"""
    if result.get("timed_out"):
        return "timeout"
    text = f"{result.get('stdout', '')} {result.get('stderr', '')}".lower()
    if any(marker in text for marker in ("401", "unauthorized", "login", "token expired", "auth")):
        return "auth_expired"
    if any(marker in text for marker in ("permission", "forbidden", "403")):
        return "permission_denied"
    if any(marker in text for marker in ("rate", "429", "too many")):
        return "rate_limit"
    if "folder" in text and any(marker in text for marker in ("invalid", "not found", "404", "not_found")):
        return "invalid_folder"
    return "upload_failed"


# 暂存文件名允许集：Unicode 字母数字、空格、点、横线、下划线。
# 其他字符（含 cmd.exe 元字符 & | < > ^ % ! ( )、引号、换行、路径分隔符）一律替换为 _：
# 文件名随后会作为 .cmd 调用的 argv 参数，必须是 cmd 无法解释的纯标识形态。
_STAGE_SAFE_CHARS = frozenset(" .-_")


def _stage_name(title: str, suffix: str) -> str:
    cleaned = "".join(
        char if (char.isalnum() or char in _STAGE_SAFE_CHARS) else "_" for char in title
    ).strip(" .")
    return f"{(cleaned or 'video-notes')[:80]}{suffix}"


def _extract_file_info(envelope: dict[str, Any]) -> dict[str, Any]:
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    return {
        "token": data.get("file_token") or data.get("token"),
        "name": data.get("name"),
    }


def sanitized_failure(code: str = "upload_failed") -> dict[str, Any]:
    """脱敏的失败 publication：只含稳定 code 与通用文案，绝不含异常、路径或原始输出。"""
    return {
        "status": "failed",
        "markdown": None,
        "zip": None,
        "error": {"code": code, "message": _ERROR_MESSAGES[code]},
        "attempted_at": datetime.now(timezone.utc).isoformat(),
    }


def publish_note(
    *,
    note_text: str,
    task_dir: Path,
    title: str,
    folder_token: str,
    bundle_builder: Callable[[str, Path, str], bytes | None] | None = None,
) -> dict[str, Any]:
    """把最终 Markdown 发布到飞书 folder；有截图时再串行上传一个 ZIP。

    暂存文件放在任务目录下的一次性 .feishu-stage-* 目录，finally 清理，
    绝不删除任务原始产物。结果只含脱敏字段。
    """
    try:
        token = normalize_feishu_folder(folder_token)  # 调用方之外再兜一道
    except FeishuInputError:
        return sanitized_failure("invalid_folder")
    attempted_at = datetime.now(timezone.utc).isoformat()
    outcome: dict[str, Any] = {
        "status": "failed",
        "markdown": None,
        "zip": None,
        "error": None,
        "attempted_at": attempted_at,
    }
    task_dir = Path(task_dir)
    try:
        staging = Path(tempfile.mkdtemp(prefix=".feishu-stage-", dir=task_dir))
    except Exception:
        # 发布是 best-effort：暂存失败也要返回脱敏结果，绝不向调用方抛异常
        return sanitized_failure()
    try:
        md_name = _stage_name(title, ".md")
        (staging / md_name).write_text(note_text, encoding="utf-8")
        create = _run_cli(
            ["markdown", "+create", "--as", "user", "--folder-token", token, "--file", md_name],
            cwd=str(staging),
            timeout=CLI_TIMEOUT_SECONDS,
        )
        envelope = _parse_envelope(create["stdout"]) if create["exit_code"] == 0 else None
        if envelope is None or envelope.get("ok") is not True:
            code = _classify_error(create)
            outcome["error"] = {"code": code, "message": _ERROR_MESSAGES[code]}
            return outcome
        outcome["markdown"] = _extract_file_info(envelope)

        bundle = bundle_builder(note_text, task_dir, md_name) if bundle_builder else None
        if bundle:
            zip_name = _stage_name(title, ".zip")
            (staging / zip_name).write_bytes(bundle)
            upload = _run_cli(
                ["drive", "+upload", "--as", "user", "--folder-token", token, "--file", zip_name],
                cwd=str(staging),
                timeout=CLI_TIMEOUT_SECONDS,
            )
            envelope = _parse_envelope(upload["stdout"]) if upload["exit_code"] == 0 else None
            if envelope is None or envelope.get("ok") is not True:
                code = _classify_error(upload)
                outcome["error"] = {"code": code, "message": _ERROR_MESSAGES[code]}
                return outcome
            outcome["zip"] = _extract_file_info(envelope)
        outcome["status"] = "uploaded"
        return outcome
    except Exception:
        # bundle_builder / 写盘 / CLI 编排里的任何异常都降级为脱敏失败：
        # 本地笔记已经完成并落盘，发布异常绝不能把它改判 failed
        outcome["error"] = {
            "code": "upload_failed",
            "message": _ERROR_MESSAGES["upload_failed"],
        }
        return outcome
    finally:
        shutil.rmtree(staging, ignore_errors=True)
