"""本机抖音登录态管理。

每次登录使用本次会话独占的临时浏览器 profile；登录成功、取消、超时、
启动失败、异常退出或新会话替换旧会话时，都会尝试删除该临时目录；
删除失败会向调用方报告，绝不静默宣称已清理。
API 返回的 cookie 只存在当前进程内存中，供一次 yt-dlp 请求使用，
不写入 task.json、日志或任何持久文件。
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import websockets

LOGIN_URL = "https://www.douyin.com/"
SESSION_TTL_SECONDS = 300
CDP_PORT_START = 9343
CDP_PORT_COUNT = 10
BROWSER_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
COOKIE_NAMES = (
    "msToken", "ttwid", "odin_tt", "passport_csrf_token", "sid_guard",
    "sessionid", "sessionid_ss", "s_v_web_id", "__ac_nonce",
    "__ac_signature", "tt_scid", "csrf_session_id",
)


def find_browser() -> str | None:
    return next((path for path in BROWSER_PATHS if os.path.isfile(path)), None)


def free_cdp_port() -> int | None:
    for port in range(CDP_PORT_START, CDP_PORT_START + CDP_PORT_COUNT):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return None


@dataclass
class DouyinLoginSession:
    browser_path: str
    profile_dir: Path
    cdp_port: int
    started_at: float
    process: subprocess.Popen[Any] | None = field(default=None)
    state: str = "waiting"
    message: str = "请在抖音窗口中完成登录或验证"
    cookies: dict[str, str] | None = None


class DouyinLoginManager:
    # 临时 Profile 专用前缀：清理时按「根目录归属 + 前缀」双重校验，
    # 任何不匹配的路径都拒绝删除，防止误伤用户浏览器 Profile 或其他目录。
    PROFILE_PREFIX = "v2k-douyin-profile-"

    def __init__(self, profile_root: Path) -> None:
        self.profile_root = profile_root
        self.session: DouyinLoginSession | None = None

    async def start(self) -> dict[str, Any]:
        existing = self.session
        if existing and self._alive() and existing.state == "waiting":
            return self._describe()
        if not self._terminate_browser():
            # 旧会话临时数据没清掉时绝不叠加新会话：避免凭据残留继续扩大
            return {
                "ok": False,
                "error": "上一次登录的临时数据未能完全清理，已停止新的登录尝试",
            }
        browser = await asyncio.to_thread(find_browser)
        if not browser:
            return {"ok": False, "error": "未找到 Edge 或 Chrome，请先安装桌面浏览器"}
        port = free_cdp_port()
        if port is None:
            return {"ok": False, "error": "没有可用的调试端口，请稍后重试"}
        # 每次登录都是独立临时会话：不再复用持久 Profile，也就没有
        # 「从持久 Profile 恢复登录态」的语义。
        profile_dir = Path(
            tempfile.mkdtemp(prefix=self.PROFILE_PREFIX, dir=self.profile_root)
        )
        args = [
            browser,
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-extensions",
            "--disable-background-networking",
            "--window-size=1200,900",
            LOGIN_URL,
        ]
        # 先建立 process=None 的会话占位：启动失败且清理也失败时，
        # 归属保留在管理器里，下一次 start 可以重试清理而不是丢路径
        self.session = DouyinLoginSession(
            browser_path=browser,
            profile_dir=profile_dir,
            cdp_port=port,
            started_at=time.time(),
            process=None,
        )
        try:
            process = subprocess.Popen(args)
        except OSError as exc:
            cleaned = self._cleanup_profile(profile_dir)
            error = f"启动浏览器失败：{exc}"
            if cleaned:
                self.session = None
            else:
                self.session.state = "failed"
                self.session.message = "启动浏览器失败；临时数据未能完全清理，将在下次操作时重试"
                error += "；临时数据未能完全清理"
            return {"ok": False, "error": error}
        self.session.process = process
        return self._describe()

    @staticmethod
    def _looks_authenticated(cookies: dict[str, str]) -> bool:
        return bool(cookies.get("sessionid") or cookies.get("sid_guard"))

    def _alive(self) -> bool:
        return bool(self.session and self.session.process and self.session.process.poll() is None)

    def _terminate_browser(self) -> bool:
        session = self.session
        cleaned = True
        if session and self._alive():
            try:
                session.process.terminate()
            except OSError:
                pass
        if session:
            cleaned = self._terminate_session(session)
            if cleaned:
                self.session = None
            else:
                # 清理失败必须保留归属：留下可重试清理的 session/profile 引用，
                # 否则下一次 start 会绕过残留 Profile 继续创建
                session.state = "failed"
                session.message = "登录会话已结束；临时数据未能完全清理，将在下次操作时重试"
        return cleaned

    def _terminate_session(self, session: DouyinLoginSession) -> bool:
        """统一的终止/清理安全路径：定向杀进程 + 删除已验证的临时 Profile。

        成功、取消、超时、异常退出、新会话替换都必须走这里；只有启动失败
        （进程从未拉起）才允许只删目录。返回 Profile 是否清理干净。
        """
        self._kill_profile_browsers(session.profile_dir)
        return self._cleanup_profile(session.profile_dir)

    def _cleanup_profile(self, profile_dir: Path) -> bool:
        """只删除本管理器创建的临时 Profile 目录。

        双重校验：resolve 后的父目录必须正好等于 profile_root，且目录名
        必须带专用前缀；符号链接逃逸、普通目录、配置根本身一律拒绝。
        返回是否清理干净：删除失败绝不静默宣称完成。
        """
        try:
            root = self.profile_root.resolve()
            target = Path(profile_dir).resolve()
        except OSError:
            return False
        if target.parent != root or not target.name.startswith(self.PROFILE_PREFIX):
            return False
        if not target.exists():
            return True
        for attempt in range(3):
            try:
                shutil.rmtree(target)
                return True
            except OSError:
                # 浏览器句柄释放有延迟：先定向 kill（调用方），此处短暂重试
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
        return not target.exists()

    @staticmethod
    def _kill_profile_browsers(profile_dir: Path) -> None:
        if os.name == "nt":
            # 字面量匹配：Windows 路径里合法的 [ ] 在 -like 下是通配模式，
            # 必须用 .Contains()；CommandLine 可能为 null，先判非空
            marker = str(profile_dir).replace("'", "''").lower()
            script = (
                "Get-CimInstance Win32_Process | "
                "Where-Object { ($_.Name -eq 'msedge.exe' -or $_.Name -eq 'chrome.exe') "
                "-and $_.CommandLine -and $_.CommandLine.ToLower().Contains("
                f"'{marker}') }} | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            )
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=15)
            except Exception:
                pass
            return
        try:
            result = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=10)
        except Exception:
            return
        marker = str(profile_dir)
        for line in result.stdout.splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2 and marker in parts[1] and ("Chrome" in parts[1] or "Edge" in parts[1]):
                try:
                    os.kill(int(parts[0]), 9)
                except (OSError, ValueError):
                    pass

    def _describe(self) -> dict[str, Any]:
        session = self.session
        if not session:
            return {"ok": False, "state": "idle", "cookies": None, "message": "无进行中的抖音登录会话"}
        return {
            "ok": True,
            "state": session.state,
            "cookies": session.cookies,
            "message": session.message,
            "browser": os.path.basename(session.browser_path),
        }

    async def status(self) -> dict[str, Any]:
        session = self.session
        if not session:
            return self._describe()
        if session.cookies:
            return self._describe()
        if not self._alive():
            session.state = "failed"
            session.message = "抖音浏览器窗口已被关闭"
            if not self._terminate_session(session):
                session.message = "抖音浏览器窗口已被关闭；临时数据未能完全清理"
            return self._describe()
        if time.time() - session.started_at > SESSION_TTL_SECONDS:
            cleaned = self._terminate_browser()
            message = "浏览器验证超时"
            if not cleaned:
                message += "；临时数据未能完全清理"
            return {"ok": False, "state": "timeout", "cookies": None, "message": message}
        try:
            cookies = await asyncio.wait_for(self._fetch_cookies(), timeout=5)
        except asyncio.TimeoutError:
            return self._describe()
        if cookies and self._looks_authenticated(cookies):
            session.cookies = cookies
            session.state = "ready"
            session.message = "抖音登录成功，凭据仅保留在本次任务内存中"
            # 绑定当时的会话对象：即使调用方随后立即 start 新会话，
            # 后台清理也只作用于这个旧会话
            asyncio.create_task(self._cancel_session(session))
        return self._describe()

    async def _fetch_cookies(self) -> dict[str, str]:
        session = self.session
        if not session:
            return {}
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{session.cdp_port}/json/version", timeout=2) as response:
                version = json.loads(response.read().decode("utf-8"))
        except Exception:
            return {}
        try:
            async with websockets.connect(version["webSocketDebuggerUrl"]) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
                while True:
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=4))
                    if message.get("id") == 1:
                        cookies = (message.get("result") or {}).get("cookies", [])
                        break
        except Exception:
            return {}
        wanted: dict[str, str] = {}
        for cookie in cookies:
            domain = str(cookie.get("domain") or "")
            name = str(cookie.get("name") or "")
            if ("douyin.com" in domain or "iesdouyin.com" in domain) and name in COOKIE_NAMES:
                wanted[name] = str(cookie.get("value") or "")
        return wanted

    async def cancel(self) -> dict[str, Any]:
        session = self.session
        if not session:
            return {"ok": True, "message": "无进行中的抖音登录会话"}
        return await self._cancel_session(session)

    async def _cancel_session(self, session: DouyinLoginSession) -> dict[str, Any]:
        """关闭并清理指定会话对象；后台自动清理也走这里。

        所有动作只作用于传入的 session：status() 成功路径调度的后台任务
        绑定的是当时的会话，即使之后已 start 新会话，也绝不会误杀或误删
        新会话的进程与 Profile。只有它仍是管理器当前会话时才改当前引用。
        """
        process = session.process
        if process and process.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{session.cdp_port}/json/version", timeout=2) as response:
                    version = json.loads(response.read().decode("utf-8"))
                async with websockets.connect(version["webSocketDebuggerUrl"]) as ws:
                    await ws.send(json.dumps({"id": 1, "method": "Browser.close"}))
                    await asyncio.sleep(0.3)
            except Exception:
                pass
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        cleaned = self._terminate_session(session)
        if not cleaned:
            # 后台自动 cancel 的返回值无人接收：警告必须落到 session，
            # 否则后续 status() 会误报「登录成功」而无任何清理失败提示
            session.message = f"{session.message}；临时数据未能完全清理"
        if self.session is session and not session.cookies and cleaned:
            self.session = None
        message = "抖音登录会话已结束"
        if not cleaned:
            message += "；临时数据未能完全清理"
        return {"ok": True, "message": message}
