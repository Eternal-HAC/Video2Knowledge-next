from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import io
import ipaddress
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import aiofiles
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .local_security import LOCAL_HOSTS, header_error


# 自己的前端资源不能让操作系统决定类型：Windows 上 mimetypes 先读注册表
# HKCR\<扩展名> 的 "Content Type"，某些软件会把 .js 写成 text/plain，配上本服务的
# nosniff，浏览器直接拒绝执行脚本——页面照常渲染、按钮全废、主题锁死在暗色，
# 且只在注册表被动过的那台机器上出现。
STATIC_MEDIA_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}


class NoCacheStaticFiles(StaticFiles):
    """前端静态资源每次都重新校验，避免浏览器缓存旧版本。

    HTML 入口页更是直接 no-store：旧 HTML 与新版 script.js 混用会导致
    页面元素对不上、按钮全部"点了没反应"，因此入口页不允许任何缓存。
    """

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        suffix = os.path.splitext(str(args[0]))[1].lower() if args else ""
        media_type = STATIC_MEDIA_TYPES.get(suffix)
        if media_type is not None:
            # 304 也要带：浏览器重校验后用这里的头覆盖已缓存那份的头，
            # 否则缓存里那条 text/plain 会靠一次次 304 一直续命。
            response.headers["Content-Type"] = media_type
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response
from pydantic import BaseModel, Field, SecretStr

import product_info
from product_info import API_COMPAT, LEGACY_SERVICE_ID, PRODUCT_NAME, VERSION, env_value

from . import (
    asr_process,
    history_cache,
    media_retention,
    note_integrations,
    note_templates,
    paraformer_asr,
    secret_box,
    task_repository,
)
from .config_store import BiliCredentialsUnavailable, LLM_KEYS_FILE, ConfigStore
from .media_retention import (
    cleanup_expired_task_media,
    is_owned_media_name,
    is_safe_task_id,
    validate_retention_days,
)
from .llm_summarizer import (
    LONG_TRANSCRIPT_CHARACTERS,
    LLMSummarizer,
    default_base_url,
    normalize_endpoint_host,
    utf8_safe,
)
from .bili_login import BiliLoginManager
from .douyin_login import DouyinLoginManager
from .transcript import (
    TranscriptSegment,
    format_timestamp,
    locate_transcript,
    parse_subtitle_payload,
    segments_to_prompt,
    segments_to_srt,
    transcript_quality,
    transcript_revision,
)
from .video_processor import (
    FRAMES_DIR_NAME,
    VideoProcessor,
    VideoSource,
    bilibili_page_url,
    merge_bilibili_pages,
    normalize_video_input,
)
from .paraformer_asr import ParaformerTranscriber
from .whisper_asr import WhisperTranscriber


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
WORKSPACE_DIR = Path(
    env_value("WORKSPACE", str(BASE_DIR / "workspace"))
).resolve()
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
WHISPER_CACHE_DIR = Path(
    os.getenv("WHISPER_CACHE_DIR", str(WORKSPACE_DIR / "_model_cache"))
).resolve()
# workspace/ 下两个面向人的产物目录。转录稿单独一个目录而不是混进 notes/：先转写、后生成
# 笔记的同一视频会各留一份，分开摆一眼看得清。
NOTES_DIR_NAME = "notes"
TRANSCRIPTS_DIR_NAME = "transcripts"
FRONTEND_DIR = BASE_DIR / "frontend"
APP_ICON_PATH = BASE_DIR / "sources" / "icon.png"
FAVICON_PATH = BASE_DIR / "sources" / "icon.ico"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "2048"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
# 超过该体积的本地视频上传后自动提取音频（16kHz m4a）并删除原视频，
# 保留与在线视频一致的轻量工作目录；勾选“视频截图”时保留原视频。
LARGE_UPLOAD_EXTRACT_MB = int(os.getenv("LARGE_UPLOAD_EXTRACT_MB", "300"))
LARGE_UPLOAD_EXTRACT_BYTES = LARGE_UPLOAD_EXTRACT_MB * 1024 * 1024
MAX_CONCURRENT_TASKS = max(1, int(os.getenv("MAX_CONCURRENT_TASKS", "1")))
TASK_HISTORY_LIMIT = max(10, int(os.getenv("TASK_HISTORY_LIMIT", "100")))
ALLOWED_MEDIA_SUFFIXES = {
    ".mp3",
    ".m4a",
    ".wav",
    ".flac",
    ".aac",
    ".mp4",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
}
# 字幕导入只吃带时间轴的这两种：解析器现成，且时间戳是真的，不会像纯文本那样
# 逼着后端编一排假时间码进产物。体积上限单独给一份，不跟媒体上限走。
ALLOWED_SUBTITLE_SUFFIXES = {".srt", ".vtt"}
MAX_SUBTITLE_MB = int(os.getenv("MAX_SUBTITLE_MB", "20"))
MAX_SUBTITLE_BYTES = MAX_SUBTITLE_MB * 1024 * 1024
WHISPER_MODELS = {"tiny", "base", "small", "medium", "large-v3", "turbo", "belle-turbo-zh"}
ASR_MODELS = WHISPER_MODELS | {"paraformer-zh"}
DOUYIN_HINT = (
    "抖音链接解析失败。可以先点击“打开抖音浏览器”，在本机窗口完成登录/验证后重试；"
    "也可能是媒体地址已过期，请重新提交链接。"
)
NOTE_STEP_NAME = "生成笔记"
API_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{4,}")
# 网关报错常把整个请求头或 JSON 回显出来；只认 sk- 前缀会漏掉 Bearer 与非 sk- 格式的凭据。
# 字段名用 \b 框住，否则 "tokenizer.json" 会被当成 "token" + 值咬掉。
SECRET_ECHO_PATTERN = re.compile(
    r"\b(api[_-]?key|authorization|access[_-]?token|refresh[_-]?token|bearer|sessdata|bili_jct)"
    r"\b([\"'’：:=\s]{1,4})([A-Za-z0-9_\-\.]{8,})",
    re.IGNORECASE,
)
# 1.4.1 之前笔记里写的是 ./images/，而磁盘上一直是 frames/；两种都要认，
# 否则历史任务的笔记重新导出时仍然带不回截图。
NOTE_IMAGE_REF_RE = re.compile(
    rf"(!\[[^\]]*\]\()\./(?:{FRAMES_DIR_NAME}|images)/([^)]+)\)"
)

app = FastAPI(title=f"{PRODUCT_NAME} API", version=VERSION)


def is_loopback_client(host: str | None) -> bool:
    if not isinstance(host, str) or not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.lower() == "localhost"
    if address.is_loopback:
        return True
    return bool(address.version == 6 and address.ipv4_mapped and address.ipv4_mapped.is_loopback)


SECURITY_HEADERS = {
    # style-src 放开 inline style：KaTeX 产物的上下标/矩阵定位全靠 inline style 属性。
    # 模型产出的 HTML 仍被前端 DOMPurify 剥掉 style（FORBID_ATTR），放行的只有
    # 本机 KaTeX 渲染结果。注意 CSP 的 hash 与 'unsafe-inline' 并存时后者会被
    # 忽略，必须整体替换；此处与 frontend/index.html 的 meta 是两份独立生效的
    # CSP，改一处就要同步改另一处。
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class LocalSecurityMiddleware:
    """纯 ASGI 中间件：只允许本机回环客户端访问，并为响应附加安全头。

    不用 Starlette 的 BaseHTTPMiddleware（@app.middleware("http")）：
    它对流式响应（如 /mcp/sse 的 SSE 长连接）会在转发响应体时遇到第二次
    http.response.start 而触发 AssertionError，导致 MCP 会话请求直接崩溃；
    这里直接包装 ASGI 应用，流式响应可以原样透传。
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        async def wrapped_send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                existing = {key.lower() for key, _value in headers}
                for key, value in SECURITY_HEADERS.items():
                    if key.lower().encode("latin-1") not in existing:
                        headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        async def reject(status: int, detail: str) -> None:
            await JSONResponse(status_code=status, content={"detail": detail})(scope, receive, wrapped_send)

        client = scope.get("client")
        client_host = client[0] if isinstance(client, (tuple, list)) and client else None
        if not is_loopback_client(client_host):
            await reject(403, f"{PRODUCT_NAME} 仅允许本机访问")
            return
        error = header_error(scope)
        if error == 400:
            await reject(400, "本机请求地址无效")
            return

        # Normalize only Host casing for Starlette's exact allowlist. Do not
        # change Origin, scheme, server or trust Forwarded/X-Forwarded-*.
        checked_scope = dict(scope, headers=[
            (key, value.lower() if key.lower() == b"host" else value)
            for key, value in scope["headers"]
        ])
        entered = False

        async def trusted_app(inner_scope: Any, inner_receive: Any, inner_send: Any) -> None:
            nonlocal entered
            entered = True
            if error is not None:
                await reject(403, "本机请求来源不受信任")
                return
            await self.app(inner_scope, inner_receive, inner_send)

        async def host_send(message: dict[str, Any]) -> None:
            if entered:
                await wrapped_send(message)
            elif message["type"] == "http.response.start":
                # Replace Starlette's plain-text rejection, not business 400s.
                await reject(400, "本机请求地址无效")

        await TrustedHostMiddleware(trusted_app, allowed_hosts=LOCAL_HOSTS, www_redirect=False)(
            checked_scope, receive, host_send
        )


app.add_middleware(LocalSecurityMiddleware)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """没兜住的异常一律回 JSON，而不是 uvicorn 那句纯文本 Internal Server Error。

    前端 `extractErrorMessage` 只在响应是 JSON 时才取得到原因，裸 500 会退化成
    "测试请求失败（HTTP 500）"——群里报障时既分不清是后端崩了、还是端口被别的
    服务占着，也拿不到任何线索。traceback 由 Starlette 原样继续上抛，仍会进
    `_app.log`，这里只负责把话说清楚。
    """
    reason = utf8_safe(f"{type(exc).__name__}: {exc}")[:300]
    return JSONResponse(
        status_code=500,
        content={"detail": f"后端内部错误：{redact_secrets(reason)}（详情见本机 _app.log）"},
    )


FRONTEND_MISSING_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Video2Knowledge 界面没加载出来</title></head>
<body style="font-family:system-ui,sans-serif;max-width:34em;margin:14vh auto;padding:0 1.2em;line-height:1.9">
<h1>界面没加载出来</h1>
<p><strong>这样做就好：</strong>在右下角任务栏找到 Video2Knowledge 图标，右键选「退出」，
再双击打开程序。找不到那个图标的话，直接再双击一次程序也行。</p>
<p>要是反复出现，请把程序目录里 <code>workspace\\_app.log</code> 发给作者，
并说一下你地址栏里的端口号（这台机器上是 __PORT__）。</p>
<p style="color:#666">程序本身在正常运行，只是界面文件没读到——不是端口被别的软件占了。</p>
</body></html>
"""


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> Response:
    """从浏览器地址栏打开的 404 说人话；/api 与 /mcp 仍按原样回 JSON。

    打包版是 onefile，运行时把前端解压到临时目录。那个目录一旦被安全软件或磁盘清理
    删掉，`/api/*` 全部正常而 `/` 只剩一句 `{"detail":"Not Found"}`——连排查的人都会
    误判成端口问题，用户只能靠重启软件碰运气（重启会重新解压，所以"重启就好了"）。
    """
    if exc.status_code == 404 and not request.url.path.startswith(("/api", "/mcp")):
        port = (request.scope.get("server") or (None, None))[1]
        return HTMLResponse(
            status_code=404,
            content=FRONTEND_MISSING_HTML.replace("__PORT__", str(port or "未知")),
        )
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers
    )


video_processor = VideoProcessor(WORKSPACE_DIR)
transcriber = WhisperTranscriber(WHISPER_CACHE_DIR)
paraformer_transcriber = ParaformerTranscriber(WHISPER_CACHE_DIR)


async def run_transcription(
    media_path: Path,
    model_name: str,
    use_gpu: bool,
    title: str | None,
    cancel_event: Any,
    progress_callback: Any = None,
) -> dict:
    """转写入口：打包版交给工人子进程，源码版在原进程里跑。

    CTranslate2 / sherpa-onnx 在打包环境里出过访问违例，崩的是整个进程，
    托盘与界面一起没；正式产物里的转写因此必须死在外头。
    """
    if asr_process.use_child_process():
        return await asr_process.run_in_child(
            media_path, model_name, use_gpu, title, cancel_event, progress_callback
        )
    return await run_transcription_local(
        media_path, model_name, use_gpu, title, cancel_event, progress_callback
    )


async def run_transcription_local(
    media_path: Path,
    model_name: str,
    use_gpu: bool,
    title: str | None,
    cancel_event: Any,
    progress_callback: Any = None,
) -> dict:
    """按所选模型路由转写引擎：paraformer-zh 走 sherpa-onnx，其余走 faster-whisper。

    progress_callback(已转写秒数, 总秒数) 仅 whisper 路径支持（paraformer
    一次性出结果，且 RTF ≈ 0.05 本来就不需要心跳）。
    """
    if model_name == "paraformer-zh":
        return await paraformer_transcriber.transcribe(
            media_path, model_name, use_gpu, initial_prompt=title, cancel_event=cancel_event
        )
    return await transcriber.transcribe(
        media_path,
        model_name,
        use_gpu,
        initial_prompt=title,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
    )


def transcribe_progress_reporter(
    task: dict[str, Any],
    model_name: str,
    page_label: str = "",
    *,
    offset_seconds: float = 0,
    overall_duration: float | None = None,
    aggregate: bool = False,
) -> Any:
    """转写心跳回调：工作线程里只经 call_soon_threadsafe 回主循环改任务状态。

    set_progress 会写任务字典并落盘运行时状态，不能在转写线程里直接调。
    """
    loop = asyncio.get_running_loop()
    started = time.monotonic()
    token = object()
    task["_asr_progress_token"] = token
    last_position = -1.0

    def _clock(seconds: float) -> str:
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def report(position: float, duration: float) -> None:
        try:
            position = float(position)
        except (TypeError, ValueError, OverflowError):
            return
        if not math.isfinite(position) or position < 0 or model_name == "paraformer-zh":
            return
        snapshot = asr_progress_snapshot(
            position=position,
            duration=duration,
            elapsed=time.monotonic() - started,
            offset_seconds=offset_seconds,
            overall_duration=overall_duration,
            aggregate=aggregate,
        )
        total = _clock(snapshot["total_seconds"]) if snapshot["total_seconds"] > 0 else "未知时长"
        message = (
            f"正在转写{page_label}音频（{model_name}）："
            f"已推进到 {_clock(snapshot['processed_seconds'])} / {total}"
        )
        def apply_snapshot() -> None:
            nonlocal last_position
            if (task.get("step") != 4 or task.get("status") != "processing"
                    or task.get("_cancel_requested")
                    or task.get("_asr_progress_token") is not token
                    or position <= last_position):
                return
            last_position = position
            overall_progress = max(
                int(task.get("progress") or 0), int(snapshot["overall_progress"])
            )
            set_progress(
                task,
                4,
                "语音转写",
                overall_progress,
                message,
                phase_progress=snapshot["phase_progress"],
                processed_seconds=snapshot["processed_seconds"],
                total_seconds=snapshot["total_seconds"],
                estimated_remaining_seconds=snapshot["estimated_remaining_seconds"],
            )

        loop.call_soon_threadsafe(apply_snapshot)

    return report


def _finite_nonnegative(value: Any) -> float:
    try:
        number = float(value or 0)
        return max(0.0, number) if math.isfinite(number) else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0


def asr_progress_snapshot(
    *,
    position: float,
    duration: float,
    elapsed: float,
    offset_seconds: float = 0,
    overall_duration: float | None = None,
    aggregate: bool = False,
) -> dict[str, float | int | None]:
    """Map faster-whisper time progress onto the task's ASR progress band.

    ETA stays absent during the noisy first seconds.  The frontend deliberately
    renders the estimate as a range rather than an exact countdown.
    """
    local_position = _finite_nonnegative(position)
    local_duration = _finite_nonnegative(duration)
    if local_duration > 0:
        local_position = min(local_duration, local_position)
    known_total = _finite_nonnegative(overall_duration)
    cumulative = _finite_nonnegative(_finite_nonnegative(offset_seconds) + local_position)
    if known_total > 0:
        processed = min(known_total, cumulative)
        total = known_total
    elif aggregate:
        # A known current-page duration cannot stand in for an unknown whole ASR stage.
        processed, total = cumulative, 0.0
    else:
        processed = local_position
        total = local_duration
    ratio = min(1.0, processed / total) if total > 0 else 0.0
    phase_progress = int(round(ratio * 100)) if total > 0 else None
    overall_progress = int(round(28 + ratio * (49 - 28)))
    eta: float | None = None
    elapsed_seconds = _finite_nonnegative(elapsed)
    if (
        total > processed
        and local_position >= 15
        and elapsed_seconds >= 5
        and local_position > 0
    ):
        rate = local_position / elapsed_seconds
        if rate > 0 and math.isfinite(rate):
            estimate = (total - processed) / rate
            eta = max(0.0, estimate) if math.isfinite(estimate) else None
    return {
        "overall_progress": overall_progress,
        "phase_progress": phase_progress,
        "processed_seconds": processed,
        "total_seconds": total,
        "estimated_remaining_seconds": eta,
    }


bili_login_manager = BiliLoginManager(WORKSPACE_DIR)
douyin_login_manager = DouyinLoginManager(WORKSPACE_DIR)
config_store = ConfigStore(WORKSPACE_DIR)
tasks: dict[str, dict[str, Any]] = {}
running_jobs: dict[str, asyncio.Task[None]] = {}
task_slots = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


class BilibiliCookie(BaseModel):
    sessdata: str = ""
    bili_jct: str = ""
    buvid3: str = ""


class DouyinCookie(BaseModel):
    """浏览器验证后短暂回传的抖音会话字段；不写入任务清单。"""

    model_config = {"extra": "allow"}


class LLMConfigPayload(BaseModel):
    model_type: str = "deepseek"
    api_key: SecretStr
    base_url: str | None = None
    model: str | None = None
    label: str | None = None


class LLMKeyPayload(BaseModel):
    """按接口地址保存一把 API Key：provider + base_url 决定它属于哪个端点。"""

    api_key: SecretStr
    provider: str = "deepseek"
    base_url: str | None = None
    label: str | None = None
    model: str | None = None


class LLMTestPayload(BaseModel):
    """测试连接的可选覆盖参数。

    字段不再与已保存配置逐项混合（那会把一个端点的 Key 配到另一个端点上），
    只有 API Key 会在地址完全一致时复用本机已存的那一把。
    """

    model_type: str | None = None
    api_key: SecretStr | None = None
    base_url: str | None = None
    model: str | None = None


class BiliCredentialsPayload(BaseModel):
    sessdata: str = ""
    bili_jct: str = ""
    buvid3: str = ""


class LLMConfig(BaseModel):
    model_type: str = "deepseek"
    api_key: SecretStr = SecretStr("")
    base_url: str | None = None
    model: str | None = None
    custom_base_url: str | None = None
    custom_model_name: str | None = None


class SummarizeRequest(BaseModel):
    client_request_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    video_url: str = ""
    upload_task_id: str | None = None
    resume_task_id: str | None = None
    processing_mode: Literal["reuse", "restart"] = "reuse"
    # transcript：只做「视频 → 带时间轴转录」，不调用大模型，产物到 transcript.json 为止
    output: Literal["note", "transcript"] = "note"
    note_destination: str | None = None
    summary_style: Literal["detailed", "faithful", "concise"] = "detailed"
    # None/空 = 通用结构化内置模板；提交时解析并整体快照进 task.json（见 note_templates）
    note_template_id: str | None = None
    # 飞书发布：默认关闭；启用即显式同意把最终笔记上传到指定 Drive 文件夹
    feishu_upload_enabled: bool = False
    feishu_folder: str | None = None
    reasoning_effort: Literal["auto", "off", "high", "max"] = "auto"
    prefer_subtitles: bool = True
    include_screenshots: bool = False
    screenshot_interval: int = Field(default=30, ge=5, le=300)
    whisper_model: str = "base"
    use_gpu: bool = False
    # B 站分 P 显式选择（页码从 1 起）；None/空 = 按 URL ?p=N 规则（缺省全部）
    bilibili_pages: list[int] | None = None
    bilibili_cookie: BilibiliCookie | None = None
    douyin_cookie: DouyinCookie | None = None
    llm_config: LLMConfig


class TranscribeRequest(BaseModel):
    """`POST /api/transcribe` 的请求体：刻意没有任何大模型字段。"""

    client_request_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    video_url: str = ""
    upload_task_id: str | None = None
    resume_task_id: str | None = None
    processing_mode: Literal["reuse", "restart"] = "reuse"
    prefer_subtitles: bool = True
    whisper_model: str = "base"
    use_gpu: bool = False
    # B 站分 P 显式选择（页码从 1 起）；None/空 = 按 URL ?p=N 规则（缺省全部）
    bilibili_pages: list[int] | None = None
    bilibili_cookie: BilibiliCookie | None = None
    douyin_cookie: DouyinCookie | None = None


class BiliPagesRequest(BaseModel):
    """`POST /api/bili-pages` 的请求体：提交前预览 B 站分 P 清单。"""

    video_url: str
    bilibili_cookie: BilibiliCookie | None = None


class NoteTemplateCreatePayload(BaseModel):
    """`POST /api/note-templates`：自定义模板的完整字段。"""

    name: str
    description: str = ""
    instructions: str = ""
    layout: str


class NoteTemplateUpdatePayload(BaseModel):
    """`PUT /api/note-templates/{id}`：只更新给出的字段，版本号 +1。"""

    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    layout: str | None = None


class FavoritePayload(BaseModel):
    favorite: bool


class SourceInspectPayload(BaseModel):
    video_url: str


class OpenResultPayload(BaseModel):
    target: Literal["file", "folder"]


def new_task(status: str = "pending", task_id: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "step": 0,
        "step_name": "初始化",
        "progress_message": "等待任务开始",
        "progress": 0,
        "phase_progress": None,
        "processed_seconds": None,
        "total_seconds": None,
        "estimated_remaining_seconds": None,
        "logs": [],
        "result": None,
        "error": None,
        "advisory": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "elapsed_seconds": 0.0,
        "_task_id": task_id,
        "_cancel_requested": False,
        "_cancel_event": threading.Event(),
        "_started_monotonic": time.monotonic(),
    }


def task_elapsed_seconds(task: dict[str, Any]) -> float:
    if task.get("finished_at"):
        return float(task.get("elapsed_seconds") or 0)
    started = task.get("_started_monotonic")
    return max(0.0, time.monotonic() - float(started)) if started is not None else 0.0


def finish_task_timing(task: dict[str, Any]) -> float:
    elapsed = task_elapsed_seconds(task)
    task["elapsed_seconds"] = elapsed
    task["finished_at"] = datetime.now(timezone.utc).isoformat()
    clear_phase_progress(task)
    return elapsed


def clear_phase_progress(task: dict[str, Any]) -> None:
    task.pop("_asr_progress_token", None)
    for key in (
        "phase_progress",
        "processed_seconds",
        "total_seconds",
        "estimated_remaining_seconds",
    ):
        task[key] = None


def set_progress(
    task: dict[str, Any],
    step: int,
    name: str,
    progress: int,
    message: str,
    *,
    phase_progress: int | None = None,
    processed_seconds: float | None = None,
    total_seconds: float | None = None,
    estimated_remaining_seconds: float | None = None,
) -> None:
    if task.get("_cancel_requested") or task.get("status") in {"completed", "failed", "cancelled", "cancelling"}:
        return
    if processed_seconds is None:
        task.pop("_asr_progress_token", None)
    task.update(step=step, step_name=name, progress=progress, progress_message=message)
    task.update(
        phase_progress=phase_progress,
        processed_seconds=processed_seconds,
        total_seconds=total_seconds,
        estimated_remaining_seconds=estimated_remaining_seconds,
    )
    task["logs"].append(message)
    task_id = task.get("_task_id")
    if task_id:
        persist_task_runtime(str(task_id))


def task_directory(task_id: str) -> Path:
    candidate = (WORKSPACE_DIR / task_id).resolve()
    if candidate.parent != WORKSPACE_DIR:
        raise ValueError("非法任务 ID")
    return candidate


def uploaded_media_owner_id(uploaded_file_path: Any) -> str | None:
    """上传媒体实际落盘所属的任务目录名（位于 WORKSPACE_DIR 直接子目录内的安全 task_id）。

    上传端点把文件写成 WORKSPACE_DIR/<upload_task_id>/input.<ext>；复用该媒体的
    任务并不拥有这份文件，清理时必须保护真正的属主目录，而不是调用方自己的 id。
    只有落在 WORKSPACE_DIR 直接子目录且目录名是安全 task_id 时才返回，否则 None。
    """
    if not isinstance(uploaded_file_path, str) or not uploaded_file_path:
        return None
    try:
        resolved = Path(uploaded_file_path).resolve()
        workspace = WORKSPACE_DIR.resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    parent = resolved.parent
    if parent.parent != workspace:
        return None
    return parent.name if is_safe_task_id(parent.name) else None


def cleanup_successful_task_media(task_id: str) -> tuple[list[str], list[str]]:
    """成功笔记任务的媒体清理：只删除本任务目录直属的已知媒体文件。

    返回 (removed_names, warnings)。只列目录第一层、只按文件名白名单匹配，
    不递归、不碰其他任务。符号链接、同名目录、归属无法确认的文件一律保留并
    记 warning。普通清理失败绝不抛异常——笔记已经生成，不能因此改判失败。
    """
    removed: list[str] = []
    warnings: list[str] = []
    try:
        directory = task_directory(task_id)
    except ValueError:
        return removed, ["任务 ID 非法，跳过媒体清理"]
    try:
        children = list(directory.iterdir())
    except OSError:
        return removed, ["无法列出任务目录，媒体未清理"]
    for child in sorted(children, key=lambda path: path.name):
        name = child.name
        if not is_owned_media_name(name):
            continue
        try:
            if child.is_symlink() or not child.is_file():
                warnings.append(f"保留非常规文件：{name}")
                continue
            if child.resolve().parent != directory:
                warnings.append(f"保留无法确认归属的文件：{name}")
                continue
            child.unlink(missing_ok=True)
            removed.append(name)
        except OSError:
            warnings.append(f"未能清理媒体文件：{name}")
    return removed, warnings


def get_template_store() -> note_templates.TemplateStore:
    """自定义模板存工作区内（已被 .gitignore 忽略），每次调用按当前 WORKSPACE_DIR 解析。"""
    return note_templates.TemplateStore(WORKSPACE_DIR / "note_templates")


def _merge_task_manifest(task_id: str, key: str, value: Any) -> None:
    task_repository.merge(task_directory(task_id) / "task.json", {key: value})


def resolve_feishu_target(task_id: str, request: SummarizeRequest) -> str | None:
    """取提交时快照的飞书目标 token；直接调用（无 manifest）时按请求现场归一。"""
    manifest = read_task_manifest(task_id)
    target = manifest.get("feishu_upload")
    if isinstance(target, dict) and isinstance(target.get("folder_token"), str):
        return target["folder_token"]
    if request.feishu_upload_enabled and (request.feishu_folder or "").strip():
        try:
            return note_integrations.normalize_feishu_folder(request.feishu_folder or "")
        except note_integrations.FeishuInputError:
            return None
    return None


def resolve_task_template_snapshot(
    task_id: str, request: SummarizeRequest
) -> dict[str, Any]:
    """取任务提交时落盘的模板快照；直接调用（无 manifest）时按请求现场解析。

    快照包含模板全文（含布局与指令），之后的模板修改/删除不改写已排队任务与历史任务。
    """
    manifest = read_task_manifest(task_id)
    snapshot = manifest.get("note_template_snapshot")
    if isinstance(snapshot, dict) and snapshot.get("id") and isinstance(
        snapshot.get("layout"), str
    ):
        return dict(snapshot)
    store = get_template_store()
    template = store.get((request.note_template_id or "").strip())
    if template is None:
        template = store.get(note_templates.DEFAULT_TEMPLATE_ID)
    if template is None:  # 内置模板永远存在，这只是防御
        raise RuntimeError("内置笔记模板缺失")
    return template.snapshot()


def persist_task_runtime(task_id: str) -> None:
    """Persist non-secret runtime state atomically beside task artifacts."""
    task = tasks.get(task_id)
    if not task:
        return
    directory = task_directory(task_id)
    if not directory.is_dir():
        return
    result = task.get("result")
    result_metadata = None
    if isinstance(result, dict):
        result_metadata = {key: value for key, value in result.items() if key != "markdown"}
    runtime = {
        "status": task.get("status"),
        "step": task.get("step", 0),
        "step_name": task.get("step_name", ""),
        "progress": task.get("progress", 0),
        "progress_message": task.get("progress_message", ""),
        "phase_progress": task.get("phase_progress"),
        "processed_seconds": task.get("processed_seconds"),
        "total_seconds": task.get("total_seconds"),
        "estimated_remaining_seconds": task.get("estimated_remaining_seconds"),
        "logs": list(task.get("logs", []))[-200:],
        "error": task.get("error"),
        "created_at": task.get("created_at"),
        "finished_at": task.get("finished_at"),
        "elapsed_seconds": task_elapsed_seconds(task),
        "result": result_metadata,
    }
    def save(payload: dict[str, Any]) -> None:
        # Do not let a delayed progress snapshot replace a persisted terminal state.
        previous = payload.get("runtime")
        if (
            isinstance(previous, dict)
            and previous.get("status") in {"completed", "failed", "cancelled"}
            and runtime.get("status") in {"pending", "queued", "processing", "cancelling"}
        ):
            return
        payload.setdefault("task_id", task_id)
        payload["runtime"] = {**(previous if isinstance(previous, dict) else {}), **runtime}
    task_repository.update(directory / "task.json", save)


def raise_if_cancel_requested(task: dict[str, Any]) -> None:
    if task.get("_cancel_requested"):
        raise asyncio.CancelledError


# 任务结果系统通知：由启动器把托盘气泡接进来（打包模式才有效），
# backend 不直接依赖 pystray，避免引入循环依赖。
_task_notify_hook: Callable[[str, str], None] | None = None


def register_task_notify(callback: Callable[[str, str], None]) -> None:
    """注册通知回调：callback(title, message)。"""
    global _task_notify_hook
    _task_notify_hook = callback


def notify_task(title: str, message: str) -> None:
    """发送系统通知；异步执行且绝不影响任务主流程。"""
    callback = _task_notify_hook
    if callback is None:
        return

    def _run() -> None:
        try:
            callback(title, message)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def normalize_source_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    hostname = (parsed.hostname or "").lower()
    netloc = hostname
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"
    path = parsed.path.rstrip("/")
    query = "" if hostname == "bilibili.com" or hostname.endswith(".bilibili.com") else parsed.query
    return urlunsplit((parsed.scheme.lower(), netloc, path, query, ""))


def classify_source_url(value: str) -> dict[str, str]:
    """Classify a URL for UI guidance without contacting the platform."""
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("视频链接必须使用 http 或 https")
    host = parsed.hostname.lower().rstrip(".")

    def matches(domain: str) -> bool:
        return host == domain or host.endswith(f".{domain}")

    if matches("bilibili.com") or host == "b23.tv":
        platform, label, support = "bilibili", "B站", "focused"
    elif matches("douyin.com") or matches("iesdouyin.com"):
        platform, label, support = "douyin", "抖音", "focused"
    elif matches("youtube.com") or host == "youtu.be":
        platform, label, support = "youtube", "YouTube", "focused"
    elif matches("tiktok.com"):
        platform, label, support = "tiktok", "TikTok", "generic"
    elif matches("xiaohongshu.com") or matches("xhslink.com"):
        platform, label, support = "xiaohongshu", "小红书", "generic"
    else:
        platform, label, support = "other", "其他平台", "generic"
    return {
        "platform": platform,
        "platform_label": label,
        "support_level": support,
    }


def _history_platform(manifest: dict[str, Any], task: dict[str, Any] | None) -> str:
    if manifest.get("subtitle_import"):
        return "subtitle"
    source_url = str(manifest.get("source_url") or "").strip()
    if source_url:
        try:
            platform = classify_source_url(source_url)["platform"]
        except ValueError:
            platform = "other"
        return platform if platform in {"bilibili", "douyin", "youtube"} else "other"
    source = str(manifest.get("source") or "").strip().lower()
    if not source and isinstance(task, dict):
        result = task.get("result")
        if isinstance(result, dict):
            source = str(result.get("source") or "").strip().lower()
    if source in {"bilibili", "douyin", "youtube", "local", "subtitle"}:
        return source
    if manifest.get("uploaded_filename"):
        return "local"
    return "other"


def _read_history_manifest(task_id: str) -> tuple[Path | None, dict[str, Any]]:
    if not is_safe_task_id(task_id):
        return None, {}
    try:
        directory = task_directory(task_id)
    except ValueError:
        return None, {}
    # Reuse the validated canonical directory; resolving it again does not
    # provide an atomic filesystem snapshot and doubles per-record path work.
    return directory, task_repository.read(directory / "task.json")


def _project_history_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Retain disk summary inputs only, never URLs, bodies, logs or full results."""
    if not manifest:
        return {}
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    result = runtime.get("result") if isinstance(runtime.get("result"), dict) else {}
    snapshot = manifest.get("note_template_snapshot")
    return {
        "title": manifest.get("title") or manifest.get("uploaded_filename") or "未命名任务",
        "runtime_result_title": result.get("title"),
        "output": manifest.get("output") or "note",
        "origin": manifest.get("origin"),
        "favorite": manifest.get("favorite") is True,
        "template_name": str(snapshot.get("name") or "") if isinstance(snapshot, dict) else "",
        "created_at": runtime.get("created_at") or manifest.get("created_at") or "",
        "finished_at": runtime.get("finished_at"),
        "status": runtime.get("status") or "failed",
        "step_name": runtime.get("step_name"),
        "progress": runtime.get("progress", 0),
        "elapsed_seconds": runtime.get("elapsed_seconds") or 0,
        "platform": _history_platform(manifest, None),
        "needs_live_source": (
            not manifest.get("subtitle_import")
            and not str(manifest.get("source_url") or "").strip()
            and not str(manifest.get("source") or "").strip()
        ),
    }


def _summarize_history_projection(
    task_id: str, directory: Path | None, projection: dict[str, Any],
    task: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not projection and not isinstance(task, dict):
        return None
    live = task or {}
    result = live.get("result")
    # An explicitly empty live result suppresses the persisted result title too.
    result_title = result.get("title") if isinstance(result, dict) else projection.get("runtime_result_title")
    platform = projection.get("platform", "other")
    if projection.get("needs_live_source", True) and isinstance(result, dict):
        source = str(result.get("source") or "").strip().lower()
        if source in {"bilibili", "douyin", "youtube", "local", "subtitle"}:
            platform = source
    elapsed = (
        task_elapsed_seconds(task)
        if isinstance(task, dict)
        else float(projection.get("elapsed_seconds") or 0)
    )
    return {
        "task_id": task_id,
        "status": str(live.get("status") or projection.get("status") or "failed"),
        "step_name": live.get("step_name") or projection.get("step_name"),
        "progress": live.get("progress", projection.get("progress", 0)),
        "output": str(live.get("output") or projection.get("output") or "note"),
        "title": str(result_title or projection.get("title") or "未命名任务"),
        "created_at": str(live.get("created_at") or projection.get("created_at") or ""),
        "finished_at": live.get("finished_at") or projection.get("finished_at"),
        "elapsed_seconds": elapsed,
        "platform": platform,
        "template_name": projection.get("template_name", ""),
        "favorite": projection.get("favorite") is True,
        "has_transcript": bool(directory and (directory / "transcript.json").is_file()),
    }


def _history_task_record(task_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Fresh reads for history, eligibility and reuse."""
    directory, manifest = _read_history_manifest(task_id)
    return _summarize_history_projection(
        task_id, directory, _project_history_manifest(manifest), tasks.get(task_id)
    ), manifest


def _cached_history_task_record(task_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Experimental reader, enabled only by isolated tests/benchmarks."""
    directory = None
    if is_safe_task_id(task_id):
        try:
            directory = task_directory(task_id)
        except ValueError:
            pass
    projection: dict[str, Any] = {}
    if directory is not None:
        loaded = False

        def load(path: Path) -> dict[str, Any]:
            nonlocal loaded
            loaded = True
            return _project_history_manifest(task_repository.read(path))

        if directory == WORKSPACE_DIR / task_id:
            projection = history_cache.history_summaries.read(WORKSPACE_DIR, task_id, load)
        # Cache admission is stricter than the legacy directory reader. When it
        # declines before loading, retain that reader's behavior and protections.
        # Never reuse a value rejected by the cache's post-read identity check.
        if not loaded and not projection:
            projection = load(directory / "task.json")
    return _summarize_history_projection(task_id, directory, projection, tasks.get(task_id)), projection


def _list_history_task_record(task_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    # G5.1's cached reader regressed latency. Keep production on fresh reads;
    # isolated benchmarks may replace this list-only seam, never eligibility.
    return _history_task_record(task_id)


def history_task_summary(task_id: str) -> dict[str, Any] | None:
    summary, _ = _history_task_record(task_id)
    return summary


def iter_history_task_ids() -> list[str]:
    identifiers = set(tasks)
    try:
        for directory in WORKSPACE_DIR.iterdir():
            if (
                directory.is_dir()
                and is_safe_task_id(directory.name)
                and (directory / "task.json").is_file()
            ):
                identifiers.add(directory.name)
    except OSError:
        pass
    return list(identifiers)


def restore_task_on_demand(task_id: str) -> dict[str, Any] | None:
    """Restore one manifest-backed task without eagerly loading all history notes."""
    directory, manifest = _read_history_manifest(task_id)
    if directory is None or not manifest:
        return None
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    transcript_only = manifest.get("output") == "transcript"
    notes_path = directory / "notes.md"
    uploaded_media = next(
        (path for path in directory.glob("input.*") if path.is_file()), None
    )
    status = str(runtime.get("status") or "")
    interrupted = status in {"pending", "queued", "processing", "cancelling"}
    if notes_path.is_file() or (
        transcript_only and load_transcript_result(directory) is not None
    ):
        status = "completed"
    elif interrupted:
        status = "failed"
    elif status not in {"failed", "cancelled", "uploaded"}:
        status = "uploaded" if uploaded_media else "failed"

    task = new_task(status=status, task_id=task_id)
    task["_started_monotonic"] = None
    task.update(
        step=int(runtime.get("step") or 0),
        step_name=str(runtime.get("step_name") or "已恢复"),
        progress=int(runtime.get("progress") or (100 if status == "completed" else 0)),
        progress_message=str(runtime.get("progress_message") or ""),
        phase_progress=runtime.get("phase_progress"),
        processed_seconds=runtime.get("processed_seconds"),
        total_seconds=runtime.get("total_seconds"),
        estimated_remaining_seconds=runtime.get("estimated_remaining_seconds"),
        logs=list(runtime.get("logs") or []),
        error=runtime.get("error"),
        created_at=runtime.get("created_at") or manifest.get("created_at"),
        finished_at=runtime.get("finished_at"),
        elapsed_seconds=float(runtime.get("elapsed_seconds") or 0),
        output=str(manifest.get("output") or "note"),
        _origin=str(manifest.get("origin") or "agent"),
    )
    for key in ("feishu_upload", "feishu_publication"):
        value = manifest.get(key)
        if isinstance(value, dict):
            task[key] = value
    if interrupted:
        task.update(
            step_name="服务已重启",
            error="任务因服务重启而中断；已有转录和音频仍可复用",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        task["logs"].append("服务重启时任务尚未结束，已标记为中断")
    if status == "uploaded":
        if uploaded_media:
            task["uploaded_file_path"] = str(uploaded_media)
            task["uploaded_filename"] = manifest.get("uploaded_filename") or uploaded_media.name
        elif manifest.get("subtitle_import"):
            task["subtitle_import"] = True
            task["uploaded_filename"] = manifest.get("uploaded_filename")
    if status == "completed" and transcript_only:
        result = dict(runtime.get("result") or {})
        result.update(
            title=result.get("title") or manifest.get("title") or "",
            output="transcript",
            output_directory=str(directory),
            processing_seconds=task["elapsed_seconds"],
        )
        task["result"] = result
        task["finished_at"] = task["finished_at"] or datetime.now(timezone.utc).isoformat()
    elif status == "completed":
        try:
            markdown = notes_path.read_text(encoding="utf-8")
        except OSError:
            return None
        result = dict(runtime.get("result") or {})
        result.update(
            title=result.get("title") or manifest.get("title") or "video-notes",
            markdown=markdown,
            output_directory=str(directory),
            processing_seconds=task["elapsed_seconds"],
        )
        task["result"] = result
        task["finished_at"] = task["finished_at"] or datetime.now(timezone.utc).isoformat()
    tasks[task_id] = task
    if interrupted:
        persist_task_runtime(task_id)
    return task


def source_url_from_task(task_dir: Path) -> str | None:
    manifest_path = task_dir / "task.json"
    if manifest_path.is_file():
        try:
            value = task_repository.read(manifest_path).get("source_url")
            if value:
                return str(value)
        except (OSError, ValueError, TypeError):
            pass

    notes_path = task_dir / "notes.md"
    if notes_path.is_file():
        try:
            for line in reversed(notes_path.read_text(encoding="utf-8").splitlines()):
                if line.startswith("来源："):
                    return line.removeprefix("来源：").strip()
        except OSError:
            pass
    return None


def find_reusable_task(source_url: str) -> str | None:
    normalized_source = normalize_source_url(source_url)
    candidates: list[tuple[float, Path]] = []
    try:
        entries = list(WORKSPACE_DIR.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not is_safe_task_id(entry.name):
            continue
        try:
            candidate = task_directory(entry.name)
            if not candidate.is_dir():
                continue
            candidates.append((candidate.stat().st_mtime, candidate))
        except (OSError, ValueError, RuntimeError):
            continue
    for _mtime, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
        if load_transcript_result(candidate) is None:
            continue
        existing_source = source_url_from_task(candidate)
        if existing_source and normalize_source_url(existing_source) == normalized_source:
            return candidate.name
    return None


def load_transcript_result(task_dir: Path) -> dict[str, Any] | None:
    path = task_dir / "transcript.json"
    if not path.is_file():
        return None
    try:
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("segments"), list):
            return None
        if any(payload.get(key) is not None and not isinstance(payload[key], str) for key in ("language", "source")):
            return None
        segments = []
        for item in payload["segments"]:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                return None
            if any(isinstance(item.get(key), bool) for key in ("start", "end")):
                return None
            start, end = float(item["start"]), float(item["end"])
            if not all(math.isfinite(value) for value in (start, end)) or start < 0 or end < start:
                return None
            if item["text"].strip():
                segments.append(TranscriptSegment(start, end, item["text"]))
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None
    if not segments:
        return None
    return {
        "segments": segments,
        "language": payload.get("language") or "unknown",
        "source": payload.get("source") or "reused_transcript",
        "quality": payload.get("quality"),
    }


def load_reused_video_info(
    task_dir: Path,
    transcript_result: dict[str, Any],
    source_url: str | None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    manifest_path = task_dir / "task.json"
    if manifest_path.is_file():
        try:
            manifest = task_repository.read(manifest_path)
        except (OSError, ValueError, TypeError):
            pass

    title = str(manifest.get("title") or "").strip()
    if not title:
        notes_path = task_dir / "notes.md"
        try:
            # 1.4.3 起笔记带 YAML Frontmatter，标题行不再一定是第一行
            for line in notes_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# 视频笔记：《") and line.endswith("》"):
                    title = line.removeprefix("# 视频笔记：《")[:-1]
                    break
        except (OSError, IndexError):
            pass
    if not title:
        title = f"已恢复任务 {task_dir.name}"

    segments: list[TranscriptSegment] = transcript_result["segments"]
    duration = float(manifest.get("duration") or max(segment.end for segment in segments))
    if source_url:
        source = video_processor.detect_source(source_url).value
    else:
        source = VideoSource.LOCAL.value
    return {
        "title": title,
        "source": source,
        "duration": duration,
        "owner": str(manifest.get("owner") or ""),
        "upload_date": str(manifest.get("upload_date") or ""),
        "timestamp": manifest.get("timestamp") or 0,
        "view_count": manifest.get("view_count") or 0,
        "like_count": manifest.get("like_count") or 0,
        "bili_selected_pages": manifest.get("bili_selected_pages"),
        "bili_total_pages": manifest.get("bili_total_pages"),
        "description": "",
    }


def update_task_manifest(task_id: str, info: dict[str, Any]) -> None:
    payload = dict(
        title=info.get("title"),
        owner=info.get("owner"),
        duration=info.get("duration"),
        source=info.get("source"),
        upload_date=info.get("upload_date"),
        timestamp=info.get("timestamp"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
    )
    # 分 P 信息只在 B 站多 P 时才有，缺键的旧任务重开时不能把它写空。
    # bilibili_pages 仍是请求里的 list[int]|None，realized 信息单独用新键。
    for key in ("bili_selected_pages", "bili_total_pages"):
        if info.get(key) is not None:
            payload[key] = info[key]
    task_repository.merge(task_directory(task_id) / "task.json", payload)


def read_task_manifest(task_id: str) -> dict[str, Any]:
    return task_repository.read(task_directory(task_id) / "task.json")


def write_task_manifest(
    task_id: str,
    request: SummarizeRequest,
    reused_task_id: str | None,
    origin: str,
    template_snapshot: dict[str, Any] | None = None,
    feishu_target: dict[str, Any] | None = None,
    submission: dict[str, Any] | None = None,
) -> None:
    uploaded_filename = tasks.get(task_id, {}).get("uploaded_filename")
    payload = {
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_url": request.video_url if request.video_url and not uploaded_filename else None,
        "normalized_source_url": (
            normalize_source_url(request.video_url)
            if request.video_url and not uploaded_filename
            else None
        ),
        "uploaded_filename": uploaded_filename,
        "processing_mode": request.processing_mode,
        "output": request.output,
        "note_destination": request.note_destination,
        # origin=agent 的纯转录任务不进网页端历史（见 list_recent_tasks）
        "origin": origin,
        "summary_style": request.summary_style,
        "reasoning_effort": request.reasoning_effort,
        "reused_task_id": reused_task_id,
        # 分 P 勾选随任务落盘：同一视频重新处理时，/bili-pages 用它预勾上次的范围
        "bilibili_pages": getattr(request, "bilibili_pages", None),
    }
    if reused_task_id:
        parent = read_task_manifest(reused_task_id)
        payload["parent_task_id"] = reused_task_id
        payload["transcript_ref"] = {"task_id": reused_task_id, "filename": "transcript.json"}
        if not payload["source_url"]:
            payload["source_url"] = parent.get("source_url")
            payload["normalized_source_url"] = parent.get("normalized_source_url")
        if parent.get("subtitle_import"):
            payload["subtitle_import"] = True
    if tasks.get(task_id, {}).get("subtitle_import"):
        # 字幕上传任务在 submit 时会重写 manifest：标记必须跟着写回去，
        # 否则服务重启后来源身份丢失，只剩内存里的任务能跑。
        payload["subtitle_import"] = True
    if template_snapshot is not None:
        payload["note_template"] = {
            "id": template_snapshot.get("id"),
            "version": template_snapshot.get("version"),
        }
        payload["note_template_snapshot"] = template_snapshot
    if feishu_target is not None:
        # 只快照归一后的目标 token；认证状态绝不落盘
        payload["feishu_upload"] = feishu_target
    if submission is not None:
        payload["submission"] = submission
    task_repository.merge(task_directory(task_id) / "task.json", payload)


def write_upload_manifest(
    task_id: str, filename: str, *, subtitle_import: bool = False
) -> None:
    payload = {
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_url": None,
        "uploaded_filename": filename,
    }
    if subtitle_import:
        payload["subtitle_import"] = True
    task_repository.merge(task_directory(task_id) / "task.json", payload)


def probe_note_destination(path: Path) -> None:
    """用一次不覆盖的临时写入确认目录当前可写。"""
    probe = path / f".video2knowledge-write-test-{uuid.uuid4().hex}"
    try:
        with probe.open("x", encoding="utf-8") as handle:
            handle.write("ok")
    finally:
        probe.unlink(missing_ok=True)


def validate_note_destination(value: str) -> str | None:
    """在任务创建前规范化并验证可选的最终笔记目录。"""
    cleaned = value.strip()
    if not cleaned:
        return None
    path = Path(cleaned)
    if not path.is_absolute():
        raise HTTPException(status_code=422, detail="笔记目的地必须是绝对路径")
    try:
        if path.exists() and not path.is_dir():
            raise HTTPException(status_code=422, detail="笔记目的地必须是目录")
        path.mkdir(parents=True, exist_ok=True)
        resolved = path.resolve(strict=True)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(
            status_code=422,
            detail="无法创建笔记目的地：请检查父目录和写入权限",
        ) from exc
    try:
        probe_note_destination(resolved)
    except OSError as exc:
        raise HTTPException(
            status_code=422,
            detail="笔记目的地不可写：请检查目录写入权限",
        ) from exc
    return str(resolved)


@app.post("/api/summarize")
async def start_summarize(request: SummarizeRequest) -> dict[str, Any]:
    return await submit_video_task(request, origin="web")


def submission_fingerprint(request: SummarizeRequest, origin: str) -> str:
    """Compare request intent only. Never hash Key/Cookie values, even indirectly."""
    values = request.model_dump(exclude={
        "client_request_id", "bilibili_cookie", "douyin_cookie", "llm_config",
    })
    values["llm_config"] = request.llm_config.model_dump(exclude={"api_key"})
    values["origin"] = origin
    encoded = json.dumps(values, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def replay_submission(request_id: str, fingerprint: str) -> dict[str, Any] | None:
    # Manifests remain the source of truth. No unbounded in-memory idempotency index.
    for task_id in iter_history_task_ids():
        manifest = read_task_manifest(task_id)
        submission = manifest.get("submission")
        if not isinstance(submission, dict) or submission.get("client_request_id") != request_id:
            continue
        if submission.get("fingerprint") != fingerprint:
            raise HTTPException(status_code=409, detail="该请求 ID 已用于不同参数；显式新建任务请使用新的 ID")
        return {"task_id": task_id, "reused_task_id": manifest.get("reused_task_id"), "replayed": True}
    return None


@app.get("/api/submission/{client_request_id}")
async def lookup_submission(client_request_id: str) -> dict[str, Any]:
    """Resolve an uncertain submission without repeating a paid task request."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", client_request_id):
        raise HTTPException(status_code=422, detail="非法请求 ID")
    for task_id in iter_history_task_ids():
        manifest = read_task_manifest(task_id)
        submission = manifest.get("submission")
        if isinstance(submission, dict) and submission.get("client_request_id") == client_request_id:
            return {"task_id": task_id, "reused_task_id": manifest.get("reused_task_id"), "replayed": True}
    raise HTTPException(status_code=404, detail="未找到该提交；请确认服务和工作区未改变后再新建任务")


@app.post("/api/transcribe")
async def start_transcribe(request: TranscribeRequest) -> dict[str, Any]:
    """只做「视频 → 带时间轴转录」，全程不调用大模型，本机没有 API Key 也能用。

    给自带模型的 agent 用：拿原料自己组织笔记，不必先给本机配一把 Key。
    复用同一套任务机制（进度、取消、并发闸门、产物复用），产物停在
    `transcript.json` / `transcript.md`；正文用 `GET /api/task/{id}/transcript` 取。
    """
    return await submit_video_task(
        SummarizeRequest(
            **request.model_dump(), output="transcript", llm_config=LLMConfig()
        ),
        origin="agent",
    )


async def submit_video_task(
    request: SummarizeRequest, origin: str
) -> dict[str, Any]:
    # There is no await between replay lookup and durable reservation. The single
    # backend event loop serializes submissions, including MCP in-process calls.
    request = request.model_copy(deep=True)
    fingerprint = submission_fingerprint(request, origin) if request.client_request_id else None
    if request.client_request_id:
        replay = replay_submission(request.client_request_id, fingerprint)
        if replay is not None:
            return replay
    if request.whisper_model not in ASR_MODELS:
        raise HTTPException(status_code=422, detail="不支持的转写模型")
    if request.output == "note" and request.note_destination:
        request.note_destination = validate_note_destination(request.note_destination)
    else:
        request.note_destination = None
    uploaded_task = None
    if request.upload_task_id:
        # 本地上传的媒体位置记在上传任务上；此时 video_url 是后端目录里的文件路径，
        # 不是链接，不能进链接校验（否则必 422）。
        uploaded_task = tasks.get(request.upload_task_id) or restore_task_on_demand(request.upload_task_id)
        if not uploaded_task or uploaded_task.get("status") != "uploaded":
            raise HTTPException(status_code=400, detail="上传任务不存在或已经处理")
        request.video_url = ""
    elif request.video_url:
        normalized = normalize_video_input(request.video_url)
        if not normalized:
            raise HTTPException(
                status_code=422,
                detail="无法识别视频链接：支持 http(s) 链接，或包含 B 站/抖音链接的分享文本",
            )
        request.video_url = normalized
    reused_task_id = request.resume_task_id
    if request.processing_mode == "restart":
        reused_task_id = None
    elif not reused_task_id and request.video_url:
        reused_task_id = find_reusable_task(request.video_url)

    if reused_task_id:
        try:
            resume_dir = task_directory(reused_task_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="非法恢复任务 ID") from exc
        if not resume_dir.is_dir():
            raise HTTPException(status_code=404, detail="要继续的任务目录不存在")
        if load_transcript_result(resume_dir) is None:
            raise HTTPException(status_code=409, detail="原任务缺少完整可用的转录；请检查历史任务或显式从头处理")
        original_source = source_url_from_task(resume_dir)
        if request.video_url and original_source and normalize_source_url(request.video_url) != normalize_source_url(original_source):
            raise HTTPException(status_code=409, detail="恢复任务的来源与当前链接不同；请打开原任务或显式从头处理")

    template_snapshot = None
    if request.output == "note":
        template_id = (request.note_template_id or "").strip()
        template = get_template_store().get(template_id or note_templates.DEFAULT_TEMPLATE_ID)
        if template is None:
            raise HTTPException(status_code=404, detail="笔记模板不存在，请刷新模板列表后重试")
        template_snapshot = template.snapshot()

    feishu_target: dict[str, Any] | None = None
    if request.output == "note" and request.feishu_upload_enabled:
        # 在排队前阻断：目标非法、CLI 不可用、user 登录不就绪或缺少最小 scope
        try:
            folder_token = note_integrations.normalize_feishu_folder(
                request.feishu_folder or ""
            )
        except note_integrations.FeishuInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        readiness = note_integrations.check_feishu_readiness()
        if not (readiness["installed"] and readiness["capable"]):
            raise HTTPException(
                status_code=400,
                detail="未检测到可用的 lark-cli（缺少 docs 命令），无法创建飞书在线文档",
            )
        if readiness["auth"] != "ready" or not readiness["scopes_ready"]:
            raise HTTPException(
                status_code=400,
                detail="飞书 user 登录不可用或缺少在线文档发布权限，请先用 lark-cli 完成授权后重试",
            )
        feishu_target = {"folder_token": folder_token}

    task_id = request.upload_task_id or str(uuid.uuid4())
    if uploaded_task is not None:
        tasks[task_id] = new_task(task_id=task_id)
        tasks[task_id]["uploaded_file_path"] = uploaded_task.get("uploaded_file_path")
        tasks[task_id]["uploaded_filename"] = uploaded_task.get("uploaded_filename")
        if uploaded_task.get("subtitle_import"):
            tasks[task_id]["subtitle_import"] = True
            # 字幕导入没有媒体可抽帧：勾选状态在这里就否掉，别留到第 5 步再报"没有视频"
            request.include_screenshots = False
    else:
        if request.video_url:
            try:
                video_processor.detect_source(request.video_url)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        elif not reused_task_id:
            raise HTTPException(status_code=422, detail="请提供视频链接、上传文件或可继续的任务")
        tasks[task_id] = new_task(task_id=task_id)
        task_directory(task_id).mkdir(parents=True, exist_ok=False)

    tasks[task_id]["resume_task_id"] = reused_task_id
    tasks[task_id]["output"] = request.output
    tasks[task_id]["_origin"] = origin
    if reused_task_id:
        old_task = tasks.get(reused_task_id, {})
        if old_task.get("uploaded_file_path"):
            tasks[task_id]["uploaded_file_path"] = old_task["uploaded_file_path"]
        old_filename = old_task.get("uploaded_filename") or read_task_manifest(
            reused_task_id
        ).get("uploaded_filename")
        if old_filename:
            tasks[task_id]["uploaded_filename"] = old_filename
        if read_task_manifest(reused_task_id).get("subtitle_import"):
            tasks[task_id]["subtitle_import"] = True
            request.include_screenshots = False
        tasks[task_id]["logs"].append(f"将从任务 {reused_task_id} 复用已有产物")
    write_task_manifest(
        task_id, request, reused_task_id, origin, template_snapshot, feishu_target,
        submission={
            "client_request_id": request.client_request_id, "fingerprint": fingerprint,
        } if request.client_request_id else None,
    )
    persist_task_runtime(task_id)

    job = asyncio.create_task(run_queued_video_task(task_id, request))
    running_jobs[task_id] = job
    job.add_done_callback(lambda _job, current_id=task_id: running_jobs.pop(current_id, None))
    return {"task_id": task_id, "reused_task_id": reused_task_id}


def task_status_payload(task_id: str, task: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in task.items() if not key.startswith("_")}
    payload["elapsed_seconds"] = task_elapsed_seconds(task)
    manifest = read_task_manifest(task_id)
    if task.get("status") in {"failed", "cancelled", "completed"}:
        payload["recovery"] = task_recovery_summary(task_id, task, manifest)
    source_url = str(manifest.get("source_url") or "")
    payload["source_url"] = source_url if source_url.startswith(("http://", "https://")) else None
    payload["uploaded_filename"] = payload.get("uploaded_filename") or manifest.get(
        "uploaded_filename"
    )
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    payload["download_name"] = download_stem(
        str(
            result.get("title")
            or manifest.get("title")
            or manifest.get("uploaded_filename")
            or ""
        ),
        manifest,
        str(task.get("output") or manifest.get("output") or "note"),
    )
    if task.get("status") == "queued":
        ordered = [
            current_id
            for current_id, current in tasks.items()
            if current.get("status") in {"processing", "cancelling", "queued"}
        ]
        try:
            ahead = ordered.index(task_id)
        except ValueError:
            ahead = 0
        payload.update(
            queue_ahead=ahead,
            queue_position=ahead + 1,
            queue_total=len(ordered),
        )
    return payload


def task_recovery_summary(
    task_id: str, task: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    directory = task_directory(task_id)
    transcript = load_transcript_result(directory) is not None
    note = (directory / "notes.md").is_file()
    output = task.get("output") or manifest.get("output") or "note"
    retained = (["transcript"] if transcript else []) + (["note"] if note else [])
    can_resume = transcript and task.get("status") in {"failed", "cancelled", "completed"}
    redo = ["note_generation"] if transcript and output == "note" else []
    if not transcript and not note:
        redo = ["source_processing"] + (["note_generation"] if output == "note" else [])
    return {
        "retained": retained, "can_resume": can_resume, "resume_task_id": task_id if can_resume else None,
        "redo": redo, "requires_explicit_submit": True,
        "message": (
            "已保留完整转录；继续将跳过音频下载与 ASR，重新生成笔记会调用所选模型。勾选截图时仍可能下载预览视频。"
            if transcript and output == "note" else
            "已保留完整转录；继续可复用转录，不调用大模型。" if transcript else
            "未找到完整可用转录；从头处理可能重新下载媒体或转写。"
        ),
    }


@app.get("/api/tasks")
async def list_recent_tasks(
    query: str = "",
    status: Literal["all", "active", "completed", "failed", "cancelled"] = "all",
    output: Literal["all", "note", "transcript"] = "all",
    platform: Literal[
        "all", "bilibili", "douyin", "youtube", "local", "subtitle", "other"
    ] = "all",
    favorite: bool | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    refresh: bool = False,
) -> dict[str, Any]:
    """Return manifest-backed local history without loading note bodies."""
    if refresh:
        history_cache.history_summaries.clear()
    # Agent-only transcript material remains hidden from the web history.
    visible: list[dict[str, Any]] = []
    for task_id in iter_history_task_ids():
        summary, manifest = _list_history_task_record(task_id)
        if summary is None:
            continue
        live_task = tasks.get(task_id)
        origin = manifest.get("origin") or (
            live_task.get("_origin") if isinstance(live_task, dict) else None
        )
        if summary["output"] == "transcript" and str(origin or "agent") != "web":
            continue
        visible.append(summary)

    needle = query.strip().casefold()
    active_statuses = {"pending", "uploaded", "queued", "processing", "cancelling"}

    def matches(summary: dict[str, Any]) -> bool:
        current_status = str(summary.get("status") or "")
        if status == "active" and current_status not in active_statuses:
            return False
        if status not in {"all", "active"} and current_status != status:
            return False
        if output != "all" and summary.get("output") != output:
            return False
        if platform != "all" and summary.get("platform") != platform:
            return False
        if favorite is not None and bool(summary.get("favorite")) is not favorite:
            return False
        if needle and needle not in str(summary.get("title") or "").casefold():
            return False
        return True

    ordered = sorted(
        (summary for summary in visible if matches(summary)),
        key=lambda summary: (str(summary.get("created_at") or ""), summary["task_id"]),
        reverse=True,
    )
    page = ordered[offset : offset + limit]
    return {
        "tasks": page,
        "total": len(ordered),
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(page) < len(ordered),
    }


@app.patch("/api/task/{task_id}/favorite")
async def set_task_favorite(task_id: str, payload: FavoritePayload) -> dict[str, Any]:
    summary = history_task_summary(task_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="任务不存在或已被清理")
    if summary["status"] != "completed" or summary["output"] != "note":
        raise HTTPException(status_code=409, detail="只能收藏已完成的笔记任务")
    try:
        _merge_task_manifest(task_id, "favorite", payload.favorite)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="收藏状态保存失败") from exc
    return {"task_id": task_id, "favorite": payload.favorite}


@app.post("/api/source-inspect")
async def inspect_source(payload: SourceInspectPayload) -> dict[str, Any]:
    try:
        classification = classify_source_url(payload.video_url)
        reusable_task = find_reusable_task(payload.video_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    summary = history_task_summary(reusable_task) if reusable_task else None
    if summary is not None:
        summary = {
            key: summary.get(key)
            for key in (
                "task_id",
                "title",
                "created_at",
                "platform",
                "template_name",
                "favorite",
            )
        }
    return {**classification, "reusable_task": summary}


@app.get("/api/task/{task_id}")
async def get_task_status(task_id: str, refresh_note: bool = False) -> dict[str, Any]:
    task = tasks.get(task_id) or restore_task_on_demand(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或已被清理")
    payload = task_status_payload(task_id, task)
    if refresh_note and task.get("status") == "completed" and task.get("output") != "transcript":
        # Opt-in history read only. Polls/MCP keep their original contract and cached result.
        if not is_safe_task_id(task_id):
            raise HTTPException(status_code=400, detail="非法任务 ID")
        path = WORKSPACE_DIR / task_id / "notes.md"
        identity = _plain_path_snapshot(path)
        try:
            if identity is None:
                raise OSError
            markdown = path.read_text(encoding="utf-8")
            if _plain_path_snapshot(path) != identity:
                raise OSError
        except (OSError, ValueError):
            raise HTTPException(status_code=409, detail="当前笔记缺失或无法安全读取；未返回缓存旧正文") from None
        result = task.get("result") if isinstance(task.get("result"), dict) else {}
        payload["result"] = {**result, "markdown": markdown}
    return payload


@app.get("/api/task/{task_id}/transcript")
async def get_task_transcript(
    task_id: str, output_format: Literal["json", "markdown", "srt"] = "json"
) -> dict[str, Any]:
    """取该任务的带时间轴转录（`segments` 的时间单位是秒）。

    只看转录产物在不在，不看任务状态：即便笔记在第 6 步失败，已完成的转录
    照样能取走，不必重跑。`markdown` 返回人读版整篇文本，`json` 返回分段，
    `srt` 返回可直接进播放器的 SubRip 正文（与 markdown 同一种 JSON 包裹契约）。
    """
    try:
        directory = task_directory(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法任务 ID") from exc
    json_path = directory / "transcript.json"
    if not json_path.is_file():
        raise HTTPException(
            status_code=409, detail="该任务还没有转录产物，可先调用 POST /api/transcribe"
        )
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(status_code=500, detail="转录文件无法读取") from None

    task = tasks.get(task_id) or {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    manifest = read_task_manifest(task_id)
    title = str(
        result.get("title") or manifest.get("title") or manifest.get("uploaded_filename") or ""
    )

    if output_format == "markdown":
        markdown_path = directory / "transcript.md"
        if not markdown_path.is_file():
            raise HTTPException(status_code=409, detail="转录 Markdown 不存在")
        return {
            "task_id": task_id,
            "title": title,
            "format": "markdown",
            "text": markdown_path.read_text(encoding="utf-8"),
        }

    if output_format == "srt":
        srt_segments = payload.get("segments") or []
        return {
            "task_id": task_id,
            "title": title,
            "format": "srt",
            "filename": f"{download_stem(title, manifest, 'transcript')}.srt",
            "text": segments_to_srt(
                [
                    TranscriptSegment(
                        float(item.get("start") or 0),
                        float(item.get("end") or 0),
                        str(item.get("text") or ""),
                    )
                    for item in srt_segments
                    if isinstance(item, dict)
                ]
            ),
        }

    segments = payload.get("segments") or []
    return {
        "task_id": task_id,
        "title": title,
        "format": "json",
        "language": payload.get("language"),
        "transcript_source": payload.get("source"),
        "transcript_quality": payload.get("quality"),
        "segment_count": len(segments),
        "segments": segments,
    }


@app.get("/api/task/{task_id}/transcript-context")
async def get_transcript_context(
    task_id: str,
    start: float = Query(0, ge=0),
    end: float | None = Query(None, ge=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    transcript_hash: str | None = Query(None, pattern=r"^[a-f0-9]{64}$"),
    note_hash: str | None = Query(None, pattern=r"^[a-f0-9]{64}$"),
) -> dict[str, Any]:
    """Read-only time lookup; hashes bind a lookup/page to the same saved artifacts."""
    if not math.isfinite(start) or (end is not None and (not math.isfinite(end) or end < start)):
        raise HTTPException(status_code=422, detail="时间范围无效，终点须不早于起点")
    if not is_safe_task_id(task_id):
        raise HTTPException(status_code=400, detail="非法任务 ID")
    # Inspect the lexical directory before task_directory resolves any components.
    if _plain_path_snapshot(WORKSPACE_DIR / task_id, directory=True) is None:
        raise HTTPException(status_code=409, detail="原转录缺失、损坏或无法安全读取；不会自动重新处理")
    try:
        directory = task_directory(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="非法任务 ID") from None
    path = directory / "transcript.json"
    identity = _plain_path_snapshot(path)
    result = load_transcript_result(directory) if identity else None
    if result is None or _plain_path_snapshot(path) != identity:
        raise HTTPException(status_code=409, detail="原转录缺失、损坏或无法安全读取；不会自动重新处理")
    segments = result["segments"]
    revision = transcript_revision(segments)
    if transcript_hash is not None and transcript_hash != revision:
        raise HTTPException(status_code=409, detail="原转录已变化，请重新读取后定位")

    note_revision = None
    note_path = directory / "notes.md"
    note_identity = _plain_path_snapshot(note_path)
    if note_identity:
        try:
            text = note_path.read_text(encoding="utf-8")
            if _plain_path_snapshot(note_path) == note_identity:
                note_revision = hashlib.sha256(text.encode("utf-8")).hexdigest()
        except (OSError, ValueError):
            pass
    if note_hash is not None and note_hash != note_revision:
        raise HTTPException(status_code=409, detail="笔记已变化或无法读取，请从历史重新打开当前笔记")

    matches = locate_transcript(segments, start, end)
    coverage_start = min(s.start for s in segments)
    coverage_end = max(s.end for s in segments)
    range_state = "gap"
    if matches:
        range_state = "partial" if start < coverage_start or (end is not None and end > coverage_end) else "matched"
    elif start >= coverage_end or (end if end is not None else start) < coverage_start:
        range_state = "outside"
    manifest = _open_result_manifest(task_id)
    pages = manifest.get("bili_selected_pages")
    merged = (isinstance(pages, list) and len(pages) > 1) or any(
        re.match(r"【P\d+[\s】]", s.text) for s in segments
    )
    try:
        media_retained = any(
            media_retention.is_owned_media_name(p.name) and _plain_path_snapshot(p)
            for p in directory.iterdir()
        )
    except OSError:
        media_retained = False
    return {
        "task_id": task_id, "transcript_hash": revision, "note_hash": note_revision,
        "start": start, "end": end, "coverage": {"start": coverage_start, "end": coverage_end},
        "range_state": range_state, "segments": matches[offset:offset + limit],
        "total": len(matches), "offset": offset, "limit": limit,
        "has_more": offset + limit < len(matches),
        "timeline": "merged" if merged else "single",
        "media_state": "retained" if media_retained else "not_retained",
    }


@app.get("/api/whisper-models")
async def whisper_models_status() -> dict[str, Any]:
    """返回各 Whisper 模型在本机的缓存状态（供前端标注下拉框）。"""
    models = [
        {
            "id": model_id,
            "status": transcriber._model_cache_status(model_id),
        }
        for model_id in sorted(WHISPER_MODELS)
    ]
    models.append({"id": "paraformer-zh", "status": paraformer_transcriber.cache_status()})
    return {"models": models, "manual_dir": str(WHISPER_CACHE_DIR / "manual")}


class WhisperManualFolderPayload(BaseModel):
    model: str
    open: bool = True


def _open_in_file_manager(path: Path) -> bool:
    """用系统默认程序打开文件或目录；失败时返回 False（前端展示路径兜底）。"""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:
        return False


def _plain_path_snapshot(path: Path, *, directory: bool = False) -> tuple | None:
    """Inspect lexical components before resolution, retaining identities for recheck.

    Match the retention guard's no-reparse/no-hardlink policy. Shell opening is
    pathname based: this narrows, but cannot eliminate, the final dispatch race.
    """
    try:
        if (not path.is_absolute() or path.drive.startswith("\\\\")
                or any(part == ".." or ":" in part or "\0" in part
                       or part.endswith((".", " ")) for part in path.parts[1:])):
            return None
        identities = []
        for component in (*reversed(path.parents), path):
            is_directory = component != path or directory
            info = component.stat(follow_symlinks=False)
            kind_ok = stat.S_ISDIR(info.st_mode) if is_directory else stat.S_ISREG(info.st_mode)
            if (not kind_ok or getattr(info, "st_file_attributes", 0) & 0x400
                    or not info.st_ino or (not is_directory and info.st_nlink != 1)):
                return None
            identities.append((info.st_dev, info.st_ino))
        return tuple(identities)
    except (OSError, ValueError, RuntimeError):
        return None


def _open_result_manifest(task_id: str) -> dict[str, Any]:
    path = WORKSPACE_DIR / task_id / "task.json"
    identity = _plain_path_snapshot(path)
    if identity is None:
        return {}
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if _plain_path_snapshot(path) != identity:
            return {}
    except (OSError, ValueError, RuntimeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _trusted_archived_result(task_id: str, task: dict[str, Any]) -> tuple[Path, tuple] | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    raw_path = result.get("archived_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    manifest = _open_result_manifest(task_id)
    output = str(task.get("output") or manifest.get("output") or "note")
    try:
        raw_root = manifest.get("note_destination", "")
        if raw_root is None:
            raw_root = ""
        if output == "note":
            if not isinstance(raw_root, str):
                return None
            root = Path(raw_root) if raw_root else WORKSPACE_DIR / NOTES_DIR_NAME
        elif output == "transcript":
            root = WORKSPACE_DIR / TRANSCRIPTS_DIR_NAME
        else:
            return None
        candidate = Path(raw_path)
        if candidate.suffix.lower() != ".md" or candidate.parent != root:
            return None
        identity = _plain_path_snapshot(candidate)
        return (candidate, identity) if identity is not None else None
    except (OSError, ValueError, RuntimeError):
        return None


def _result_file_for_open(task_id: str, task: dict[str, Any]) -> tuple[Path, tuple] | None:
    if not is_safe_task_id(task_id):
        return None
    archived = _trusted_archived_result(task_id, task)
    if archived is not None:
        return archived
    manifest = _open_result_manifest(task_id)
    output = str(task.get("output") or manifest.get("output") or "note")
    if output not in {"note", "transcript"}:
        return None
    filename = "transcript.md" if output == "transcript" else "notes.md"
    try:
        candidate = WORKSPACE_DIR / task_id / filename
        identity = _plain_path_snapshot(candidate)
        return (candidate, identity) if identity is not None else None
    except (OSError, ValueError, RuntimeError):
        return None


@app.post("/api/task/{task_id}/open-result")
async def open_task_result(task_id: str, payload: OpenResultPayload) -> dict[str, Any]:
    """Open one completed result without accepting a caller-supplied path."""
    if (not is_safe_task_id(task_id)
            or _plain_path_snapshot(WORKSPACE_DIR / task_id, directory=True) is None):
        raise HTTPException(status_code=404, detail="结果文件不存在或路径不可安全打开")
    task = tasks.get(task_id)
    if task is None:
        # Opening a result needs only a safe manifest summary, never note content
        # or unrelated runtime fields that may be corrupt in an old task.
        manifest = _open_result_manifest(task_id)
        if manifest:
            runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
            output = str(manifest.get("output") or "note")
            filename = "transcript.md" if output == "transcript" else "notes.md"
            inferred = "completed" if _plain_path_snapshot(WORKSPACE_DIR / task_id / filename) else "failed"
            task = {"status": runtime.get("status") or inferred, "output": output,
                    "result": runtime.get("result")}
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在或已被清理")
    if task.get("status") != "completed":
        raise HTTPException(status_code=409, detail="任务尚未完成")
    result = _result_file_for_open(task_id, task)
    if result is None:
        raise HTTPException(status_code=404, detail="结果文件不存在或路径不可安全打开")
    result_file, identity = result
    if _plain_path_snapshot(result_file) != identity:
        raise HTTPException(status_code=404, detail="结果文件不存在或路径不可安全打开")
    target = result_file if payload.target == "file" else result_file.parent
    return {"opened": _open_in_file_manager(target), "target": payload.target}


PARAFORMER_IMPORT_LABELS = {
    "asr": "转写主模型",
    "punc": "标点模型（可以不放：缺了会自动降级为无标点转写）",
    "vad": "语音活动检测",
}


@app.post("/api/whisper-models/manual-folder")
async def open_whisper_manual_folder(payload: WhisperManualFolderPayload) -> dict[str, Any]:
    """创建并返回手动导入模型的引导（大模型网络下载失败时的替代方案）。

    open=false 只给引导信息，供前端先展示步骤、用户确认后再开文件夹。
    一条模型可能由多个组件目录组成（paraformer-zh 是 asr / punc / vad 三份，
    而且和 faster-whisper 系根本不是一个缓存目录），所以引导统一返回 folders 列表。
    """
    if payload.model not in ASR_MODELS:
        raise HTTPException(status_code=422, detail="不支持的转写模型")

    if payload.model == "paraformer-zh":
        folders = []
        for component, spec in paraformer_asr.MODEL_SPECS.items():
            directory = paraformer_transcriber._component_dir(component)
            directory.mkdir(parents=True, exist_ok=True)
            folders.append(
                {
                    "label": PARAFORMER_IMPORT_LABELS[component],
                    "path": str(directory),
                    "files": list(spec["files"]),
                    "download_url": f"https://hf-mirror.com/{spec['repo']}/tree/main",
                }
            )
        open_path = paraformer_transcriber.download_root
    else:
        manual_dir = WHISPER_CACHE_DIR / "manual" / payload.model
        manual_dir.mkdir(parents=True, exist_ok=True)
        folders = [
            {
                "label": "模型文件",
                "path": str(manual_dir),
                "files": transcriber.manual_import_files(payload.model),
                "download_url": f"https://hf-mirror.com/{transcriber._model_repo(payload.model)}/tree/main",
            }
        ]
        open_path = manual_dir

    return {
        "folders": folders,
        "open_path": str(open_path),
        "opened": _open_in_file_manager(open_path) if payload.open else False,
    }


def _key_storage_info() -> dict[str, Any]:
    return {"algorithm": secret_box.storage_backend(), "secure": secret_box.is_secure_storage()}


def resolve_llm_credentials(*, model_type: str, base_url: str | None, api_key: str) -> tuple[str, str]:
    """显式 Key 永远优先；否则只按接口地址复用本机已存 Key。

    地址不一致就直接失败，不会"先拿本机某把 Key 试试"——那正是把 DeepSeek 的
    Key 发给第三方网关的路径。返回 ``(api_key, 来源说明)``，来源说明进任务日志。
    """
    explicit = (api_key or "").strip()
    if explicit:
        return explicit, "本次请求提供"
    resolved = config_store.resolve_stored_key(model_type=model_type, base_url=base_url or "")
    secret = str(resolved.get("api_key") or "")
    if secret:
        entry = resolved.get("entry") or {}
        where = str(entry.get("label") or resolved.get("host") or "")
        masked = str(entry.get("api_key_masked") or "")
        return secret, f"本机已存 {masked}（{where}）"
    raise RuntimeError(_missing_key_message(model_type, base_url, resolved))


def _missing_key_message(model_type: str, base_url: str | None, resolved: dict[str, Any]) -> str:
    target = (base_url or "").strip() or default_base_url(model_type) or "未指定接口地址"
    reason = str(resolved.get("reason") or "")
    detail = {
        "undecryptable": (
            f"为 {target} 保存的 Key 无法解密（可能来自其他机器或其他 Windows 账户），"
            "请重新填写并保存"
        ),
        "corrupt_keys_file": (
            f"本机密钥文件 {LLM_KEYS_FILE} 已损坏，请在模型配置页清除本机配置后重新保存"
        ),
        "unknown_endpoint": f"接口地址无法识别（{target}），不会复用任何本机 Key",
    }.get(reason) or f"本机没有为 {target} 保存 Key"
    return (
        f"未提供 API Key，{detail}。"
        "请在模型配置页填写 API Key 并「保存到本机」，或在请求中直接带上 api_key。"
    )


@app.get("/api/llm-keys")
async def get_llm_keys(base_url: str = "", provider: str = "") -> dict[str, Any]:
    """列出本机保存的接口 Key（只有掩码）；带 base_url 时顺带回答"这个地址存了没有"。"""
    if config_store.keys_are_corrupt():
        return {"storage": _key_storage_info(), "error": "corrupt_keys_file", "entries": []}
    payload: dict[str, Any] = {"storage": _key_storage_info(), "entries": config_store.list_keys()}
    if base_url or provider:
        resolved = config_store.resolve_stored_key(model_type=provider, base_url=base_url)
        entry = resolved.get("entry")
        key_state = "none"
        if entry:
            key_state = "saved" if resolved.get("api_key") else "undecryptable"
        payload["match"] = {
            "saved": bool(entry),
            "key_state": key_state,
            "endpoint": normalize_endpoint_host(base_url, provider),
            **(entry or {}),
        }
    return payload


@app.put("/api/llm-keys")
async def put_llm_key(payload: LLMKeyPayload) -> dict[str, Any]:
    """显式保存：把某个接口地址的 API Key 加密写入本机。清除只能走 DELETE。"""
    try:
        entry = config_store.put_key(
            provider=payload.provider,
            base_url=payload.base_url or "",
            api_key=payload.api_key.get_secret_value(),
            label=payload.label,
            model=payload.model,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except secret_box.SecretBoxError as error:
        raise HTTPException(status_code=500, detail=f"本机加密保存失败：{error}") from error
    return {"saved": True, **entry}


@app.delete("/api/llm-keys")
async def delete_llm_key(base_url: str = "", provider: str = "") -> dict[str, Any]:
    return {"removed": config_store.delete_key(base_url=base_url, model_type=provider)}


@app.get("/api/llm-config")
async def get_llm_config() -> dict[str, Any]:
    """旧接口：报告本机最近保存的一条配置（含掩码，不含 Key 原文），供 MCP 免传参复用。"""
    entry = config_store.most_recent_entry()
    if not entry or not entry["has_key"]:
        return {"saved": False}
    return {
        "saved": True,
        "model_type": entry["provider"],
        "model": entry["model"],
        "base_url": entry["base_url"] or None,
        "api_key_masked": entry["api_key_masked"] or None,
    }


@app.post("/api/llm-config")
async def save_llm_config(payload: LLMConfigPayload) -> dict[str, Any]:
    """旧接口：等价于按接口地址保存 Key（MCP 的 save_llm_config 仍走这里）。"""
    try:
        entry = config_store.put_key(
            provider=payload.model_type,
            base_url=payload.base_url or "",
            api_key=payload.api_key.get_secret_value(),
            label=payload.label,
            model=payload.model,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except secret_box.SecretBoxError as error:
        raise HTTPException(status_code=500, detail=f"本机加密保存失败：{error}") from error
    return {
        "saved": True,
        "model_type": entry["provider"],
        "model": entry["model"],
        "label": entry["label"],
    }


@app.post("/api/llm-test")
async def test_llm_connection(
    payload: LLMTestPayload | None = None,
) -> dict[str, Any]:
    """用（可选覆盖的）LLM 配置做一次轻量连通测试。"""
    body = payload or LLMTestPayload()
    model_type = body.model_type or "deepseek"
    base_url = body.base_url or default_base_url(model_type) or None
    try:
        api_key, key_source = resolve_llm_credentials(
            model_type=model_type,
            base_url=base_url,
            api_key=body.api_key.get_secret_value() if body.api_key else "",
        )
    except RuntimeError as error:
        return {"ok": False, "error": str(error)}
    except Exception as error:
        # 密钥档案读不了（磁盘故障 / DPAPI 失灵 / 文件损坏）不该裸 500。
        # 只回固定脱敏提示与异常类型；绝不回显 str(error)、路径或配置。
        return {
            "ok": False,
            "error": utf8_safe(
                "读取本机保存的 Key 失败，请重新保存或清除损坏配置"
                f"（{type(error).__name__}）"
            ),
        }
    try:
        summarizer = LLMSummarizer(
            model_type=model_type,
            api_key=api_key,
            base_url=base_url,
            model=body.model,
        )
        ok, message, latency = await summarizer.test_connection()
        return {
            "ok": ok,
            "message": message,
            "latency_ms": int(round(latency * 1000)),
            "model": body.model or summarizer.model,
            "base_url": summarizer.base_url,
            "key_source": key_source,
        }
    except Exception as exc:
        try:
            detail = utf8_safe(str(exc))
            detail = redact_secrets(detail, api_key)
            detail = redact_paths(detail)
        except Exception:
            detail = type(exc).__name__
        return {"ok": False, "error": f"初始化失败：{detail}"}


@app.delete("/api/llm-config")
async def clear_llm_config() -> dict[str, Any]:
    """旧接口：只清除它刚报告的那一条，不会一次清空全部本机 Key。"""
    entry = config_store.most_recent_entry()
    removed = bool(entry) and config_store.delete_key(
        base_url=entry["base_url"], model_type=entry["provider"]
    )
    return {"saved": False, "removed": removed}


@app.get("/api/bili-credentials")
async def get_bili_credentials() -> dict[str, Any]:
    """Return saved Bilibili credential status without exposing cookie values.

    走 ``bili_credentials_status()``：只用保存时写死的掩码，全程不解密，
    所以换机器解不开时这个端点仍然有得报。
    """
    return config_store.bili_credentials_status()


@app.post("/api/bili-credentials")
async def save_bili_credentials(payload: BiliCredentialsPayload) -> dict[str, Any]:
    try:
        config_store.save_bili_credentials(
            {"sessdata": payload.sessdata, "bili_jct": payload.bili_jct, "buvid3": payload.buvid3}
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except secret_box.SecretBoxError as error:
        raise HTTPException(status_code=500, detail=f"本机加密保存失败：{error}") from error
    return {"saved": True}


@app.delete("/api/bili-credentials")
async def clear_bili_credentials() -> dict[str, bool]:
    config_store.clear_bili_credentials()
    return {"saved": False}


def previous_bili_pages(normalized_url: str) -> list[int] | None:
    """该视频最近一次任务显式勾选的分 P（新任务在前扫描，没有则 None）。

    重新处理多分 P 视频时，面板默认沿用上次的范围，不用重新勾一遍；
    只认显式下发过的 bilibili_pages（None 表示当时的「全部」，不预勾）。
    """
    for candidate in sorted(
        (path for path in WORKSPACE_DIR.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        manifest_path = candidate / "task.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if manifest.get("normalized_source_url") != normalized_url:
            continue
        pages = manifest.get("bilibili_pages")
        if isinstance(pages, list) and pages:
            return [int(page) for page in pages]
    return None


@app.post("/api/bili-pages")
async def preview_bilibili_pages(request: BiliPagesRequest) -> dict[str, Any]:
    """提交任务前预览 B 站分 P 清单，让用户显式勾选要转写的分 P。

    只读 view 接口，不触发下载；凭据可选（公开接口一般无需登录，
    携带凭据可降低风控概率）。front 端拿 url 的 ?p= 自行决定默认勾选。
    """
    url = normalize_video_input(request.video_url) or request.video_url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="请先粘贴 B 站视频链接")
    try:
        source = video_processor.detect_source(url)
    except ValueError:
        source = None
    if source != VideoSource.BILIBILI:
        raise HTTPException(status_code=400, detail="分 P 预览仅支持 B 站视频链接")
    if request.bilibili_cookie:
        cookie: dict[str, str] | None = request.bilibili_cookie.model_dump()
    else:
        try:
            cookie = config_store.load_bili_credentials()
        except BiliCredentialsUnavailable:
            cookie = None
    video = await video_processor.bilibili_video_pages(url, cookie)
    if video is None:
        raise HTTPException(
            status_code=400, detail="未能从链接解析出 B 站视频（BV/av 号）"
        )
    if not video.pages:
        raise HTTPException(
            status_code=502,
            detail="B 站接口未返回分 P 信息（网络或风控异常），可稍后重试或填写凭据",
        )
    return {
        "title": video.title,
        "total_pages": len(video.pages),
        "pages": [
            {"page": page.page, "part": page.part, "duration": page.duration}
            for page in video.pages
        ],
        # 该视频上次任务显式勾选的分 P；前端拿它做默认勾选（优先于 ?p=N）
        "previous_pages": previous_bili_pages(normalize_source_url(url)),
    }


@app.get("/api/note-templates")
async def list_note_templates() -> dict[str, Any]:
    """列出全部模板：内置模板在前，自定义模板按名称排序。"""
    templates = get_template_store().list_templates()
    return {
        "templates": [
            {**template.to_dict(), "preview_markdown": note_templates.preview_markdown(template)}
            for template in templates
        ]
    }


@app.post("/api/note-templates")
async def create_note_template(payload: NoteTemplateCreatePayload) -> dict[str, Any]:
    try:
        template = get_template_store().create(
            name=payload.name,
            description=payload.description,
            instructions=payload.instructions,
            layout=payload.layout,
        )
    except note_templates.TemplateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return template.to_dict()


@app.put("/api/note-templates/{template_id}")
async def update_note_template(
    template_id: str, payload: NoteTemplateUpdatePayload
) -> dict[str, Any]:
    try:
        template = get_template_store().update(
            template_id,
            name=payload.name,
            description=payload.description,
            instructions=payload.instructions,
            layout=payload.layout,
        )
    except note_templates.TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="笔记模板不存在") from exc
    except (
        note_templates.TemplateImmutableError,
        note_templates.TemplateValidationError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return template.to_dict()


@app.delete("/api/note-templates/{template_id}")
async def delete_note_template(template_id: str) -> dict[str, bool]:
    try:
        get_template_store().delete(template_id)
    except note_templates.TemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="笔记模板不存在") from exc
    except note_templates.TemplateImmutableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": True}


@app.get("/api/integrations/note-destinations")
async def note_destinations() -> dict[str, Any]:
    """Obsidian Vault 与飞书 lark-cli 的只读检测结果（全部脱敏）。

    只读：不登录、不写云端、不启动应用；Vault 配置变化可通过前端刷新重新读取。
    """
    return {
        "obsidian": note_integrations.detect_obsidian(),
        "feishu": note_integrations.check_feishu_readiness(),
    }


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        # 旧发现逻辑按 service 认服务，字段名与取值都不能动
        "service": LEGACY_SERVICE_ID,
        "product": PRODUCT_NAME,
        "api_compat": API_COMPAT,
        "version": app.version,
        # portable/dev 互不复用对方实例，避免 dev 服务占用端口导致打包版不驻留托盘
        "mode": "portable" if getattr(sys, "frozen", False) else "dev",
        # 本机保存的 API Key 是加密还是明文回退，答疑时看一眼健康接口即可确认
        "llm_key_storage": secret_box.storage_backend(),
        # 前端上传上限跟随本机配置，不再自己写死一个数字
        "max_upload_mb": MAX_UPLOAD_MB,
        # 字幕导入单独一个上限：提示语要说"最大 20 MB 的字幕"，不能拿媒体的 2GB 去说
        "max_subtitle_mb": MAX_SUBTITLE_MB,
        "dependencies": {
            "yt_dlp": importlib.util.find_spec("yt_dlp") is not None,
            "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
            "openai": importlib.util.find_spec("openai") is not None,
            # MCP 的 SSE 端点是否真的挂上了（缺 mcp 依赖时前端要说"不通"而不是给个死地址）
            "mcp_sse": MCP_SSE_ENABLED,
        },
    }


@app.post("/api/bili-login/start")
async def bili_login_start() -> dict[str, Any]:
    return await bili_login_manager.start()


@app.get("/api/bili-login/status")
async def bili_login_status() -> dict[str, Any]:
    return await bili_login_manager.status()


@app.post("/api/bili-login/cancel")
async def bili_login_cancel() -> dict[str, Any]:
    return await bili_login_manager.cancel()


@app.post("/api/douyin-login/start")
async def douyin_login_start() -> dict[str, Any]:
    """打开独立的本机浏览器 profile，用户可手动完成抖音登录/验证。"""
    return await douyin_login_manager.start()


@app.get("/api/douyin-login/status")
async def douyin_login_status() -> dict[str, Any]:
    return await douyin_login_manager.status()


@app.post("/api/douyin-login/cancel")
async def douyin_login_cancel() -> dict[str, Any]:
    return await douyin_login_manager.cancel()


# 视频容器后缀（可能带音轨、需要时提取）；纯音频后缀直接使用
VIDEO_CONTAINER_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi"}


@app.post("/api/upload")
async def upload_video(
    file: UploadFile = File(...),
    include_screenshots: str | None = Form(default=None),
) -> dict[str, str]:
    filename = Path(file.filename or "upload.bin").name
    suffix = Path(filename).suffix.lower()
    is_subtitle = suffix in ALLOWED_SUBTITLE_SUFFIXES
    if not is_subtitle and suffix not in ALLOWED_MEDIA_SUFFIXES:
        raise HTTPException(status_code=415, detail="不支持的媒体文件类型")
    byte_limit = MAX_SUBTITLE_BYTES if is_subtitle else MAX_UPLOAD_BYTES
    limit_mb = MAX_SUBTITLE_MB if is_subtitle else MAX_UPLOAD_MB

    task_id = str(uuid.uuid4())
    task_dir = WORKSPACE_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=False)
    # 字幕刻意不落成 input.*：本地媒体与「复用转录」都靠 input.* 找媒体文件，
    # 字幕混进那个 glob 会让之后的「从头处理」去 ffprobe 一份 .srt。
    file_path = task_dir / (f"subtitle{suffix}" if is_subtitle else f"input{suffix}")
    wants_screenshots = (include_screenshots or "").strip().lower() in {
        "1", "true", "yes"
    }
    written = 0
    try:
        async with aiofiles.open(file_path, "wb") as destination:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > byte_limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"上传文件超过大小限制（上限 {limit_mb} MB）",
                    )
                await destination.write(chunk)
    except Exception:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise
    finally:
        await file.close()

    if is_subtitle:
        return await register_subtitle_upload(task_id, task_dir, file_path, filename)

    log_lines: list[str] = [f"文件已上传：{filename}"]
    # 大视频且不需要截图时：提取音频、删除原视频，减少工作目录体积
    if (
        written >= LARGE_UPLOAD_EXTRACT_BYTES
        and suffix in VIDEO_CONTAINER_SUFFIXES
        and not wants_screenshots
    ):
        audio_path = task_dir / "input.m4a"
        try:
            extracted = await asyncio.to_thread(
                video_processor.extract_audio_track, file_path, audio_path
            )
        except Exception:
            extracted = None
        if extracted is not None and extracted.is_file():
            original_size = written
            file_path.unlink(missing_ok=True)
            file_path = audio_path
            log_lines.append(
                f"大视频已提取音频：{format_bytes_size(original_size)} → "
                f"{format_bytes_size(audio_path.stat().st_size)}（原视频已清理；"
                "如需截图请取消勾选该任务后重新上传）"
            )
        else:
            log_lines.append(
                "视频较大，未能提取音频，将直接用原文件转写（不影响使用）"
            )

    tasks[task_id] = new_task(status="uploaded", task_id=task_id)
    tasks[task_id].update(
        uploaded_file_path=str(file_path),
        uploaded_filename=filename,
        logs=log_lines,
    )
    write_upload_manifest(task_id, filename)
    persist_task_runtime(task_id)
    return {"task_id": task_id, "file_path": str(file_path), "filename": filename}


async def register_subtitle_upload(
    task_id: str, task_dir: Path, path: Path, filename: str
) -> dict[str, str]:
    """把一份字幕落成一个「转录已经完成」的任务，后面直接从生成笔记那步起跑。

    读不出内容就地报错，而不是等任务跑到第 4 步才发现——上传是同步的，用户还对着
    那个文件选择框，这时候说「这份字幕里没有带时间轴的文本」才来得及换一份。
    """
    try:
        segments = parse_subtitle_payload(
            path.read_text(encoding="utf-8-sig", errors="replace"),
            path.suffix.lower().lstrip("."),
        )
    except (OSError, ValueError):
        segments = []
    if not segments:
        shutil.rmtree(task_dir, ignore_errors=True)
        raise HTTPException(
            status_code=415,
            detail="这份字幕里没有读到任何带时间轴的文本，请确认是 .srt / .vtt 且内容非空",
        )
    await write_transcript_files(
        task_id, segments, {"language": "unknown", "source": "subtitle_import"}
    )
    tasks[task_id] = new_task(status="uploaded", task_id=task_id)
    tasks[task_id].update(
        uploaded_filename=filename,
        subtitle_import=True,
        logs=[
            f"字幕已导入：{filename}，共 {len(segments)} 条",
            f"时间轴到 {format_timestamp(segments[-1].end)}，跳过下载与转写",
        ],
    )
    write_upload_manifest(task_id, filename, subtitle_import=True)
    persist_task_runtime(task_id)
    return {"task_id": task_id, "file_path": str(path), "filename": filename}


@app.get("/api/image/{task_id}/{filename}")
async def get_image(task_id: str, filename: str) -> FileResponse:
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    task_dir = (WORKSPACE_DIR / task_id).resolve()
    if task_dir.parent != WORKSPACE_DIR:
        raise HTTPException(status_code=400, detail="非法任务 ID")
    expected_parent = (task_dir / FRAMES_DIR_NAME).resolve()
    image_path = (expected_parent / filename).resolve()
    if image_path.parent != expected_parent or not image_path.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(image_path)


@app.get("/api/download/{task_id}")
async def download_summary_markdown(task_id: str) -> Response:
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != "completed":
        raise HTTPException(status_code=409, detail="任务尚未完成")

    task_dir = WORKSPACE_DIR / task_id
    output_path = task_dir / "notes.md"
    if not output_path.is_file():
        # 纯转录任务按设计不产出 notes.md，能下载的就是带时间轴的转录
        output_path = task_dir / "transcript.md"
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="Markdown 笔记不存在")

    title = (task.get("result") or {}).get("title", "video-notes")
    safe_name = download_stem(
        str(title),
        read_task_manifest(task_id),
        str(task.get("output") or "note"),
    )
    try:
        note_text = output_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"读取笔记失败：{exc}")

    bundle = await asyncio.to_thread(
        build_note_bundle, note_text, task_dir, f"{safe_name}.md"
    )
    if bundle is not None:
        encoded_name = quote(f"{safe_name}.zip")
        return Response(
            content=bundle,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
        )

    encoded_name = quote(f"{safe_name}.md")
    return FileResponse(
        output_path,
        media_type="text/markdown; charset=utf-8",
        filename=f"{safe_name}.md",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


def referenced_note_attachments(note_text: str, task_dir: Path) -> list[tuple[str, Path]]:
    """返回正文引用且确实位于当前任务截图目录内的附件。"""
    frames_dir = task_dir / FRAMES_DIR_NAME
    try:
        task_root = task_dir.resolve(strict=True)
        frames_root = frames_dir.resolve(strict=True)
    except OSError:
        return []
    if not frames_root.is_relative_to(task_root):
        return []
    attachments: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for match in NOTE_IMAGE_REF_RE.finditer(note_text):
        name = Path(unquote(match.group(2))).name
        if name in seen:
            continue
        try:
            source = (frames_root / name).resolve(strict=True)
        except OSError:
            continue
        if not source.is_relative_to(frames_root) or not source.is_file():
            continue
        seen.add(name)
        attachments.append((name, source))
    return attachments


def build_note_bundle(note_text: str, task_dir: Path, note_filename: str) -> bytes | None:
    """把笔记和它引用的截图打成一个包；正文里没有可解析的截图时返回 None。"""
    attachments = referenced_note_attachments(note_text, task_dir)
    if not attachments:
        return None
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr(note_filename, rewrite_note_image_refs(note_text, "./"))
        for name, source in attachments:
            archive.writestr(
                f"{FRAMES_DIR_NAME}/{name}", source.read_bytes()
            )
    return buffer.getvalue()


FEISHU_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})
FEISHU_MAX_IMAGE_BYTES = 20 * 1024 * 1024

# 飞书暂存改写专用：与 NOTE_IMAGE_REF_RE 同边界，额外捕获 alt 作为 caption。
_FEISHU_IMAGE_REF_RE = re.compile(r"!\[([^\]]*)\]\(\./(?:frames|images)/([^)]+)\)")


def strip_note_frontmatter(note_text: str) -> str:
    """仅当首行是 --- 且存在成对闭合 --- 时删除 YAML Frontmatter，否则原样返回。"""
    lines = note_text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return note_text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[index + 1:])
    return note_text


def _copy_verified_image(source: Path, destination: Path) -> None:
    """以 verified 身份打开源图片再复制：拒绝链接/硬链接/身份不一致/不可靠身份。

    先做 non-following stat 得到预期身份，再打开句柄用 fstat 与路径身份复核，最后
    用已验证句柄 copyfileobj 到排他创建的暂存目标。任何不确定或替换都 fail closed。
    """
    try:
        expected = media_retention._snapshot(source)
    except OSError as exc:
        raise note_integrations.FeishuMediaError("unsupported_image") from exc
    if expected.st_size > FEISHU_MAX_IMAGE_BYTES:
        raise note_integrations.FeishuMediaError("image_too_large")
    try:
        with media_retention._locked_path(source, expected) as fd:
            if os.fstat(fd).st_size > FEISHU_MAX_IMAGE_BYTES:
                raise note_integrations.FeishuMediaError("image_too_large")
            with os.fdopen(os.dup(fd), "rb") as reader, destination.open("xb") as writer:
                shutil.copyfileobj(reader, writer)
    except note_integrations.FeishuMediaError:
        raise
    except OSError as exc:
        raise note_integrations.FeishuMediaError("unsupported_image") from exc


def build_feishu_docx_staging(
    note_text: str, task_dir: Path, staging_dir: Path, content_name: str
) -> None:
    """把笔记写进飞书暂存目录：剥离 Frontmatter，并按首次出现顺序内联本地图片。

    引用发现、边界解析、缺失检查、编号复制与替换都只基于剥离后的正文 cloud_body；
    Frontmatter 里的引用不进入云文档，也不触发复制或失败。只复用
    referenced_note_attachments 的边界结果，任一被测正文引用图片缺失、越界、格式
    或大小不合规都抛 FeishuMediaError，绝不放行给 CLI。不修改任务原始产物。
    """
    cloud_body = strip_note_frontmatter(note_text)
    attachments = referenced_note_attachments(cloud_body, task_dir)
    safe_names = {name for name, _source in attachments}
    referenced_names = {
        Path(unquote(match.group(2))).name
        for match in _FEISHU_IMAGE_REF_RE.finditer(cloud_body)
    }
    if referenced_names - safe_names:
        raise note_integrations.FeishuMediaError("unsupported_image")

    name_map: dict[str, str] = {}
    for index, (name, source) in enumerate(attachments, start=1):
        suffix = source.suffix.lower()
        if suffix not in FEISHU_IMAGE_SUFFIXES:
            raise note_integrations.FeishuMediaError("unsupported_image")
        staged_name = f"image-{index:03d}{suffix}"
        frames = staging_dir / FRAMES_DIR_NAME
        frames.mkdir(parents=True, exist_ok=True)
        _copy_verified_image(source, frames / staged_name)
        name_map[name] = staged_name

    def replace(match):
        name = Path(unquote(match.group(2))).name
        staged = name_map.get(name)
        if staged is None:
            return match.group(0)
        return f"![{match.group(1)}](<@./{FRAMES_DIR_NAME}/{staged}>)"

    (staging_dir / content_name).write_text(
        _FEISHU_IMAGE_REF_RE.sub(replace, cloud_body), encoding="utf-8"
    )


@app.post("/api/task/{task_id}/feishu-upload")
async def retry_feishu_upload(task_id: str) -> dict[str, Any]:
    """只重试飞书发布：复用现有 notes.md / frames，不跑下载、ASR 或 LLM。

    不覆盖远端已有文件：每次重试都可能再创建一份，超时等结果不确定的
    场景由前端在重试前明确提示。
    """
    task = tasks.get(task_id) or restore_task_on_demand(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != "completed":
        raise HTTPException(status_code=409, detail="只有已完成的笔记任务才能重试飞书上传")
    manifest = read_task_manifest(task_id)
    if str(manifest.get("output") or "note") != "note":
        raise HTTPException(status_code=409, detail="纯转录任务没有飞书上传目标")
    target = manifest.get("feishu_upload")
    token = target.get("folder_token") if isinstance(target, dict) else None
    if not isinstance(token, str) or not token:
        raise HTTPException(status_code=409, detail="该任务没有飞书上传目标")
    notes_path = task_directory(task_id) / "notes.md"
    if not notes_path.is_file():
        raise HTTPException(status_code=409, detail="本地笔记不存在，无法重试飞书上传")
    readiness = note_integrations.check_feishu_readiness()
    if not (readiness["installed"] and readiness["capable"]):
        raise HTTPException(
            status_code=400,
            detail="未检测到可用的 lark-cli（缺少 docs 命令），无法创建飞书在线文档",
        )
    if readiness["auth"] != "ready" or not readiness["scopes_ready"]:
        raise HTTPException(
            status_code=400,
            detail="飞书 user 登录不可用或缺少在线文档发布权限，请先用 lark-cli 完成授权后重试",
        )
    try:
        note_text = notes_path.read_text(encoding="utf-8")
        title = str((task.get("result") or {}).get("title") or manifest.get("title") or "video-notes")
        publication = note_integrations.publish_note(
            note_text=note_text,
            task_dir=task_directory(task_id),
            title=title,
            folder_token=token,
            staging_builder=build_feishu_docx_staging,
        )
    except Exception:
        # 重试同样 best-effort：返回稳定 failed 结果而不是 500
        publication = note_integrations.sanitized_failure()
    task["feishu_publication"] = publication
    if publication["status"] == "uploaded":
        task["logs"].append("飞书重试上传完成")
    else:
        task["logs"].append(f"飞书重试上传失败：{publication['error']['message']}")
    _merge_task_manifest(task_id, "feishu_publication", publication)
    persist_task_runtime(task_id)
    return publication


@app.post("/api/task/{task_id}/cancel")
async def cancel_task(task_id: str) -> dict[str, Any]:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="任务已经结束")

    first_request = not task.get("_cancel_requested")
    task["_cancel_requested"] = True
    cancel_event = task.get("_cancel_event")
    if cancel_event is not None:
        cancel_event.set()
    task.update(status="cancelling", step_name="取消中", error=None)
    clear_phase_progress(task)
    task["logs"].append("已收到取消请求；正在尽快停止当前步骤")
    persist_task_runtime(task_id)
    if first_request:
        # 取消的唯一收口：直接掐掉 asyncio 任务，让 CancelledError 落在当前 await 点。
        # should_abort / cancel_event 只是让后台线程早点收工的优化，新增阶段忘了接线
        # 也不会再让取消"失效"（v1.2.3 的 412 回退把没接线的读取信息/查找字幕阶段
        # 拉长，表现为取消不动）。这一句之后不能再有 await，否则会覆盖处理器写的终态。
        job = running_jobs.get(task_id)
        if job is not None and not job.done():
            job.cancel()
    return {
        "cancelled": False,
        "status": task["status"],
        "elapsed_seconds": task_elapsed_seconds(task),
    }


@app.delete("/api/task/{task_id}")
async def delete_task(task_id: str) -> dict[str, bool]:
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    job = running_jobs.get(task_id)
    if job and not job.done():
        raise HTTPException(status_code=409, detail="任务仍在运行，请先取消并等待其停止")
    running_jobs.pop(task_id, None)
    await video_processor.cleanup(task_id)
    tasks.pop(task_id, None)
    history_cache.history_summaries.invalidate(WORKSPACE_DIR / task_id / "task.json")
    return {"deleted": True}


class MediaRetentionCleanupRequest(BaseModel):
    # strict=True：字符串 "7" 不得被宽模式悄悄当成 7 接受
    days: int = Field(strict=True)


@app.post("/api/media-retention/cleanup")
async def cleanup_media_retention(request: MediaRetentionCleanupRequest) -> dict[str, Any]:
    """失败/取消任务媒体的可选按天清理：只接受白名单天数，默认永久保留不触发。"""
    try:
        days = validate_retention_days(request.days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    active_task_ids = {
        task_id
        for task_id, task in tasks.items()
        if task.get("status") in {"pending", "queued", "processing", "cancelling"}
    }
    active_task_ids.update(
        task_id for task_id, job in running_jobs.items() if not job.done()
    )
    # A new retry may still read media from a terminal old task directory, and that
    # old task may itself reuse an even older one. Protect the whole resume_task_id
    # closure with a visited set so self/cyclic chains cannot loop.
    pending = list(active_task_ids)
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if not isinstance(current, str) or current in visited:
            continue
        visited.add(current)
        active_task_ids.add(current)
        source_id = tasks.get(current, {}).get("resume_task_id")
        if isinstance(source_id, str) and source_id not in visited:
            pending.append(source_id)
    # An active task can still read uploaded media that physically lives in the
    # workspace directory of the upload task; protect that real owner directory too.
    for task_id in tuple(active_task_ids):
        owner_id = uploaded_media_owner_id(tasks.get(task_id, {}).get("uploaded_file_path"))
        if owner_id is not None:
            active_task_ids.add(owner_id)
    return cleanup_expired_task_media(
        WORKSPACE_DIR, days=days, active_task_ids=active_task_ids
    )


def _format_page_nums(pages) -> str:
    """把分 P 对象 / 页码列表格式化为 “1、2、3”。"""
    nums = sorted(int(page.page if hasattr(page, "page") else page) for page in pages)
    return "、".join(str(num) for num in nums)


def append_asr_notes(task: dict[str, Any], whisper_result: dict[str, Any]) -> None:
    """转写阶段的降级说明与耗时入日志（单文件与 B 站多分 P 共用）。"""
    note = whisper_result.get("fallback_note")
    if note and note not in task["logs"]:
        task["logs"].append(note)
    load_seconds = float(whisper_result.get("model_load_seconds") or 0)
    if load_seconds >= 1:
        task["logs"].append(
            f"模型加载用时 {load_seconds} 秒，转写用时 "
            f"{whisper_result.get('transcribe_seconds')} 秒"
        )


async def run_queued_video_task(task_id: str, request: SummarizeRequest) -> None:
    task = tasks[task_id]
    task.update(status="queued", step_name="等待执行", progress=0)
    task["logs"].append(
        f"任务已进入队列；当前最多同时处理 {MAX_CONCURRENT_TASKS} 个任务"
    )
    persist_task_runtime(task_id)
    try:
        async with task_slots:
            raise_if_cancel_requested(task)
            await process_video_task(task_id, request)
    except asyncio.CancelledError:
        finish_task_timing(task)
        task.update(status="cancelled", step_name="已取消", error=None)
        task["logs"].append("任务已取消；已生成的中间文件将保留")
        persist_task_runtime(task_id)


async def process_video_task(task_id: str, request: SummarizeRequest) -> None:
    task = tasks[task_id]
    task["status"] = "processing"
    persist_task_runtime(task_id)

    def should_abort() -> bool:
        return bool(task.get("_cancel_requested"))

    douyin_cookie = request.douyin_cookie.model_dump() if request.douyin_cookie else None
    # 终态通知会用 title 组文案：早期失败（读凭据、取元数据）时 title 还没赋值，
    # 少了这个初值 except 分支自己会 NameError，任务就只改了内存、task.json 留在 processing
    title = request.video_url or "上传的视频"
    # B 站视频页被风控时（Issue #1）处理链会回退到开放接口直连，回退说明经这里进任务日志
    fallback_notes: list[str] = []
    # except 分支靠它决定能不能套用平台文案，而 detect_source 自己就可能抛错（非 http 链接）
    source_kind = VideoSource.LOCAL
    # 通道报错里可能整段回显本次用的明文 Key，落盘前要换成掩码；
    # 放在 try 之外初始化，因为早期失败根本没走到 resolve_llm_credentials
    used_api_key = ""

    def note_api_fallback() -> None:
        for note in fallback_notes:
            if note not in task["logs"]:
                task["logs"].append(note)

    try:
        raise_if_cancel_requested(task)
        resume_task_id = task.get("resume_task_id")
        resume_dir = task_directory(resume_task_id) if resume_task_id else None
        # 字幕导入与「复用转录」共用这条缝：转录已经在盘上了，第 1~4 步整体跳过。
        # 差别只在从哪个目录读——导入读的是本任务自己的目录（上传当场落好的）。
        transcript_dir = resume_dir or (task_directory(task_id) if task.get("subtitle_import") else None)
        source_url = request.video_url or (source_url_from_task(resume_dir) if resume_dir else None)
        uploaded_path = task.get("uploaded_file_path")
        if not uploaded_path and resume_dir:
            uploaded_media = next(
                (path for path in resume_dir.glob("input.*") if path.is_file()), None
            )
            uploaded_path = str(uploaded_media) if uploaded_media else None
        is_local = bool(uploaded_path) or not source_url
        source_kind = (
            video_processor.detect_source(source_url) if source_url else VideoSource.LOCAL
        )
        transcript_result = (
            load_transcript_result(transcript_dir) if transcript_dir else None
        )
        if transcript_dir is not None and transcript_result is None:
            raise RuntimeError("恢复转录已丢失或损坏；未执行下载或 ASR，请检查原任务后再提交")
        bili_cookie = (
            request.bilibili_cookie.model_dump() if request.bilibili_cookie else
            config_store.load_bili_credentials()
            if source_kind == VideoSource.BILIBILI and (not transcript_result or request.include_screenshots)
            else None
        )
        cookie = douyin_cookie if source_kind == VideoSource.DOUYIN else bili_cookie
        bili_pages_to_transcribe: list = []

        if transcript_result:
            set_progress(task, 1, "恢复任务信息", 8, "正在读取已有任务信息")
            info = load_reused_video_info(transcript_dir, transcript_result, source_url)
        else:
            media_input = uploaded_path or source_url or ""
            set_progress(task, 1, "读取视频信息", 8, "正在读取视频信息")
            info = await video_processor.get_video_info(
                media_input, cookie, allow_local=is_local, notes=fallback_notes
            )
            note_api_fallback()
        raise_if_cancel_requested(task)
        if is_local:
            # 上传落地文件统一叫 input.<ext>，路径推出来的标题就是占位名 input
            original_name = str(task.get("uploaded_filename") or "").strip()
            if original_name:
                info["title"] = Path(original_name).stem
        title = info["title"]
        update_task_manifest(task_id, info)
        task["logs"].append(f"标题：{title}")
        if info.get("duration"):
            task["logs"].append(f"时长：{format_duration(info['duration'])}")

        if transcript_result:
            set_progress(task, 4, "复用转录", 48, "已读取已有转录，跳过字幕、音频和 Whisper")
            if task.get("subtitle_import"):
                task["logs"].append(
                    f"已使用导入的字幕：{len(transcript_result['segments'])} 条"
                    "（跳过下载与转写）"
                )
            else:
                task["logs"].append(
                    f"复用任务 {resume_task_id} 的 {len(transcript_result['segments'])} 个转录分段"
                )
        elif request.prefer_subtitles and not is_local:
            set_progress(task, 2, "查找平台字幕", 16, "正在查找平台字幕")
            subtitle = await video_processor.fetch_subtitles(source_url or "", info, cookie)
            if subtitle:
                transcript_result = {
                    "segments": subtitle.segments,
                    "language": subtitle.language,
                    "source": subtitle.source,
                }
                task["logs"].append(
                    f"已使用平台字幕：{subtitle.language}，共 {len(subtitle.segments)} 段"
                )
            else:
                is_bilibili = (
                    video_processor.detect_source(source_url or "")
                    == VideoSource.BILIBILI
                )
                subtitle_outcome = (
                    await video_processor.fetch_bilibili_subtitles(
                        source_url or "", cookie, only_pages=request.bilibili_pages or None
                    )
                    if is_bilibili
                    else None
                )
                if subtitle_outcome is not None:
                    bili_pages_to_transcribe = list(subtitle_outcome.pages_to_transcribe)
                    if subtitle_outcome.title:
                        info["title"] = subtitle_outcome.title
                    if subtitle_outcome.pages:
                        info["duration"] = sum(
                            page.duration for page in subtitle_outcome.pages
                        ) or info.get("duration")
                        info["bili_selected_pages"] = [
                            {"page": page.page, "part": page.part}
                            for page in subtitle_outcome.pages
                        ]
                    if subtitle_outcome.total_pages:
                        info["bili_total_pages"] = subtitle_outcome.total_pages
                    if subtitle_outcome.pages or subtitle_outcome.total_pages:
                        update_task_manifest(task_id, info)
                    if subtitle_outcome.total_pages > 1:
                        task["logs"].append(
                            f"检测到 B 站分 P 视频：共 {subtitle_outcome.total_pages} 个分 P，"
                            f"本次处理 {_format_page_nums(subtitle_outcome.pages)}"
                        )
                if subtitle_outcome is not None and subtitle_outcome.result:
                    transcript_result = {
                        "segments": subtitle_outcome.result.segments,
                        "language": subtitle_outcome.result.language,
                        "source": subtitle_outcome.result.source,
                    }
                    task["logs"].append(
                        f"已使用 B 站 AI 字幕：{subtitle_outcome.result.language}，"
                        f"共 {len(subtitle_outcome.result.segments)} 段"
                    )
                    if bili_pages_to_transcribe:
                        task["logs"].append(
                            "分 P "
                            f"{_format_page_nums(bili_pages_to_transcribe)}"
                            " 无 AI 字幕，将通过语音转写补齐"
                        )
                elif subtitle_outcome is not None:
                    reason = subtitle_outcome.reason
                    if reason == "credentials_missing":
                        task["logs"].append(
                            "未读取到可用的 B 站字幕轨；AI 字幕需要填写当前账号的 "
                            "SESSDATA 等访问凭据"
                        )
                    elif reason == "no_track":
                        task["logs"].append(
                            "当前账号已登录，但该视频没有可用的 AI 字幕轨"
                        )
                    elif reason == "error":
                        task["logs"].append(
                            "读取 B 站 AI 字幕失败（网络或接口异常，"
                            f"{subtitle_outcome.detail}）"
                        )
                    elif reason == "empty":
                        task["logs"].append("B 站字幕轨存在但内容为空")
                    if bili_pages_to_transcribe:
                        task["logs"].append(
                            f"分 P {_format_page_nums(bili_pages_to_transcribe)} 将通过语音转写"
                        )
                    task["logs"].append("未找到可用平台字幕，将进行语音转写")
            title = info["title"]

        raise_if_cancel_requested(task)
        if transcript_result is None or bili_pages_to_transcribe:
            set_progress(task, 3, "准备音频", 25, "正在准备音频")
            if bili_pages_to_transcribe:
                # 多分 P：对没有 AI 字幕的分 P 逐个下载音频并转写，再按顺序合并
                whisper_by_page: dict[int, dict] = {}
                page_durations = [
                    _finite_nonnegative(page.duration)
                    for page in bili_pages_to_transcribe
                ]
                overall_asr_duration = (
                    _finite_nonnegative(sum(page_durations)) if page_durations and all(page_durations) else None
                )
                completed_asr_duration = 0.0
                for page in bili_pages_to_transcribe:
                    raise_if_cancel_requested(task)
                    set_progress(
                        task, 3, "准备音频", max(25, int(task.get("progress") or 0)),
                        f"正在下载分 P {page.page} 音频"
                    )
                    media_path = await video_processor.download_audio(
                        bilibili_page_url(source_url or "", page.page),
                        task_id,
                        cookie,
                        media_name=f"audio_p{page.page}",
                        should_abort=should_abort,
                        notes=fallback_notes,
                    )
                    note_api_fallback()
                    raise_if_cancel_requested(task)
                    set_progress(
                        task,
                        4,
                        "语音转写",
                        max(28, int(task.get("progress") or 0)),
                        f"正在转写分 P {page.page}（{request.whisper_model} 模型）",
                    )
                    whisper_result = await run_transcription(
                        media_path,
                        request.whisper_model,
                        request.use_gpu,
                        title,
                        task.get("_cancel_event"),
                        progress_callback=transcribe_progress_reporter(
                            task,
                            request.whisper_model,
                            f"分 P {page.page} ",
                            offset_seconds=completed_asr_duration,
                            overall_duration=overall_asr_duration,
                            aggregate=True,
                        ),
                    )
                    raise_if_cancel_requested(task)
                    whisper_by_page[page.page] = whisper_result
                    task["logs"].append(
                        f"分 P {page.page} 语音转写完成：{len(whisper_result['segments'])} 段，"
                        f"设备 {whisper_result['device']}"
                    )
                    append_asr_notes(task, whisper_result)
                    if whisper_result["model"] != whisper_result["requested_model"]:
                        task["logs"].append(
                            f"所选 Whisper {whisper_result['requested_model']} 未缓存或无法加载，"
                            f"已自动降级为本机缓存的 {whisper_result['model']}"
                        )
                    completed_asr_duration += (
                        _finite_nonnegative(page.duration)
                        or _finite_nonnegative(whisper_result.get("duration"))
                    )
                if subtitle_outcome is not None and subtitle_outcome.pages:
                    merged_segments, language = merge_bilibili_pages(
                        subtitle_outcome.pages,
                        dict(subtitle_outcome.subtitle_by_page),
                        whisper_by_page,
                    )
                else:
                    merged_segments = [
                        seg
                        for whisper in whisper_by_page.values()
                        for seg in (whisper.get("segments") or [])
                    ]
                    language = next(
                        (
                            str(whisper.get("language") or "zh")
                            for whisper in whisper_by_page.values()
                        ),
                        "zh",
                    )
                transcript_result = {
                    "segments": merged_segments,
                    "language": language,
                    "source": "bilibili_multi_page",
                }
                if not info.get("duration"):
                    info["duration"] = sum(
                        float(whisper.get("duration") or 0)
                        for whisper in whisper_by_page.values()
                    )
                task["logs"].append(f"分 P 转录合并完成：共 {len(merged_segments)} 段")
            elif transcript_result is None:
                set_progress(task, 3, "准备音频", 25, "正在准备音频")
                reused_audio = None
                if resume_dir:
                    reused_audio = next(
                        (path for path in resume_dir.glob("audio.*") if path.is_file()), None
                    )
                if reused_audio:
                    media_path = reused_audio
                    task["logs"].append(f"复用已有音频：{reused_audio.name}")
                elif is_local:
                    media_path = Path(uploaded_path)
                else:
                    media_path = await video_processor.download_audio(
                        source_url or "", task_id, cookie, should_abort=should_abort,
                        notes=fallback_notes,
                    )
                raise_if_cancel_requested(task)
                note_api_fallback()
                set_progress(
                    task,
                    4,
                    "语音转写",
                    28,
                    f"正在加载 {request.whisper_model}（未缓存时可能下载模型）",
                )
                whisper_result = await run_transcription(
                    media_path,
                    request.whisper_model,
                    request.use_gpu,
                    title,
                    task.get("_cancel_event"),
                    progress_callback=transcribe_progress_reporter(
                        task, request.whisper_model
                    ),
                )
                raise_if_cancel_requested(task)
                transcript_result = {
                    "segments": whisper_result["segments"],
                    "language": whisper_result["language"],
                    "source": (
                        "paraformer"
                        if request.whisper_model == "paraformer-zh"
                        else "faster_whisper"
                    ),
                }
                if not info.get("duration"):
                    info["duration"] = whisper_result["duration"]
                task["logs"].append(
                    f"语音转写完成：{len(whisper_result['segments'])} 段，设备 {whisper_result['device']}"
                )
                append_asr_notes(task, whisper_result)
                if whisper_result["model"] != whisper_result["requested_model"]:
                    task["logs"].append(
                        f"所选 Whisper {whisper_result['requested_model']} 未缓存或无法加载，"
                        f"已自动降级为本机缓存的 {whisper_result['model']}"
                    )

        segments: list[TranscriptSegment] = transcript_result["segments"]
        if not segments:
            raise RuntimeError("没有从视频中获得可总结的文字")
        quality = transcript_quality(segments, float(info.get("duration") or 0))
        transcript_result["quality"] = quality
        task["logs"].append(
            f"文字质量检查：{quality['characters']} 字，语音覆盖 {quality['speech_coverage']:.0%}"
        )
        await write_transcript_files(task_id, segments, transcript_result)
        if (
            transcript_result["source"] in {"faster_whisper", "paraformer"}
            and quality["insufficient"]
        ):
            stage = "调用大模型" if request.output == "note" else "返回转录"
            raise RuntimeError(
                f"可识别语音覆盖过低，已在{stage}前停止。源视频可能被静音、替换、"
                "受版权或审核限制，或主要内容并非语音；请先检查原视频。"
            )

        if request.output == "transcript":
            # 正文只留在 transcript.json / transcript.md：result 会被 wait_for_task
            # 每 2 秒轮询一次并由 persist_task_runtime 反复落盘，不能放大文本
            elapsed = finish_task_timing(task)
            # 归档读的是刚落盘的那份 transcript.md（与下载端点同一个文件），
            # 不在这里重新拼一遍格式。失败只记固定警告，绝不改判任务。
            archived_path: Path | None = None
            try:
                transcript_markdown = (
                    WORKSPACE_DIR / task_id / "transcript.md"
                ).read_text(encoding="utf-8")
            except OSError:
                transcript_markdown = ""
            if transcript_markdown:
                try:
                    archived_path = archive_note(
                        download_stem(title, info, "transcript"),
                        transcript_markdown,
                        folder=TRANSCRIPTS_DIR_NAME,
                    )
                except Exception:
                    archived_path = None
            if archived_path:
                task["logs"].append(f"转录稿已归档：{archived_path}")
            else:
                task["logs"].append(
                    "转录稿未能归档到 workspace/transcripts（任务内 transcript.md 仍可下载）"
                )
            task["result"] = {
                "title": title,
                "output": "transcript",
                "source": VideoSource.LOCAL.value if is_local else info.get("source", "other"),
                "duration": info.get("duration", 0),
                "segment_count": len(segments),
                "characters": quality["characters"],
                "transcript_source": transcript_result["source"],
                "transcript_language": transcript_result["language"],
                "transcript_quality": quality,
                "output_directory": str(WORKSPACE_DIR / task_id),
                "archived_path": str(archived_path) if archived_path else None,
                "processing_seconds": elapsed,
            }
            task.update(
                status="completed", step=7, step_name="转录完成", progress=100, error=None
            )
            task["logs"].append(
                f"转录完成：{len(segments)} 段，可用 GET /api/task/{task_id}/transcript 取正文"
            )
            notify_task("转录完成", f"已生成带时间轴转录：{title}")
            persist_task_runtime(task_id)
            return

        screenshots: list[Path] = []
        if request.include_screenshots:
            set_progress(task, 5, "提取截图", 50, "正在提取低清预览截图")
            video_path = (
                Path(uploaded_path)
                if is_local
                else await video_processor.download_preview_video(
                    source_url or "", task_id, cookie, should_abort=should_abort,
                    notes=fallback_notes,
                )
            )
            note_api_fallback()
            screenshots = await video_processor.extract_frames(
                video_path, task_id, request.screenshot_interval, should_abort
            )
            raise_if_cancel_requested(task)
            task["logs"].append(f"已提取 {len(screenshots)} 张截图")

        transcript_characters = int(quality.get("characters") or 0)
        duration_seconds = float(info.get("duration") or 0)
        advisory = ""
        if (
            transcript_characters > LONG_TRANSCRIPT_CHARACTERS
            and request.summary_style != "concise"
        ):
            advisory = (
                "这段内容很长，笔记会按时间顺序逐段完整记录（不做预先压缩），"
                "因此 Token 消耗与耗时都随时长增长，输出量与口播字数同量级。"
                "3 小时量级的课可能要几十分钟才出稿（限流的免费通道更慢），"
                "挂着等即可，任何时候都能取消。想省一些可以改用「精简摘要」。"
            )
        elif transcript_characters >= 9_000 or duration_seconds >= 1_800:
            advisory = (
                "这段内容较长，将通过多轮整理生成完整笔记，耗时和 Token 消耗会相应增加。"
                "上下文容量较大、指令理解能力较强的模型通常更稳定；免费或轻量模型可能出现遗漏或截断。"
            )
        if advisory:
            task["advisory"] = advisory
            task["logs"].append(advisory)
        set_progress(task, 6, "生成笔记", 55, "正在规划笔记生成流程")
        # 提交时已快照：此处读到的是不可变快照，模板后续的修改/删除不影响本任务
        template_snapshot = resolve_task_template_snapshot(task_id, request)
        task["logs"].append(f"笔记模板：{template_snapshot.get('name')}")
        config = request.llm_config
        base_url = config.base_url or config.custom_base_url
        model = config.model or config.custom_model_name
        api_key, key_source = resolve_llm_credentials(
            model_type=config.model_type,
            base_url=base_url,
            api_key=config.api_key.get_secret_value(),
        )
        used_api_key = api_key
        summarizer = LLMSummarizer(
            model_type=config.model_type,
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        resolved_model = getattr(summarizer, "model", None) or model
        task["logs"].append(
            f"调用模型：Provider={config.model_type}，Model={resolved_model}，"
            f"Base URL={base_url}，Key={key_source}"
        )
        task["logs"].append(
            f"推理设置：{summarizer.describe_effort(request.reasoning_effort, request.summary_style)}"
        )

        async def report_llm_progress(progress: int, message: str) -> None:
            raise_if_cancel_requested(task)
            mapped = 55 + round(max(0, min(100, progress)) * 0.44)
            set_progress(task, 6, "生成笔记", mapped, message)

        summary = await summarizer.generate_summary(
            title,
            segments,
            {
                "owner": info.get("owner"),
                "published_at": format_publish_time(info),
                "duration_text": format_duration(info.get("duration", 0)),
                "view_count": info.get("view_count") or 0,
                "like_count": info.get("like_count") or 0,
                "transcript_source": transcript_result["source"],
                "description": (info.get("description") or "")[:600],
            },
            style=request.summary_style,
            reasoning_effort=request.reasoning_effort,
            progress_callback=report_llm_progress,
            should_abort=should_abort,
            organization_instructions=template_snapshot.get("instructions") or "",
        )
        raise_if_cancel_requested(task)
        for warning in getattr(summarizer, "warnings", []):
            # 告警会把网关异常原文嵌进来，落盘前必须过一遍脱敏
            cleaned = redact_secrets(warning, api_key)
            if cleaned not in task["logs"]:
                task["logs"].append(cleaned)
        summary = add_note_header_metadata(summary, title, info)
        if screenshots:
            summary += "\n\n## 视频截图\n\n" + "\n\n".join(
                f"![截图 {index}](./{FRAMES_DIR_NAME}/{path.name})"
                for index, path in enumerate(screenshots, start=1)
            )
        # 确定性收尾：布局包住草稿（草稿自带的文档标题交给布局的标题占位符），
        # 再生成 YAML Frontmatter；均不触发额外的大模型调用。
        note_values: dict[str, Any] = {
            "title": title,
            "source_url": source_url,
            "platform": (
                VideoSource.LOCAL.value if is_local else info.get("source", "other")
            ),
            "author": info.get("owner") or None,
            "published_at": format_publish_time(info),
            "duration": (
                format_duration(info.get("duration", 0)) if info.get("duration") else None
            ),
            "created_at": task.get("created_at"),
            "transcript_source": transcript_result["source"],
            "template_name": template_snapshot.get("name") or "",
        }
        note_values["template"] = note_values["template_name"]
        content = strip_document_heading(summary)
        note_text = note_templates.render_note(
            template_snapshot["layout"], note_values, content
        )
        summary = append_note_footer(
            note_text,
            source_url,
            config.model_type,
            resolved_model,
            request.summary_style,
        )

        task_dir = WORKSPACE_DIR / task_id
        (task_dir / "notes.md").write_text(summary, encoding="utf-8")
        archived_path = archive_note(
            download_stem(title, info), summary, task_id, request.note_destination
        )
        if archived_path:
            task["logs"].append(f"笔记已归档：{archived_path}")
        elapsed = finish_task_timing(task)
        task["result"] = {
            "title": title,
            "markdown": summary,
            "source": VideoSource.LOCAL.value if is_local else info.get("source", "other"),
            "duration": info.get("duration", 0),
            "screenshot_count": len(screenshots),
            "transcript_source": transcript_result["source"],
            "transcript_language": transcript_result["language"],
            "segment_count": len(segments),
            "transcript_quality": quality,
            "output_directory": str(task_dir),
            "archived_path": str(archived_path) if archived_path else None,
            "processing_seconds": elapsed,
            "note_template_id": template_snapshot.get("id"),
            "note_template_version": template_snapshot.get("version"),
        }
        task.update(
            status="completed", step=7, step_name="完成", progress=100, error=None
        )
        task["logs"].append("视频笔记生成完成")
        persist_task_runtime(task_id)
        # 成功通知必须在完成态落盘之后：否则持久化失败时用户会先收成功、
        # 再收外层失败分支的失败通知，两条互相矛盾。
        notify_task("任务完成", f"视频笔记已生成：{title}")
        # 飞书发布（opt-in）：本地笔记与归档已成功，上传失败不改判任务。
        feishu_token = resolve_feishu_target(task_id, request)
        if feishu_token is not None:
            # 直接走管线（测试 harness 等绕过提交入口）时 manifest 可能缺少
            # feishu_upload 快照，这里补写，保证重试端点能读到上传目标。
            try:
                _merge_task_manifest(
                    task_id, "feishu_upload", {"folder_token": feishu_token}
                )
            except OSError:
                task["logs"].append("飞书上传目标未能写入 task.json（仅影响日志完整性）")
            try:
                publication = note_integrations.publish_note(
                    note_text=(task_dir / "notes.md").read_text(encoding="utf-8"),
                    task_dir=task_dir,
                    title=title,
                    folder_token=feishu_token,
                    staging_builder=build_feishu_docx_staging,
                )
            except Exception:
                # 发布是 best-effort：任何漏网异常都降级为脱敏失败，
                # 已完成并落盘的本地笔记绝不能被改判 failed
                publication = note_integrations.sanitized_failure()
            task["feishu_publication"] = publication
            if publication["status"] == "uploaded":
                task["logs"].append("飞书上传完成")
            else:
                task["logs"].append(
                    f"飞书上传失败（不影响本地笔记，可在任务页重试）："
                    f"{publication['error']['message']}"
                )
            try:
                _merge_task_manifest(task_id, "feishu_publication", publication)
            except OSError:
                task["logs"].append("飞书上传结果未能写入 task.json（仅影响日志完整性）")
        # 完成态已经成功落盘，此后才允许清理本任务的源媒体与中间文件：
        # 若清理先于持久化，完成态写盘失败会把任务改判 failed，
        # 而重试媒体已经被删，违反「失败任务保留重试材料」。
        # 清理只碰当前任务目录；清理失败降级为警告，不改判任务状态。
        removed_media, cleanup_warnings = cleanup_successful_task_media(task_id)
        if removed_media:
            task["logs"].append(
                f"已清理源媒体与中间文件：{'、'.join(removed_media)}"
            )
        for cleanup_warning in cleanup_warnings:
            task["logs"].append(f"媒体清理警告：{cleanup_warning}")
        if removed_media or cleanup_warnings or feishu_token is not None:
            # best-effort 二次持久化清理结果：即使失败也不能让异常逃到外层
            # 失败分支——完成态已经落盘，任务不允许被改回 failed。
            try:
                persist_task_runtime(task_id)
            except Exception:
                task["logs"].append("媒体清理结果未能写入 task.json（仅影响日志完整性）")
    except asyncio.CancelledError:
        finish_task_timing(task)
        task.update(status="cancelled", step_name="已取消", error=None)
        if not task["logs"] or "用户已取消任务" not in task["logs"][-1]:
            task["logs"].append("任务已取消；已生成的中间文件将保留")
        persist_task_runtime(task_id)
    except Exception as exc:
        finish_task_timing(task)
        raw = str(exc)
        # 失败文案有三条出口（error 字段、任务日志、系统通知），未知异常时
        # friendly_* 会原样返回底层文本，网关回显的明文 Key 就会跟着落进 task.json
        message = redact_secrets(
            friendly_task_error(
                raw, source=source_kind, step_name=task.get("step_name", "")
            ),
            used_api_key,
        )
        task.update(status="failed", error=message)
        task["logs"].append(f"处理失败：{message}")
        if message != raw:
            # 文案一旦被替换掉，真实的返回码就没人能看到了——这次误诊就是这么来的
            task["logs"].append(f"底层错误：{scrub_technical_error(raw, used_api_key)}")
        notify_task("任务失败", f"{title}\n{message}")
        persist_task_runtime(task_id)


async def write_transcript_files(
    task_id: str, segments: list[TranscriptSegment], metadata: dict[str, Any]
) -> None:
    """转录文件先写 .tmp 再改名。

    取消能落在任意 await 点（见 cancel_task），而「复用转录」以 transcript.json
    是否存在为准——半截文件会比没有文件更糟。
    """
    task_dir = WORKSPACE_DIR / task_id
    json_payload = {
        "language": metadata["language"],
        "source": metadata["source"],
        "quality": metadata.get("quality"),
        "segments": [segment.to_dict() for segment in segments],
    }
    await _write_atomically(
        task_dir / "transcript.json",
        (json.dumps(json_payload, ensure_ascii=False, indent=2),),
    )
    await _write_atomically(
        task_dir / "transcript.md",
        ("# 带时间戳转录\n\n", segments_to_prompt(segments), "\n"),
    )


async def _write_atomically(path: Path, chunks: tuple[str, ...]) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    async with aiofiles.open(temporary, "w", encoding="utf-8") as file:
        for chunk in chunks:
            await file.write(chunk)
    os.replace(temporary, path)


def friendly_task_error(
    message: str,
    *,
    source: VideoSource | None = None,
    step_name: str = "",
) -> str:
    """把已知的平台限制错误转成对用户友好的提示。

    平台文案只在对应平台的任务里出现，模型通道的错误不套平台说法：v1.4.0 之前
    任何含 403 的异常都说成「抖音媒体地址已过期」，而实际触发它的是 B 站任务里
    模型接口返回的 403，用户据此重投了三次没问题的链接。
    """
    lowered = message.lower()
    if "certificate_verify_failed" in lowered or "certificate verify failed" in lowered:
        return (
            "Whisper 模型下载时 TLS 证书校验失败。程序已尝试备用下载源；"
            "如果仍失败，请检查系统时间、网络代理或企业根证书，"
            "并通过 HF_ENDPOINT 指定能正常验证证书的镜像后重试。"
        )
    if step_name == NOTE_STEP_NAME:
        return friendly_llm_error(lowered, message)
    if source == VideoSource.DOUYIN:
        if "fresh cookies" in lowered or "challenge" in lowered or "验证码" in message:
            return "抖音要求浏览器验证。点击输入区下方的“打开抖音浏览器”，完成登录/验证后重新提交。"
        if "403" in lowered or "forbidden" in lowered:
            return "抖音媒体地址已过期或被拒绝，请重新提交链接；如果仍失败，先用本机抖音浏览器完成验证。"
        if "douyin" in lowered or "iesdouyin" in lowered or "抖音" in message:
            return DOUYIN_HINT
    if source == VideoSource.BILIBILI and any(
        marker in lowered for marker in ("403", "412", "forbidden", "precondition")
    ):
        return (
            "B 站拒绝了本次请求（风控或访问凭据失效）。请在「B 站访问凭据」里重新扫码导入 "
            "SESSDATA 后重投链接；也可以稍等几分钟再试。"
        )
    return message


# 各家对"上下文窗口不够"的说法不一样（ollama 两种、OpenAI/vLLM 一种、LM Studio 一种），
# 但都带这些字样。刻意不含 "too many tokens"：OpenAI 限流的原文就是
# "Too many tokens per minute"，按它判会把限流说成窗口不够。
_CONTEXT_LIMIT_MARKERS = (
    "context_length_exceeded",
    "context length",
    "context window",
    "prompt is too long",
    "num_ctx",
    "maximum capacity of",
)


def friendly_llm_error(lowered: str, message: str) -> str:
    """生成笔记阶段的失败来自模型通道，重投视频链接不会有任何改变。"""
    # 放在额度/429 之前：下面几条判的是裸子串 "429"/"403"，而本类报错里的数字是
    # token 数（requested 9403 tokens 就含 "403"），先判会把窗口不够说成权限问题。
    if any(marker in lowered for marker in _CONTEXT_LIMIT_MARKERS):
        return (
            "模型的上下文窗口装不下本次请求（这是模型侧的容量上限，不是本程序的笔记长度设置）。"
            "本地模型（ollama / LM Studio / llama.cpp）请把上下文调到 16K 以上再重投："
            "ollama 设 OLLAMA_CONTEXT_LENGTH=16384 后重启服务，或在 Modelfile 里写 "
            "num_ctx 16384。在线通道多为该模型或网关的上限较低，"
            "可换上下文更大的模型，或改用「精简摘要」减少单次送入的材料。"
        )
    if "insufficient_quota" in lowered or "quota" in lowered or "余额" in message:
        return (
            "模型通道的额度或余额不足，笔记生成中断。"
            "请在「模型配置」里换一个通道（Base URL 与 Key），或给当前通道续额后重投。"
        )
    if "429" in lowered or "rate limit" in lowered or "too many requests" in lowered:
        return (
            "模型通道限流。可以稍后重投，或改用付费通道；"
            "长视频换用「精简摘要」能明显减少请求数。"
        )
    if "401" in lowered or "invalid_api_key" in lowered or "incorrect api key" in lowered:
        return (
            "模型接口拒绝了本机保存的 Key（401）。"
            "请在「模型配置」里重新填写该 Base URL 对应的 Key 后重投。"
        )
    if "403" in lowered or "permission" in lowered or "forbidden" in lowered:
        return (
            "模型接口拒绝了本次请求（403）：本机保存的 Key 可能没有该模型的权限，"
            "或 Base URL 与模型名不匹配。请核对「模型配置」后重投，"
            "任务日志里「调用模型」一行就是本次实际使用的通道。"
        )
    if "404" in lowered or "not found" in lowered or "does not exist" in lowered:
        return "模型接口找不到该模型（404）。请检查「模型配置」里的模型名与 Base URL。"
    if "timeout" in lowered or "timed out" in lowered or "connection" in lowered:
        return "与模型接口的连接中断，多为网络抖动或通道限流。可以直接重投任务，或换一个通道。"
    return message


def redact_secrets(text: str, secret: str = "") -> str:
    """把文本里的凭据换成掩码。

    比正则更可靠的一层是 `secret`：调用方手里就有本次用的明文 Key，
    整串替换不依赖网关把回显写成什么格式。
    """
    cleaned = API_KEY_PATTERN.sub("sk-****", text)
    cleaned = SECRET_ECHO_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}****", cleaned
    )
    if secret and len(secret) >= 8:
        cleaned = cleaned.replace(secret, secret_box.mask_secret(secret))
    return cleaned


_PATH_IN_TEXT_RE = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'<>|]+|\\\\[^\s\"'<>|]+|/(?:[^\s/\"'<>|]+/)+[^\s/\"'<>|]*)"
)


def redact_paths(text: str) -> str:
    """把明显的本机路径替换掉，避免错误回显目录结构。"""
    return _PATH_IN_TEXT_RE.sub("<路径>", text)


def scrub_technical_error(raw: str, secret: str = "") -> str:
    """异常文本进日志前的脱敏与截断：通道报错可能整段回显 JSON。"""
    return redact_secrets(" ".join(raw.split()), secret)[:400]


def format_duration(seconds: float) -> str:
    if not seconds:
        return "未知"
    return format_timestamp(float(seconds))


def strip_document_heading(text: str) -> str:
    """去掉草稿首行的成品文档标题：布局里的 {{title}} 才是文档标题的唯一来源。

    只剥「# 视频笔记：《…》」这一种成品标题（管线提示词与兜底标题都固定长这样）；
    模型自拟的其他一级标题属于正文内容，保留。独立成模块函数——测试与复用路径
    会把 main.LLMSummarizer 整体换成假类，不能依赖类上的静态方法。
    """
    lines = text.strip().splitlines()
    if (
        lines
        and lines[0].startswith("# 视频笔记：《")
        and lines[0].endswith("》")
    ):
        lines.pop(0)
    return "\n".join(lines).strip()


def format_bytes_size(num_bytes: float) -> str:
    """把字节数格式化为人类可读大小（MB / GB）。"""
    size = max(0.0, float(num_bytes))
    if size >= 1024 * 1024 * 1024:
        return f"{size / (1024 ** 3):.2f} GB"
    return f"{size / (1024 ** 2):.2f} MB"


def format_publish_time(info: dict[str, Any]) -> str:
    """优先使用 yt-dlp 的发布日期；没有日期时再使用 Unix 时间戳。"""
    raw_date = str(info.get("upload_date") or info.get("release_date") or "").strip()
    if len(raw_date) == 8 and raw_date.isdigit():
        return f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
    raw_timestamp = info.get("timestamp") or info.get("release_timestamp")
    try:
        timestamp = float(raw_timestamp)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


def add_note_header_metadata(summary: str, title: str, info: dict[str, Any]) -> str:
    """在模型标题下放置可验证的视频元信息，不让模型负责记住固定排版。"""
    value = summary.strip()
    lines = value.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).lstrip()
    else:
        heading = f"# 视频笔记：《{title}》"
        body = value

    body = strip_model_metadata_block(body)

    metadata: list[str] = []
    owner = str(info.get("owner") or "").strip()
    published_at = format_publish_time(info)
    duration = format_duration(info.get("duration", 0))
    view_count = int(info.get("view_count") or 0)
    like_count = int(info.get("like_count") or 0)
    if owner:
        metadata.append(f"UP主：{owner}")
    if published_at:
        metadata.append(f"发布时间：{published_at}")
    if duration != "未知":
        metadata.append(f"时长：{duration}")
    if view_count > 0:
        metadata.append(f"播放：{view_count:,}")
    if like_count > 0:
        metadata.append(f"点赞：{like_count:,}")
    if not metadata:
        return value or heading
    metadata_block = "> " + " · ".join(metadata)
    return f"{heading}\n\n{metadata_block}" + (f"\n\n{body}" if body else "")


def strip_model_metadata_block(body: str) -> str:
    """移除模型紧跟标题生成的重复元信息，保留正文内容。

    提示词已经把作者、时间、时长和文字来源作为参考资料传给模型，
    但模型仍可能输出一行 ``作者：…｜发布时间：…``。这些字段由代码
    确定性写入标题下方，因此只清理标题后的重复元信息块。
    """
    lines = body.splitlines()
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    start = index
    metadata_labels = ("作者", "UP主", "发布时间", "时长", "播放", "点赞", "文字来源")
    removed = 0
    while index < len(lines):
        line = lines[index].strip().lstrip("> ")
        label_count = sum(f"{label}：" in line or f"{label}:" in line for label in metadata_labels)
        if label_count < 2:
            break
        removed += 1
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
    if not removed:
        return body
    return "\n".join(lines[index:]).lstrip()


def summary_style_label(style: str) -> str:
    return {
        "detailed": "详细笔记 + 点评分析",
        "faithful": "详细复原（仅视频内容）",
        "concise": "精简摘要",
    }.get(style, style)


def append_note_footer(
    summary: str,
    source_url: str | None,
    model_type: str,
    model: str | None,
    style: str,
) -> str:
    """确定性追加来源与生成配置，避免不同风格遗漏关键追溯信息。"""
    source = source_url.strip() if source_url else ""
    source_line = source or "本地文件（未提供视频链接）"
    model_line = model.strip() if model else "未指定模型"
    footer = "\n".join(
        [
            "---",
            f"来源：{source_line}",
            f"生成模型：{model_type} · {model_line}",
            f"笔记风格：{summary_style_label(style)}",
        ]
    )
    return f"{summary.rstrip()}\n\n{footer}\n"


SAFE_NAME_LIMIT = 80


def _sanitize_name_text(value: str) -> str:
    """只去掉 Windows 非法字符与控制字符，保留中文标点。"""
    invalid = set('\\/:*?"<>|')
    cleaned = "".join(
        char for char in str(value) if char not in invalid and ord(char) >= 32
    )
    return cleaned.strip()


def _safe_filename(value: str) -> str:
    """把标题清洗为安全的文件名：只去掉 Windows 非法字符，保留中文标点。"""
    return (_sanitize_name_text(value) or "video-notes")[:SAFE_NAME_LIMIT]


def download_stem(title: str, meta: dict[str, Any], output: str = "note") -> str:
    """产物文件名主干（不含扩展名），下载、压缩包、归档和网页端共用。

    B 站分 P 与纯转录都要带进名字：同一视频逐 P 跑出来的笔记、以及同一视频
    先转写后生成的两份产物，否则在下载目录里只剩一串相同或时间戳文件名。
    分 P 标记与转录正文里用的「【P3 分P名】」保持同一写法；80 字预算优先保后缀。
    """
    base = _sanitize_name_text(title) or "video-notes"
    raw_pages = meta.get("bili_selected_pages")
    pages = [
        page
        for page in (raw_pages if isinstance(raw_pages, list) else [])
        if isinstance(page, dict)
        and isinstance(page.get("page"), int)
        and not isinstance(page.get("page"), bool)
    ]
    raw_total = meta.get("bili_total_pages")
    total = (
        raw_total
        if isinstance(raw_total, int) and not isinstance(raw_total, bool)
        else 0
    )
    descriptor = ""
    part = ""
    if total > 1 and pages:
        if len(pages) == 1:
            descriptor = f"P{pages[0]['page']}"
            part = _sanitize_name_text(str(pages[0].get("part") or ""))
        elif len(pages) < total:
            descriptor = f"P{_format_page_nums([page['page'] for page in pages])}"
    transcript = "【转录】" if output == "transcript" else ""
    suffix = (
        f"【{descriptor}{(' ' + part) if part else ''}】{transcript}"
        if descriptor
        else transcript
    )
    if len(base) + len(suffix) > SAFE_NAME_LIMIT:
        base = base[: max(1, SAFE_NAME_LIMIT - len(suffix))].rstrip() or "v"
    if len(base) + len(suffix) > SAFE_NAME_LIMIT and part:
        minimal = f"【{descriptor}】{transcript}"
        room = SAFE_NAME_LIMIT - len(base) - len(minimal) - 1
        part = part[: max(0, room)].rstrip()
        suffix = f"【{descriptor} {part}】{transcript}" if part else minimal
    if len(base) + len(suffix) > SAFE_NAME_LIMIT:
        room = SAFE_NAME_LIMIT - len(base) - len("【】") - len(transcript)
        descriptor = descriptor[: max(1, room)].rstrip()
        suffix = f"【{descriptor}】{transcript}" if descriptor else transcript
    return _safe_filename(f"{base}{suffix}")


def rewrite_note_image_refs(content: str, prefix: str) -> str:
    return NOTE_IMAGE_REF_RE.sub(
        lambda match: f"{match.group(1)}{prefix}{FRAMES_DIR_NAME}/{match.group(2)})",
        content,
    )


def rewrite_exported_note_image_refs(
    content: str, attachment_dir: str, attachment_names: set[str]
) -> str:
    def replace(match: re.Match[str]) -> str:
        name = Path(unquote(match.group(2))).name
        if name not in attachment_names:
            return match.group(0)
        encoded_dir = quote(attachment_dir, safe="")
        encoded_name = quote(name, safe="")
        return f"{match.group(1)}./{encoded_dir}/{encoded_name})"

    return NOTE_IMAGE_REF_RE.sub(replace, content)


def opened_file_identity(handle: Any) -> tuple[int, int] | None:
    """返回可用于失败清理的稳定文件身份；不可靠时放弃删除。"""
    try:
        stat = os.fstat(handle.fileno())
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(stat.st_dev, int) or not isinstance(stat.st_ino, int):
        return None
    if stat.st_ino == 0:
        return None
    return stat.st_dev, stat.st_ino


def unlink_if_identity_matches(path: Path, identity: tuple[int, int] | None) -> bool:
    """仅删除仍指向本次排他创建文件的路径。"""
    if identity is None:
        return False
    try:
        current = path.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != identity:
            return False
        path.unlink()
        return True
    except OSError:
        return False


def archive_note(
    title: str,
    content: str,
    task_id: str | None = None,
    destination: str | Path | None = None,
    *,
    folder: str = NOTES_DIR_NAME,
) -> Path | None:
    """归档最终笔记；自定义目的地同时复制正文实际引用的任务附件。

    留空目的地时保持原行为：归档到 workspace/notes，不复制截图，引用改写为
    ../<task_id>/frames/。自定义目的地写入失败会抛出稳定错误，让任务进入失败状态。

    folder 只允许 notes / transcripts；destination 非空时继续完全走自定义目的地，
    folder 不改变目标目录。

    默认归档写入失败仍返回 None，以保持上游兼容行为。
    """
    if folder not in {NOTES_DIR_NAME, TRANSCRIPTS_DIR_NAME}:
        raise ValueError("unsupported archive folder")
    notes_root = Path(destination) if destination else WORKSPACE_DIR / folder
    if destination:
        task_dir = WORKSPACE_DIR / task_id if task_id else WORKSPACE_DIR
        attachments = referenced_note_attachments(content, task_dir)
        try:
            notes_root.mkdir(parents=True, exist_ok=True)
            safe = _safe_filename(title)
            index = 1
            while True:
                stem = safe if index == 1 else f"{safe}-{index}"
                candidate = notes_root / f"{stem}.md"
                attachment_dir = f"{stem}-attachments"
                attachment_root = notes_root / attachment_dir
                if candidate.exists() or attachment_root.exists():
                    index += 1
                    continue
                created_attachments = False
                created_note_identity: tuple[int, int] | None = None
                created_files: list[tuple[Path, tuple[int, int] | None]] = []

                def clean_up_created_paths() -> None:
                    unlink_if_identity_matches(candidate, created_note_identity)
                    for path, identity in reversed(created_files):
                        unlink_if_identity_matches(path, identity)
                    if created_attachments:
                        try:
                            attachment_root.rmdir()
                        except OSError:
                            pass

                try:
                    if attachments:
                        attachment_root.mkdir(exist_ok=False)
                        created_attachments = True
                        for name, source in attachments:
                            target = attachment_root / name
                            with source.open("rb") as source_handle, target.open(
                                "xb"
                            ) as target_handle:
                                created_files.append(
                                    (target, opened_file_identity(target_handle))
                                )
                                shutil.copyfileobj(source_handle, target_handle)
                    exported = rewrite_exported_note_image_refs(
                        content, attachment_dir, {name for name, _ in attachments}
                    )
                    with candidate.open("x", encoding="utf-8") as handle:
                        created_note_identity = opened_file_identity(handle)
                        handle.write(exported)
                    return candidate
                except FileExistsError:
                    clean_up_created_paths()
                    index += 1
                except OSError:
                    clean_up_created_paths()
                    raise
        except OSError as exc:
            raise RuntimeError(
                "导出笔记失败：请检查笔记目的地和目录写入权限"
            ) from exc

    if task_id:
        content = rewrite_note_image_refs(content, f"../{task_id}/")
    try:
        notes_root.mkdir(parents=True, exist_ok=True)
        safe = _safe_filename(title)
        index = 1
        while True:
            stem = safe if index == 1 else f"{safe}-{index}"
            candidate = notes_root / f"{stem}.md"
            created_note_identity: tuple[int, int] | None = None
            try:
                with candidate.open("x", encoding="utf-8") as handle:
                    created_note_identity = opened_file_identity(handle)
                    handle.write(content)
                return candidate
            except FileExistsError:
                index += 1
            except OSError:
                unlink_if_identity_matches(candidate, created_note_identity)
                return None
    except OSError:
        return None


def restore_tasks_from_workspace() -> None:
    """Rebuild recent task status from manifests after a service restart."""
    try:
        candidates = sorted(
            (
                path
                for path in WORKSPACE_DIR.iterdir()
                if path.is_dir() and (path / "task.json").is_file()
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:TASK_HISTORY_LIMIT]
    except OSError:
        return

    for task_dir in candidates:
        # 启动时仍只预加载最近 TASK_HISTORY_LIMIT 条；更旧任务由详情接口按需恢复。
        restore_task_on_demand(task_dir.name)


restore_tasks_from_workspace()


# MCP 端点：SSE 传输（/mcp/sse，供 Cherry Studio 等 MCP 客户端接入）
MCP_SSE_ENABLED = False
try:
    from .mcp_server import use_in_process_backend, mcp as mcp_app
    # 同进程调用端点函数：HTTP 自调会被 SSE 长连接阻塞（自调死锁）
    use_in_process_backend()
    app.mount("/mcp", mcp_app.sse_app())
    MCP_SSE_ENABLED = True
except ImportError:
    # mcp 依赖未安装时跳过，不影响主服务
    pass


@app.get("/icon.png", include_in_schema=False)
async def app_icon() -> FileResponse:
    if not APP_ICON_PATH.is_file():
        raise HTTPException(status_code=404, detail="应用图标不存在")
    return FileResponse(APP_ICON_PATH, media_type="image/png")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    if not FAVICON_PATH.is_file():
        raise HTTPException(status_code=404, detail="应用图标不存在")
    return FileResponse(FAVICON_PATH, media_type="image/x-icon")


if FRONTEND_DIR.is_dir():
    app.mount(
        "/",
        NoCacheStaticFiles(directory=FRONTEND_DIR, html=True),
        name="frontend",
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    product_info.set_env_aliases("BACKEND_URL", f"http://127.0.0.1:{port}")
    uvicorn.run(
        "backend.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=port,
        reload=os.getenv("RELOAD", "false").lower() == "true",
        proxy_headers=False,
    )
