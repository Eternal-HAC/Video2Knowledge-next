"""DouyinLoginManager 临时 Profile 生命周期的纯 mock 合同测试。

不启动真实浏览器、不联网、不读取真实 cookie；磁盘操作只发生在 tmp_path。
"""
from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path

import pytest

from backend import douyin_login
from backend.douyin_login import DouyinLoginManager


class FakeProcess:
    """可控的假浏览器进程：poll() 返回 None 表示存活。"""

    def __init__(self, args, **_kwargs):
        self.args = list(args)
        self._alive = True
        self.terminated = False

    def poll(self):
        return None if self._alive else 1

    def terminate(self):
        self.terminated = True
        self._alive = False

    def kill(self):
        self._alive = False


@pytest.fixture
def manager_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """装配一个完全 mock 的 DouyinLoginManager；profile_root 指向 tmp_path。"""
    created: list[FakeProcess] = []
    killed_markers: list[str] = []

    monkeypatch.setattr(douyin_login, "find_browser", lambda: "fake-browser.exe")
    monkeypatch.setattr(douyin_login, "free_cdp_port", lambda: 9343)

    def fake_popen(args, **kwargs):
        process = FakeProcess(args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(douyin_login.subprocess, "Popen", fake_popen)

    def spy_kill(profile_dir: Path) -> None:
        killed_markers.append(str(profile_dir))
        # 不执行真实进程枚举：本 fixture 下没有真实浏览器

    monkeypatch.setattr(DouyinLoginManager, "_kill_profile_browsers", staticmethod(spy_kill))

    manager = DouyinLoginManager(tmp_path)
    return manager, created, killed_markers, monkeypatch


def _fake_cookies(manager: DouyinLoginManager, monkeypatch: pytest.MonkeyPatch, value):
    async def fetch():
        return value

    monkeypatch.setattr(manager, "_fetch_cookies", fetch)


def test_each_start_uses_unique_owned_temp_profile(manager_env) -> None:
    manager, created, _, _ = manager_env
    asyncio.run(manager.start())
    first_dir = manager.session.profile_dir
    created[0]._alive = False  # 旧会话结束后才允许新会话替换
    asyncio.run(manager.start())
    second_dir = manager.session.profile_dir
    assert first_dir != second_dir
    for directory in (first_dir, second_dir):
        assert directory.name.startswith(DouyinLoginManager.PROFILE_PREFIX)
        assert directory.parent == manager.profile_root


def test_new_session_cleans_previous_profile(manager_env) -> None:
    manager, created, _, _ = manager_env
    asyncio.run(manager.start())
    first_dir = manager.session.profile_dir
    (first_dir / "dummy").write_text("x", encoding="utf-8")
    created[0]._alive = False  # 旧浏览器已退出，新会话应接管并清理旧 Profile
    asyncio.run(manager.start())
    assert not first_dir.exists(), "旧会话 Profile 必须在新会话启动前删除"


def test_success_keeps_memory_cookies_but_removes_profile(manager_env) -> None:
    """成功路径必须在同一事件循环内完成自动清理：profile 消失、内存 cookie 保留。"""
    manager, created, killed, monkeypatch = manager_env
    _fake_cookies(manager, monkeypatch, {"sessionid": "secret", "ttwid": "x"})

    async def scenario() -> None:
        await manager.start()
        profile_dir = manager.session.profile_dir
        status = await manager.status()
        assert status["state"] == "ready"
        # status() 内部异步调度的 cancel 必须自动完成，无需手工 cancel
        for _ in range(100):
            if not profile_dir.exists():
                break
            await asyncio.sleep(0.02)
        assert not profile_dir.exists(), "自动清理未删除临时 Profile"
        assert created[0].terminated, "自动清理未关闭浏览器进程"
        follow_up = await manager.status()
        assert follow_up["state"] == "ready"
        assert follow_up["cookies"] == {"sessionid": "secret", "ttwid": "x"}
        assert not list(manager.profile_root.iterdir()), "磁盘上不得残留任何登录 Profile"

    asyncio.run(scenario())


def test_cancel_removes_profile(manager_env) -> None:
    manager, _, _, _ = manager_env
    asyncio.run(manager.start())
    profile_dir = manager.session.profile_dir
    asyncio.run(manager.cancel())
    assert not profile_dir.exists()


def test_timeout_removes_profile(manager_env, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, _, _, _ = manager_env
    asyncio.run(manager.start())
    profile_dir = manager.session.profile_dir
    manager.session.started_at -= douyin_login.SESSION_TTL_SECONDS + 10
    status = asyncio.run(manager.status())
    assert status["state"] == "timeout"
    assert not profile_dir.exists()


def test_browser_exit_marks_failed_and_removes_profile(manager_env) -> None:
    manager, created, _, _ = manager_env
    asyncio.run(manager.start())
    profile_dir = manager.session.profile_dir
    created[0]._alive = False  # 浏览器异常退出
    status = asyncio.run(manager.status())
    assert status["state"] == "failed"
    assert not profile_dir.exists()


def test_launch_failure_removes_profile(manager_env, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, _, _, _ = manager_env

    def boom(*_args, **_kwargs):
        raise OSError("cannot launch")

    monkeypatch.setattr(douyin_login.subprocess, "Popen", boom)
    result = asyncio.run(manager.start())
    assert result["ok"] is False
    assert manager.session is None
    assert not list(manager.profile_root.iterdir())


def test_cleanup_refuses_foreign_paths(manager_env, tmp_path: Path) -> None:
    manager, _, _, _ = manager_env
    outside = tmp_path.parent / f"{DouyinLoginManager.PROFILE_PREFIX}escape"
    outside.mkdir()
    wrong_prefix = manager.profile_root / "daily-edge-profile"
    wrong_prefix.mkdir()
    for target in (outside, wrong_prefix, manager.profile_root):
        assert manager._cleanup_profile(target) is False, f"清理函数必须拒绝 {target}"
        assert target.exists(), f"清理函数不得删除 {target}"


def test_kill_marker_is_exact_profile_path(manager_env) -> None:
    """只杀命令行明确引用本次 Profile 的进程：marker 必须是该目录的精确路径。"""
    manager, created, killed, _ = manager_env
    asyncio.run(manager.start())
    profile_dir = manager.session.profile_dir
    killed.clear()  # 只观察 cancel 自己的行为
    asyncio.run(manager.cancel())
    assert killed == [str(profile_dir)], "取消必须恰好定向清理一次本次 Profile"


def test_abnormal_exit_kills_once_with_exact_marker(manager_env) -> None:
    """异常退出分支同样走统一定向终止：恰好一次、marker 精确。"""
    manager, created, killed, _ = manager_env
    asyncio.run(manager.start())
    profile_dir = manager.session.profile_dir
    killed.clear()
    created[0]._alive = False
    asyncio.run(manager.status())
    assert killed == [str(profile_dir)], "异常退出必须恰好定向清理一次本次 Profile"


def test_cleanup_failure_is_observable(manager_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """rmtree 失败不得无声宣称清理完成：信号可观察且不含路径/cookie。"""
    manager, _, _, _ = manager_env
    asyncio.run(manager.start())
    profile_dir = manager.session.profile_dir

    def boom(*_args, **_kwargs):
        raise OSError("file locked")

    monkeypatch.setattr(douyin_login.shutil, "rmtree", boom)
    monkeypatch.setattr(douyin_login.time, "sleep", lambda *_a, **_k: None)
    assert manager._cleanup_profile(profile_dir) is False
    result = asyncio.run(manager.cancel())
    assert "未能完全清理" in result["message"]
    assert str(profile_dir) not in result["message"]
    assert profile_dir.exists(), "删除失败时目录当然仍在，但不能被误报为已清理"
    status = asyncio.run(manager.status())
    assert "未能完全清理" in status["message"], "后续 status 也必须可见清理失败"


def test_auto_cancel_cleanup_failure_visible_in_status(manager_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """生产成功路径是 status() 后台调度的 cancel：其清理失败必须在 status 可见。"""
    manager, _, _, monkeypatch_env = manager_env
    _fake_cookies(manager, monkeypatch_env, {"sessionid": "secret"})

    def boom(*_args, **_kwargs):
        raise OSError("file locked")

    async def scenario() -> None:
        await manager.start()
        profile_dir = manager.session.profile_dir
        monkeypatch_env.setattr(douyin_login.shutil, "rmtree", boom)
        monkeypatch_env.setattr(douyin_login.time, "sleep", lambda *_a, **_k: None)
        status = await manager.status()
        assert status["state"] == "ready"
        for _ in range(100):
            if "未能完全清理" in (manager.session.message if manager.session else ""):
                break
            await asyncio.sleep(0.02)
        follow_up = await manager.status()
        assert follow_up["state"] == "ready"
        assert follow_up["cookies"] == {"sessionid": "secret"}
        assert "未能完全清理" in follow_up["message"], "后台 cancel 清理失败不得误报成功"
        assert str(profile_dir) not in follow_up["message"]

    asyncio.run(scenario())


def test_start_refuses_new_session_when_old_cleanup_fails(
    manager_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """旧会话清理失败时停止启动新会话：不创建第二个 Profile/进程。"""
    manager, created, _, _ = manager_env
    asyncio.run(manager.start())
    created[0]._alive = False  # 旧浏览器已退出，下一次 start 会走替换路径

    def boom(*_args, **_kwargs):
        raise OSError("file locked")

    monkeypatch.setattr(douyin_login.shutil, "rmtree", boom)
    monkeypatch.setattr(douyin_login.time, "sleep", lambda *_a, **_k: None)
    result = asyncio.run(manager.start())
    assert result["ok"] is False
    assert "未能完全清理" in result["error"]
    assert len(created) == 1, "清理失败时不得再拉起新的浏览器进程"


def test_launch_failure_with_cleanup_failure_warns(
    manager_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, _, _, _ = manager_env

    def boom_popen(*_args, **_kwargs):
        raise OSError("cannot launch")

    def boom_rmtree(*_args, **_kwargs):
        raise OSError("file locked")

    monkeypatch.setattr(douyin_login.subprocess, "Popen", boom_popen)
    monkeypatch.setattr(douyin_login.shutil, "rmtree", boom_rmtree)
    monkeypatch.setattr(douyin_login.time, "sleep", lambda *_a, **_k: None)
    result = asyncio.run(manager.start())
    assert result["ok"] is False
    assert "启动浏览器失败" in result["error"]
    assert "未能完全清理" in result["error"]
    assert str(manager.profile_root) not in result["error"]


def test_no_persistent_profile_recovery_semantics() -> None:
    """持久 Profile 恢复语义已移除：不再使用固定 _douyin_profile 目录。"""
    source = Path(douyin_login.__file__).read_text(encoding="utf-8")
    assert "_douyin_profile" not in source
    assert "恢复抖音登录态" not in source


def test_kill_profile_browsers_uses_literal_contains(monkeypatch: pytest.MonkeyPatch) -> None:
    """进程清理脚本必须字面量匹配 Profile 路径：不含 -like，含 .Contains 与字面路径。"""
    captured: list[dict] = []

    def fake_run(*args, **kwargs):
        captured.append({"args": args, "kwargs": kwargs})

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(douyin_login.subprocess, "run", fake_run)
    # 不依赖宿主平台：显式让 Windows 分支生效（monkeypatch 结束后自动还原）
    monkeypatch.setattr(douyin_login.os, "name", "nt")
    # 含 [ ] 的合法 Windows 路径：-like 时代会被当作通配模式
    DouyinLoginManager._kill_profile_browsers(
        Path("C:" + "\\" + "tmp" + "\\" + "v2k-douyin-profile-ab[1]")
    )
    assert len(captured) == 1
    argv = captured[0]["args"][0]
    assert argv[0] == "powershell"
    script = argv[-1]
    assert "-like" not in script
    assert ".Contains(" in script
    assert "v2k-douyin-profile-ab[1]" in script
    assert "$_.CommandLine -and" in script, "CommandLine 为 null 时必须先判非空"


def test_blocked_start_keeps_ownership_and_recovers(manager_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """清理失败被拦截后归属不丢：两次拦截 Popen 仍 1 次；恢复后可先清旧目录再创新会话。"""
    manager, created, _, _ = manager_env
    asyncio.run(manager.start())
    old_dir = manager.session.profile_dir
    created[0]._alive = False

    failing = {"on": True}
    real_rmtree = douyin_login.shutil.rmtree

    def flaky(target, *args, **kwargs):
        if failing["on"]:
            raise OSError("file locked")
        return real_rmtree(target, *args, **kwargs)

    monkeypatch.setattr(douyin_login.shutil, "rmtree", flaky)
    monkeypatch.setattr(douyin_login.time, "sleep", lambda *_a, **_k: None)

    first = asyncio.run(manager.start())
    assert first["ok"] is False and "未能完全清理" in first["error"]
    second = asyncio.run(manager.start())
    assert second["ok"] is False
    assert len(created) == 1, "连续拦截期间不得再拉起浏览器进程"
    assert manager.session is not None, "清理失败必须保留可重试的归属引用"

    failing["on"] = False
    third = asyncio.run(manager.start())
    assert third["ok"] is True
    assert len(created) == 2
    assert not old_dir.exists(), "恢复后再次 start 必须先清掉旧目录"
    assert manager.session.profile_dir != old_dir


def test_launch_failure_keeps_profile_reference_for_retry(
    manager_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """启动失败+清理失败后归属保留：下一次 start 能重试清理旧目录。"""
    manager, created, _, _ = manager_env
    failing = {"on": True}
    real_rmtree = douyin_login.shutil.rmtree

    def flaky(target, *args, **kwargs):
        if failing["on"]:
            raise OSError("file locked")
        return real_rmtree(target, *args, **kwargs)

    def flaky_popen(args, **kwargs):
        if failing["on"]:
            raise OSError("cannot launch")
        process = FakeProcess(args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(douyin_login.subprocess, "Popen", flaky_popen)
    monkeypatch.setattr(douyin_login.shutil, "rmtree", flaky)
    monkeypatch.setattr(douyin_login.time, "sleep", lambda *_a, **_k: None)
    result = asyncio.run(manager.start())
    assert result["ok"] is False
    stuck = manager.session
    assert stuck is not None and stuck.state == "failed"
    stuck_dir = stuck.profile_dir
    assert stuck_dir.exists()

    failing["on"] = False
    retry = asyncio.run(manager.start())
    assert retry["ok"] is True
    assert not stuck_dir.exists(), "重试 start 必须先清掉上次失败的旧目录"
    assert manager.session.profile_dir != stuck_dir


def test_background_cancel_never_touches_new_session(manager_env, monkeypatch: pytest.MonkeyPatch) -> None:
    """竞态：ready 后立即 start 新会话，旧后台清理绝不能动新会话。"""
    manager, created, killed, monkeypatch_env = manager_env
    _fake_cookies(manager, monkeypatch_env, {"sessionid": "secret"})

    async def scenario() -> None:
        await manager.start()
        old_dir = manager.session.profile_dir
        status = await manager.status()
        assert status["state"] == "ready"
        # 后台 _cancel_session(旧) 已调度；立刻 start 新会话（旧浏览器标记退出走替换路径）
        created[0]._alive = False
        await manager.start()
        new_dir = manager.session.profile_dir
        new_process = created[1]
        for _ in range(100):
            await asyncio.sleep(0.02)
            if not old_dir.exists():
                break
        assert new_dir.exists(), "后台清理不得删除新会话 Profile"
        assert not new_process.terminated, "后台清理不得 terminate 新会话进程"
        assert manager.session.profile_dir == new_dir
        assert all(marker != str(new_dir) for marker in killed)

    asyncio.run(scenario())


def test_no_proxy_opener_ignores_system_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """系统代理被投毒时，CDP opener 仍不得携带任何非空代理配置。

    空 ProxyHandler({}) 的作用是挤掉 build_opener 默认装配的系统代理
    ProxyHandler；在 Python 3.13 上它因不注册协议方法而不会留在
    opener.handlers 里，因此正确断言是「不存在非空 proxies 的 ProxyHandler」。
    """
    monkeypatch.setattr(
        urllib.request, "getproxies", lambda: {"http": "http://10.0.0.1:9", "https": "http://10.0.0.1:9"}
    )
    opener = douyin_login._no_proxy_opener()
    proxy_handlers = [h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert all(h.proxies == {} for h in proxy_handlers), "opener 不得携带任何系统代理配置"


def test_free_cdp_port_returns_none_when_winsock_broken(monkeypatch: pytest.MonkeyPatch) -> None:
    """socket 创建本身抛 OSError（Winsock 拖垮）时返回 None，不得向上抛裸 500。"""

    def broken_socket(*_args, **_kwargs):
        raise OSError("Winsock unavailable")

    monkeypatch.setattr(douyin_login.socket, "socket", broken_socket)
    assert douyin_login.free_cdp_port() is None


def test_fetch_cookies_uses_no_proxy_opener_and_ws_proxy_disabled(
    manager_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """行为级确认：/json/version 走模块级无代理 opener，WebSocket 显式 proxy=None。"""
    manager, created, _, _ = manager_env
    asyncio.run(manager.start())
    assert created, "fixture 必须产生一个假浏览器进程"

    opener_calls: list[str] = []

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps({"webSocketDebuggerUrl": "ws://127.0.0.1:9343/devtools"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    class FakeOpener:
        def open(self, url: str, timeout: float = 0):
            opener_calls.append(url)
            return FakeResponse()

    ws_kwargs: list[dict] = []

    class FakeWS:
        async def send(self, _data: str) -> None:
            return None

        async def recv(self) -> str:
            return json.dumps(
                {
                    "id": 1,
                    "result": {
                        "cookies": [
                            {"domain": ".douyin.com", "name": "sessionid", "value": "x"},
                            {"domain": ".example.com", "name": "ignored", "value": "y"},
                        ]
                    },
                }
            )

    class FakeConnect:
        def __init__(self, _url: str, **kwargs):
            ws_kwargs.append(kwargs)

        async def __aenter__(self):
            return FakeWS()

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(douyin_login, "_CDP_OPENER", FakeOpener())
    monkeypatch.setattr(douyin_login.websockets, "connect", FakeConnect)

    cookies = asyncio.run(manager._fetch_cookies())

    assert cookies == {"sessionid": "x"}, "只应保留 douyin 域内的允许字段"
    assert opener_calls and "127.0.0.1:9343" in opener_calls[0]
    assert ws_kwargs and ws_kwargs[0].get("proxy") is None, "WebSocket 必须显式 proxy=None"
