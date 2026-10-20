"""Agent Skill 脚本的凭据处理测试。

`skills/video-to-note/scripts/video_note.py` 不在包里（没有可导入的包路径），
所以用 importlib 按文件加载——这个脚本是发给用户机器跑的，Key 的来路和出口
必须钉住：命令行明文要能换成环境变量/stdin，任何回显凭据的文本都要先脱敏。
"""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "video-to-note"
    / "scripts"
    / "video_note.py"
)
spec = importlib.util.spec_from_file_location("video_note_skill", SCRIPT)
assert spec and spec.loader
video_note = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video_note)


def test_skill_redacts_every_credential_shape() -> None:
    plain = "Vh7NqzL0mBxc8dke"
    video_note.remember_secret(plain)
    out = video_note.redact(
        'HTTP 401 upstream echoed {"api_key": "sk-abcdef12345", '
        '"authorization": Bearer Q29uZ3JldGVzczEyMzQ1Ng, "note": "' + plain + '"}'
    )
    assert "sk-abcdef12345" not in out
    assert "Q29uZ3JldGVzczEyMzQ1Ng" not in out
    assert plain not in out
    assert plain[:4] + "****" in out
    # 不能顺手把模型文件名单咬坏
    assert "tokenizer.json" in video_note.redact("missing tokenizer.json in snapshot")


def test_skill_reads_key_from_stdin_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    env_name = video_note.API_KEY_ENV
    monkeypatch.delenv(video_note.LEGACY_API_KEY_ENV, raising=False)
    monkeypatch.setenv(env_name, "envkey-9f8e7d6c")
    from_argv = SimpleNamespace(api_key="argvkey-1a2b3c4d")
    from_env = SimpleNamespace(api_key="")
    from_stdin = SimpleNamespace(api_key="-")

    monkeypatch.setattr(video_note.sys, "stdin", io.StringIO("  piped-key-1a2b3c4d \n"))
    assert video_note.resolve_api_key(from_stdin) == "piped-key-1a2b3c4d"
    assert video_note.resolve_api_key(from_env) == "envkey-9f8e7d6c"
    assert video_note.resolve_api_key(from_argv) == "argvkey-1a2b3c4d"
    monkeypatch.delenv(env_name)
    assert video_note.resolve_api_key(from_env) == ""


def test_skill_env_alias_prefers_new_name_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    assert video_note.API_KEY_ENV == "VIDEO2KNOWLEDGE_LLM_API_KEY"
    assert video_note.LEGACY_API_KEY_ENV == "VIDEOTONOTES_LLM_API_KEY"
    from_env = SimpleNamespace(api_key="")
    monkeypatch.setenv("VIDEOTONOTES_LLM_API_KEY", "legacy-key-00112233")
    monkeypatch.setenv("VIDEO2KNOWLEDGE_LLM_API_KEY", "new-key-44556677")
    assert video_note.resolve_api_key(from_env) == "new-key-44556677"
    monkeypatch.delenv("VIDEO2KNOWLEDGE_LLM_API_KEY")
    assert video_note.resolve_api_key(from_env) == "legacy-key-00112233"


def test_skill_discovery_accepts_new_product_and_legacy_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def __init__(self, payload: bytes):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.payload

    def fake_urlopen_factory(payload: bytes):
        def fake_urlopen(url, timeout):
            port = int(str(url).rsplit(":", 1)[1].split("/")[0])
            if port == 8002:
                return FakeResponse(payload)
            raise OSError("refused")

        return fake_urlopen

    monkeypatch.setattr(
        video_note.urllib.request,
        "urlopen",
        fake_urlopen_factory(b'{"status":"ok","product":"Video2Knowledge"}'),
    )
    assert video_note.find_service() == "http://127.0.0.1:8002"

    monkeypatch.setattr(
        video_note.urllib.request,
        "urlopen",
        fake_urlopen_factory(b'{"status":"ok","service":"VideoToNo"}'),
    )
    assert video_note.find_service() == "http://127.0.0.1:8002"
