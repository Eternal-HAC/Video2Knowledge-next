import json
import os
import re
from pathlib import Path

import launcher
import product_info


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_version_metadata_has_single_canonical_source() -> None:
    assert product_info.PRODUCT_NAME == "Video2Knowledge"
    assert product_info.LEGACY_SERVICE_ID == "VideoToNo"
    assert product_info.VERSION == "1.0.0-beta.4"
    assert product_info.GITHUB_REPO == "Eternal-HAC/Video2Knowledge-next"
    assert launcher.VERSION == product_info.VERSION
    assert launcher.APP_NAME == f"Video2Knowledge v{product_info.VERSION}"


def test_version_key_orders_transition_line_below_independent_line() -> None:
    """过渡线（v1.4.2-v2k.N）数字再大也低于独立线的第一个 beta。"""
    assert launcher.version_tuple("v1.4.2-v2k.9") < launcher.version_tuple("1.0.0-beta.1")
    assert launcher.version_tuple("v1.4.2-v2k.2") > launcher.version_tuple("v1.4.2-v2k.1")


def test_version_key_orders_beta_rc_stable_and_numbers() -> None:
    assert launcher.version_tuple("1.0.0-beta.2") < launcher.version_tuple("1.0.0-beta.3")
    assert launcher.version_tuple("v1.0.0-beta.9") < launcher.version_tuple("1.0.0-rc.1")
    assert launcher.version_tuple("1.0.0-rc.1") < launcher.version_tuple("v1.0.0")
    assert launcher.version_tuple("v1.9.0") < launcher.version_tuple("1.10.0")
    assert launcher.version_tuple("1.0.0") < launcher.version_tuple("1.0.1")


def test_invalid_versions_never_count_as_updates() -> None:
    invalid = launcher.version_tuple("not-a-version")
    assert invalid == product_info.INVALID_VERSION_KEY
    assert launcher.version_tuple("") == invalid
    # 无法识别的远端 tag 不会触发更新提示；过渡线版本对当前 beta 也不算更新
    assert not product_info.is_update("garbage", product_info.VERSION)
    assert not product_info.is_update("v1.4.2-v2k.9", product_info.VERSION)
    assert product_info.is_update("v1.0.0-beta.3", "1.0.0-beta.2")
    assert product_info.is_update("v1.0.0-rc.1", "1.0.0-beta.9")
    assert not product_info.is_update("1.0.0-beta.1", "1.0.0")


def test_server_alive_accepts_new_product_and_legacy_service(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        def __init__(self, payload: bytes):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.payload

    responses = iter(
        [
            b'{"status":"ok","product":"Video2Knowledge","mode":"portable","version":"1.0.0-beta.1"}',
            b'{"status":"ok","service":"VideoToNo","mode":"portable","version":"1.0.0-beta.1"}',
            b'{"status":"ok","service":"SomethingElse","mode":"portable","version":"1.0.0-beta.1"}',
        ]
    )
    monkeypatch.setattr(
        launcher.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(next(responses)),
    )

    assert launcher.server_alive("http://127.0.0.1:8000", mode="portable", version="1.0.0-beta.1")
    assert launcher.server_alive("http://127.0.0.1:8000", mode="portable", version="1.0.0-beta.1")
    assert not launcher.server_alive("http://127.0.0.1:8000", mode="portable", version="1.0.0-beta.1")


def test_env_alias_prefers_new_name_and_keeps_legacy(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", "legacy-dir")
    monkeypatch.setenv("VIDEO2KNOWLEDGE_WORKSPACE", "new-dir")
    assert product_info.env_value("WORKSPACE") == "new-dir"
    monkeypatch.delenv("VIDEO2KNOWLEDGE_WORKSPACE")
    assert product_info.env_value("WORKSPACE") == "legacy-dir"
    monkeypatch.delenv("VIDEOTONOTES_WORKSPACE")
    assert product_info.env_value("WORKSPACE") is None
    assert product_info.env_value("WORKSPACE", "fallback") == "fallback"


def test_env_value_empty_new_name_still_wins_over_legacy(monkeypatch) -> None:
    """优先级按"是否设置"而非"是否非空"：新名显式设成空串也要赢过旧名，
    空值怎么处理是调用方的事（configure_runtime_dirs 会退回默认目录）。"""
    monkeypatch.setenv("VIDEO2KNOWLEDGE_WORKSPACE", "")
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", "legacy-dir")
    assert product_info.env_value("WORKSPACE") == ""
    assert product_info.env_value("WORKSPACE", "fallback") == ""
    monkeypatch.delenv("VIDEO2KNOWLEDGE_WORKSPACE")
    assert product_info.env_value("WORKSPACE") == "legacy-dir"


def test_set_env_aliases_overwrites_conflicting_legacy_value(monkeypatch) -> None:
    """两个名字冲突时必须同步到同一份解析结果，不能 setdefault 留下旧值：
    backend / ASR 子进程按新名优先读，留下的旧名会让父子进程各说各话。"""
    monkeypatch.setenv("VIDEO2KNOWLEDGE_WORKSPACE", "stale-new")
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", "stale-legacy")
    product_info.set_env_aliases("WORKSPACE", "resolved")
    assert os.environ["VIDEO2KNOWLEDGE_WORKSPACE"] == "resolved"
    assert os.environ["VIDEOTONOTES_WORKSPACE"] == "resolved"


def test_configure_runtime_dirs_empty_new_env_falls_back_and_synchronizes(
    monkeypatch, tmp_path
) -> None:
    """新名设成空串时不许拿空串当工作目录（Path('') 会落到 cwd）：
    configure 退回默认目录，并把两个名字都同步成解析结果。"""
    legacy_dir = tmp_path / "legacy-ws"
    monkeypatch.setenv("VIDEO2KNOWLEDGE_WORKSPACE", "")
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", str(legacy_dir))
    monkeypatch.setattr(launcher, "is_frozen", lambda: False)
    monkeypatch.setattr(launcher, "base_dir", lambda: tmp_path)
    launcher.configure_runtime_dirs()
    resolved = str(tmp_path / "workspace")
    assert os.environ["VIDEO2KNOWLEDGE_WORKSPACE"] == resolved
    assert os.environ["VIDEOTONOTES_WORKSPACE"] == resolved
    assert (tmp_path / "workspace").is_dir()
    assert not legacy_dir.exists()


def test_configure_runtime_dirs_honors_new_env_over_legacy(monkeypatch, tmp_path) -> None:
    new_dir = tmp_path / "new-ws"
    legacy_dir = tmp_path / "legacy-ws"
    monkeypatch.setenv("VIDEO2KNOWLEDGE_WORKSPACE", str(new_dir))
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", str(legacy_dir))
    monkeypatch.setattr(launcher, "is_frozen", lambda: False)
    launcher.configure_runtime_dirs()
    assert new_dir.is_dir()
    assert not legacy_dir.exists()
    # 两个名字都解析到新值，下游（backend / ASR 子进程）拿到同一份
    assert product_info.env_value("WORKSPACE") == str(new_dir)


def test_configure_runtime_dirs_legacy_env_still_works(monkeypatch, tmp_path) -> None:
    legacy_dir = tmp_path / "legacy-ws"
    monkeypatch.delenv("VIDEO2KNOWLEDGE_WORKSPACE", raising=False)
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", str(legacy_dir))
    monkeypatch.setattr(launcher, "is_frozen", lambda: False)
    launcher.configure_runtime_dirs()
    assert legacy_dir.is_dir()
    # 旧名生效后补写新名，整套进程读到的路径一致
    assert product_info.env_value("WORKSPACE") == str(legacy_dir)


def test_fallback_workspace_prefers_existing_legacy_dir(monkeypatch, tmp_path) -> None:
    """exe 旁不可写退回用户目录时：旧数据目录已存在就继续用它，不搬动数据。"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "VideoToNo" / "workspace"
    legacy.mkdir(parents=True)
    assert launcher._fallback_workspace() == legacy


def test_fallback_workspace_uses_branded_dir_once_it_exists(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "VideoToNo" / "workspace"
    legacy.mkdir(parents=True)
    branded = tmp_path / "Video2Knowledge" / "workspace"
    branded.mkdir(parents=True)
    assert launcher._fallback_workspace() == branded


def test_fallback_workspace_fresh_install_uses_branded_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert launcher._fallback_workspace() == tmp_path / "Video2Knowledge" / "workspace"


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
    monkeypatch.delenv("VIDEO2KNOWLEDGE_WORKSPACE", raising=False)
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
                [
                    {
                        "tag_name": "v9.9.9-draft",
                        "html_url": "https://github.com/example/draft",
                        "draft": True,
                    },
                    {
                        "tag_name": "v1.4.2-v2k.1",
                        "html_url": "https://github.com/example/release",
                        "draft": False,
                        "prerelease": True,
                    },
                ]
            ).encode("utf-8")

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(launcher.urllib.request, "urlopen", fake_urlopen)
    assert launcher.latest_release_info() == {
        "tag_name": "v1.4.2-v2k.1",
        "html_url": "https://github.com/example/release",
    }
    assert captured == {"url": launcher.GITHUB_RELEASES_API, "timeout": 5}


def test_release_api_points_to_successor_fork() -> None:
    assert launcher.GITHUB_RELEASES_API.startswith(
        "https://api.github.com/repos/Eternal-HAC/Video2Knowledge-next/releases"
    )


def test_release_version_is_synchronized_across_runtime_and_frontend() -> None:
    page = (PROJECT_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert f'id="appVersion" class="app-version">v{launcher.VERSION}</span>' in page


def test_build_script_pins_the_approved_pyinstaller_version() -> None:
    build_script = (PROJECT_ROOT / "scripts" / "build_exe.ps1").read_text(
        encoding="utf-8"
    )
    assert 'pip install --quiet "pyinstaller==6.22.3"' in build_script


def test_build_and_release_read_canonical_metadata_and_brand_outputs() -> None:
    """构建/发布不再各自抄一份版本号：统一从 product_info.py 读，产物名跟品牌走。"""
    build_script = (PROJECT_ROOT / "scripts" / "build_exe.ps1").read_text(
        encoding="utf-8"
    )
    assert 'product_info.py' in build_script
    assert '--name "$productName"' in build_script
    assert '"dist\\$productName-$version-portable.exe"' in build_script
    assert '"dist\\$productName-portable.exe"' in build_script
    assert '从 launcher.py 读取 VERSION' not in build_script

    template = (PROJECT_ROOT / "scripts" / "version_info.txt.template").read_text(
        encoding="utf-8"
    )
    assert "Video2Knowledge" in template
    assert "VideoToNo" not in template

    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert "product_info.py" in workflow
    assert "Path(\"launcher.py\")" not in workflow
    assert "dist/${{ env.PRODUCT_NAME }}-${{ env.VERSION }}-portable.exe" in workflow
    assert '--title "$PRODUCT_NAME $GITHUB_REF_NAME"' in workflow


def test_build_script_rewrites_checksum_for_the_versioned_artifact() -> None:
    build_script = (PROJECT_ROOT / "scripts" / "build_exe.ps1").read_text(
        encoding="utf-8"
    )
    assert "Get-FileHash -LiteralPath $target -Algorithm SHA256" in build_script
    assert 'Join-Path $projectRoot "dist\\SHA256SUMS.txt"' in build_script
    assert '"$hash  $artifactName`r`n"' in build_script
    assert "[System.Text.Encoding]::ASCII" in build_script


def test_beta3_portable_smoke_covers_local_history_favorites_and_source_inspection() -> None:
    smoke = (PROJECT_ROOT / "scripts" / "smoke_portable_beta3.ps1").read_text(
        encoding="utf-8"
    )
    assert "/api/note-templates" in smoke
    assert "/api/tasks?offset=0&limit=1" in smoke
    assert "/api/task/seed-note/favorite" in smoke
    assert "/api/source-inspect" in smoke
    assert "Favorite did not survive a portable restart" in smoke
    assert "Stop-SmokeProcessTree" in smoke
    assert "v2k-beta3-smoke-" in smoke


def test_version_info_keeps_numeric_file_and_full_product_version() -> None:
    """PE 规范里 filevers/FileVersion 必须是纯数字四段（1.0.0.0），
    而 ProductVersion 字符串要保留完整语义化版本（1.0.0-beta.3）——
    模板用两套占位符，构建脚本做两套替换。"""
    template = (PROJECT_ROOT / "scripts" / "version_info.txt.template").read_text(
        encoding="utf-8"
    )
    assert "filevers=(__VERSION_PARTS__)" in template
    assert "StringStruct(u'FileVersion', u'__FILE_VERSION__')" in template
    assert "StringStruct(u'ProductVersion', u'__PRODUCT_VERSION__')" in template

    build_script = (PROJECT_ROOT / "scripts" / "build_exe.ps1").read_text(
        encoding="utf-8"
    )
    assert "-replace '__FILE_VERSION__', $fileVersion" in build_script
    assert "-replace '__PRODUCT_VERSION__', $version" in build_script

    # 按 build_exe.ps1 的替换口径在 Python 侧渲染一遍，核对最终产物字段
    version = product_info.VERSION
    clean = re.sub(r"[^0-9.].*$", "", version)
    parts = ([int(p) for p in clean.split(".")] + [0, 0, 0])[:4]
    file_version = ".".join(str(p) for p in parts)
    rendered = (
        template.replace("__VERSION_PARTS__", ", ".join(str(p) for p in parts))
        .replace("__FILE_VERSION__", file_version)
        .replace("__PRODUCT_VERSION__", version)
    )
    assert "filevers=(1, 0, 0, 0)" in rendered
    assert "StringStruct(u'FileVersion', u'1.0.0.0')" in rendered
    assert "StringStruct(u'ProductVersion', u'1.0.0-beta.4')" in rendered
    assert "__" not in rendered, "模板渲染后不得残留占位符"


def test_release_workflow_pins_pyinstaller_and_publishes_prerelease() -> None:
    """tag 推送 -> 工作流构建并创建 prerelease 的全链路结构约束：
    钉住 PyInstaller 版本、给版本化 EXE 出 SHA256SUMS.txt、两个资产一起上传、
    全程只有一条 gh release create 且带 --prerelease、notes 是当前 beta 说明。"""
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert '"pyinstaller==6.22.3"' in workflow
    assert "Get-FileHash" in workflow
    assert "SHA256SUMS.txt" in workflow
    assert workflow.count("gh release create") == 1
    assert "--prerelease" in workflow
    # The exact CI artifact must be downloaded and accepted before public release.
    create = next(line for line in workflow.splitlines() if line.strip().startswith('gh release create'))
    assert '--draft' in create and '--prerelease' in create
    assert 'gh release edit' not in workflow
    # 上传路径要同时覆盖版本化 EXE 与校验文件
    upload = workflow.split("Upload Windows asset", 1)[1].split("if-no-files-found", 1)[0]
    assert "dist/${{ env.PRODUCT_NAME }}-${{ env.VERSION }}-portable.exe" in upload
    assert "dist/SHA256SUMS.txt" in upload
    # 旧的 v1.4.2 发布说明必须整段换掉，notes 讲的是 Video2Knowledge beta
    notes = workflow.split("NOTES=$(cat <<EOF", 1)[1].split("EOF", 1)[0]
    assert "v1.4.2 更新" not in notes
    assert "beta" in notes


def test_beta4_page_and_capture_match_runtime_version() -> None:
    page = (PROJECT_ROOT / 'frontend/index.html').read_text(encoding='utf-8')
    capture = (PROJECT_ROOT / 'scripts/capture_readme_screenshots.mjs').read_text(encoding='utf-8')
    assert f'>v{product_info.VERSION}</span>' in page
    assert f"=== 'v{product_info.VERSION}'" in capture
    assert 'script.js?v=20261024-4' in page


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
    monkeypatch.delenv("VIDEO2KNOWLEDGE_WORKSPACE", raising=False)
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
    monkeypatch.delenv("VIDEO2KNOWLEDGE_WORKSPACE", raising=False)
    monkeypatch.setenv("VIDEOTONOTES_WORKSPACE", ".")
    monkeypatch.setattr(launcher, "find_available_port", lambda: 1234)
    monkeypatch.setattr(launcher, "server_alive", lambda *_a, **_k: True)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda _url: None)
    monkeypatch.delenv("VIDEO2KNOWLEDGE_NO_BROWSER", raising=False)
    monkeypatch.setenv("VIDEOTONOTES_NO_BROWSER", "1")
    calls: list[str] = []
    monkeypatch.setattr(launcher, "run_asr_child", lambda: calls.append("child") or 0)

    assert launcher.main() == 0
    assert calls == []
