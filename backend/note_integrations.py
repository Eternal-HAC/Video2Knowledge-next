"""Obsidian Vault 检测与飞书在线文档发布（见 .omx/plans/feishu-native-docx-implementation.md）。

边界：
- Obsidian 只读检测：不启动应用、不改配置、不创建 Vault。
- 飞书默认关闭；发布只走 lark-cli 的 --as user，绝不回退 bot，绝不自动登录。
- 只创建在线 docx：一次 docs +create --doc-format markdown，正文内联本地图片；
  禁止 media-insert、DocxXML、Drive import 以及旧的 markdown/drive 上传命令。
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
from urllib.parse import urlsplit

DEFAULT_VAULT_SUBFOLDER = "Video2Knowledge"

# 在线 docx 发布所需的授权能力组：每组至少命中一个 scope，全部满足才算就绪。
# 前三项窄 scope 是 README 推荐授权；其它宽权限仅为兼容官方等价权限。
REQUIRED_SCOPE_GROUPS: tuple[tuple[str, ...], ...] = (
    ("docx:document", "docx:document:create"),
    ("docx:document", "docx:document:write_only"),
    (
        "docs:document.media:upload",
        "docs:doc",
        "drive:drive",
        "bitable:app",
        "sheets:spreadsheet",
    ),
)

CLI_TIMEOUT_SECONDS = 30

_FOLDER_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{8,64}$")
_FOLDER_URL_RE = re.compile(r"^https?://[^/]+/drive/folder/([A-Za-z0-9]{8,64})/?$")


class FeishuInputError(ValueError):
    """飞书目标输入不合法；文案稳定，可直接展示给用户。"""


class FeishuMediaError(ValueError):
    """被引用图片不满足格式/大小/边界约束；code 是稳定的脱敏错误码。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


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
    return "ready", _scopes_ready(granted)


def _scopes_ready(granted: set[str]) -> bool:
    """每组能力至少命中一个 scope；全部满足才算就绪。"""
    return all(any(scope in granted for scope in group) for group in REQUIRED_SCOPE_GROUPS)


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
    capable = help_result["exit_code"] == 0 and "docs" in help_text
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
# 发布：一次 docs +create 创建在线 docx，正文内联本地图片
# ---------------------------------------------------------------------------

_ERROR_MESSAGES = {
    "auth_expired": "飞书登录已过期或权限不足，请重新授权后重试",
    "invalid_folder": "飞书目标文件夹无效或不可访问",
    "permission_denied": "没有该飞书文件夹的写入权限",
    "rate_limit": "飞书接口限流，请稍后重试",
    "timeout": "飞书上传超时（远端结果不确定，重试可能产生重复文档）",
    "upload_failed": "飞书上传失败，请稍后重试",
    "unsupported_image": "笔记引用的图片格式不受支持，已跳过飞书上传",
    "image_too_large": "笔记引用的图片超过飞书单图大小上限，已跳过飞书上传",
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


_TITLE_UNSAFE_CHARS = frozenset('&|<>^%!()"')


def _safe_document_title(title: str) -> str:
    """在线文档标题：保留普通 Unicode（含中文标点），只去掉控制字符与 cmd 元字符。"""
    cleaned = "".join(
        char for char in str(title)
        if char.isprintable() and char not in _TITLE_UNSAFE_CHARS
    ).strip()
    return cleaned[:80].strip() or "video-notes"


_PUBLICATION_WARNING_MESSAGES = {
    "partial_publication": "飞书在线文档已创建，但部分内容可能未完整转换，请打开文档检查",
}


def _has_publication_warnings(envelope: dict[str, Any] | None) -> bool:
    """信封 data.warnings 非空列表即视为部分发布警告；原始内容绝不外传。"""
    if not isinstance(envelope, dict):
        return False
    data = envelope.get("data")
    if not isinstance(data, dict):
        return False
    warnings = data.get("warnings")
    return isinstance(warnings, list) and len(warnings) > 0


def _safe_https_url(value: Any) -> str | None:
    """只接受结构可验证的 https URL；否则返回 None，绝不落原始值。"""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if any(char.isspace() for char in text):
        return None
    parts = urlsplit(text)
    if parts.scheme != "https" or not parts.netloc or "@" in parts.netloc:
        return None
    return text


def _extract_document(envelope: dict[str, Any] | None, fallback_name: str) -> dict[str, Any] | None:
    """从 create 信封提取 {name, url}；缺 document_id 视为失败，绝不落 document_id。"""
    if not isinstance(envelope, dict) or envelope.get("ok") is not True:
        return None
    data = envelope.get("data")
    if not isinstance(data, dict):
        return None
    document = data.get("document")
    if not isinstance(document, dict):
        return None
    document_id = document.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip():
        return None
    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        name = fallback_name
    return {"name": name, "url": _safe_https_url(document.get("url"))}


def sanitized_failure(code: str = "upload_failed", attempted_at: str | None = None) -> dict[str, Any]:
    """脱敏的失败 publication：只含稳定 code 与通用文案，绝不含异常、路径或原始输出。"""
    return {
        "status": "failed",
        "format": "native_docx",
        "document": None,
        "warning": None,
        "error": {"code": code, "message": _ERROR_MESSAGES[code]},
        "attempted_at": attempted_at or datetime.now(timezone.utc).isoformat(),
    }


def publish_note(
    *,
    note_text: str,
    task_dir: Path,
    title: str,
    folder_token: str,
    staging_builder: Callable[[str, Path, Path, str], None] | None = None,
) -> dict[str, Any]:
    """把最终 Markdown 发布为飞书在线 docx：单次 docs +create，正文内联本地图片。

    staging_builder 负责在暂存目录内完成 Frontmatter 剥离、图片边界校验、受控
    改名和正文引用重写；publish_note 只做一次 CLI 调用并解析结果。暂存目录放在
    任务目录下的一次性 .feishu-stage-*，finally 清理，绝不删除任务原始产物。
    """
    try:
        token = normalize_feishu_folder(folder_token)  # 调用方之外再兜一道
    except FeishuInputError:
        return sanitized_failure("invalid_folder")
    attempted_at = datetime.now(timezone.utc).isoformat()
    task_dir = Path(task_dir)
    try:
        staging = Path(tempfile.mkdtemp(prefix=".feishu-stage-", dir=task_dir))
    except Exception:
        # 发布是 best-effort：暂存失败也要返回脱敏结果，绝不向调用方抛异常
        return sanitized_failure("upload_failed", attempted_at)
    try:
        safe_title = _safe_document_title(title)
        content_name = _stage_name(title, ".md")
        if staging_builder is not None:
            staging_builder(note_text, task_dir, staging, content_name)
        else:
            (staging / content_name).write_text(note_text, encoding="utf-8")
        create = _run_cli(
            [
                "docs", "+create", "--as", "user",
                "--parent-token", token,
                "--doc-format", "markdown",
                "--title", safe_title,
                "--content", f"@{content_name}",
            ],
            cwd=str(staging),
            timeout=CLI_TIMEOUT_SECONDS,
        )
        envelope = _parse_envelope(create["stdout"]) if create["exit_code"] == 0 else None
        document = _extract_document(envelope, safe_title)
        if document is None:
            return sanitized_failure(_classify_error(create), attempted_at)
        warning = None
        if _has_publication_warnings(envelope):
            warning = {
                "code": "partial_publication",
                "message": _PUBLICATION_WARNING_MESSAGES["partial_publication"],
            }
        return {
            "status": "uploaded",
            "format": "native_docx",
            "document": document,
            "warning": warning,
            "error": None,
            "attempted_at": attempted_at,
        }
    except FeishuMediaError as exc:
        code = exc.code if exc.code in _ERROR_MESSAGES else "upload_failed"
        return sanitized_failure(code, attempted_at)
    except Exception:
        # 暂存/图片准备/CLI 编排里的任何异常都降级为脱敏失败：
        # 本地笔记已经完成并落盘，发布异常绝不能把它改判 failed
        return sanitized_failure("upload_failed", attempted_at)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
