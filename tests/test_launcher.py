import json
from pathlib import Path

import launcher


def test_version_tuple_accepts_release_tags() -> None:
    assert launcher.version_tuple("v1.1.4") == (1, 1, 4)
    assert launcher.version_tuple("1.2.0-rc1") == (1, 2, 0)
    assert launcher.version_tuple("invalid") == (0,)


def test_server_alive_requires_matching_version(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status":"ok","service":"VideoToNo","mode":"portable","version":"1.1.7"}'

    monkeypatch.setattr(launcher.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    assert launcher.server_alive("http://127.0.0.1:8000", mode="portable", version="1.1.7")
    assert not launcher.server_alive("http://127.0.0.1:8000", mode="portable", version="1.1.8")


def test_configure_runtime_dirs_creates_custom_workspace(monkeypatch, tmp_path) -> None:
    """环境变量指定的 workdir 不存在时也要自动创建（打包版写日志前依赖此目录）。"""
    custom = tmp_path / "custom-ws"
    assert not custom.exists()
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", str(custom))
    monkeypatch.setattr(launcher, "is_frozen", lambda: False)
    launcher.configure_runtime_dirs()
    assert custom.is_dir()


def test_latest_release_info_reads_tag_and_url(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"tag_name": "v1.2.0", "html_url": "https://github.com/example/release"}
            ).encode("utf-8")

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(launcher.urllib.request, "urlopen", fake_urlopen)
    assert launcher.latest_release_info() == {
        "tag_name": "v1.2.0",
        "html_url": "https://github.com/example/release",
    }
    assert captured == {"url": launcher.GITHUB_LATEST_RELEASE_API, "timeout": 5}


def test_check_for_updates_opens_new_release_after_confirmation(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        launcher,
        "latest_release_info",
        lambda: {"tag_name": "v9.9.9", "html_url": "https://github.com/example/release"},
    )
    monkeypatch.setattr(launcher, "show_update_message", lambda *args, **kwargs: 6)
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)

    launcher.check_for_updates()

    assert opened == ["https://github.com/example/release"]


def test_run_asr_child_configures_dirs_then_calls_child(monkeypatch) -> None:
    import backend.asr_process as asr_process

    calls: list[str] = []
    monkeypatch.setattr(launcher, "configure_runtime_dirs", lambda: calls.append("dirs"))
    monkeypatch.setattr(asr_process, "child_main", lambda: calls.append("child") or 0)

    assert launcher.run_asr_child() == 0
    assert calls == ["dirs", "child"]


def test_main_dispatches_exact_asr_child_argv(monkeypatch) -> None:
    monkeypatch.setattr(launcher.sys, "argv", ["app", "--asr-child"])
    calls: list[str] = []
    monkeypatch.setattr(launcher, "run_asr_child", lambda: calls.append("child") or 7)

    def boom(*_args, **_kwargs):
        raise AssertionError("worker must not probe ports")

    monkeypatch.setattr(launcher, "find_available_port", boom)
    assert launcher.main() == 7
    assert calls == ["child"]


def test_main_does_not_dispatch_mixed_argv(monkeypatch) -> None:
    monkeypatch.setattr(launcher.sys, "argv", ["app", "--asr-child", "extra"])
    monkeypatch.setattr(launcher, "configure_runtime_dirs", lambda: None)
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", ".")
    calls: list[str] = []
    monkeypatch.setattr(launcher, "run_asr_child", lambda: calls.append("child") or 0)

    def no_port():
        raise RuntimeError("no port")

    monkeypatch.setattr(launcher, "find_available_port", no_port)
    monkeypatch.setattr(launcher, "show_error", lambda *_a, **_k: None)

    assert launcher.main() == 1
    assert calls == []


def test_main_keeps_normal_flow_without_child_flag(monkeypatch) -> None:
    monkeypatch.setattr(launcher.sys, "argv", ["app"])
    monkeypatch.setattr(launcher, "configure_runtime_dirs", lambda: None)
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", ".")
    monkeypatch.setattr(launcher, "find_available_port", lambda: 1234)
    monkeypatch.setattr(launcher, "server_alive", lambda *_a, **_k: True)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda _url: None)
    monkeypatch.setenv("VIDEOTONOTES_NO_BROWSER", "1")
    calls: list[str] = []
    monkeypatch.setattr(launcher, "run_asr_child", lambda: calls.append("child") or 0)

    assert launcher.main() == 0
    assert calls == []
