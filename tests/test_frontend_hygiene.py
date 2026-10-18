"""前端结构约束测试。

这里盯的都是历史上只能靠线上事故发现的那类问题：漏 bump `?v=` 让浏览器拿旧 JS
配新字段（所有模型显示"未缓存"）、HTML 改了 id 而 JS 还在绑旧 id（按钮"点了没反应"）、
以及把密钥写进浏览器存储。没有引入 JS 测试框架，这几条用源码结构就能钉住。
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
SCRIPT = (FRONTEND / "script.js").read_text(encoding="utf-8")
PAGE = (FRONTEND / "index.html").read_text(encoding="utf-8")

BOUND_ID = re.compile(r"bindListener\('([A-Za-z][A-Za-z0-9]*)'")
DECLARED_ID = re.compile(r'id="([A-Za-z][A-Za-z0-9]*)"')
SCRIPT_TAG = re.compile(r'<script src="script\.js\?v=(\d{8}-\d+)">')

# 旧版一个设置一个散装键，其中 llm_model_id 被所有 Provider 共用，
# 正是"切到自定义接口时填进 DeepSeek 模型名"的根因；迁移后不得再写回。
RETIRED_LOOSE_KEYS = (
    "llm_provider",
    "llm_model_id",
    "custom_base_url",
    "custom_model_name",
    "theme",
)


def test_all_browser_storage_writes_go_through_one_gate() -> None:
    assert SCRIPT.count("localStorage.setItem(") == 1
    gate = SCRIPT.split("function persistPrefs()", 1)[1].split("\n}", 1)[0]
    assert "localStorage.setItem(" in gate


def test_retired_loose_preference_keys_are_never_written() -> None:
    for key in RETIRED_LOOSE_KEYS:
        assert f"setItem('{key}'" not in SCRIPT


def test_script_tag_carries_a_cache_version() -> None:
    assert SCRIPT_TAG.search(PAGE), "script.js 必须带 ?v=YYYYMMDD-N（DEVELOPMENT.md 前端约定）"


def test_note_destination_is_persisted_and_only_sent_for_note_tasks() -> None:
    assert 'id="noteDestination"' in PAGE
    assert "'note_destination'" in SCRIPT.split("const GLOBAL_PREF_KEYS =", 1)[1].split("];", 1)[0]
    assert "values.note_destination = byId('noteDestination').value.trim()" in SCRIPT
    builder = SCRIPT.split("function buildSummarizeConfig(", 1)[1].split("\n}\n", 1)[0]
    transcript_branch, note_branch = builder.split("} else {", 1)
    assert "note_destination" not in transcript_branch
    assert "config.note_destination = noteDestination" in note_branch


def test_note_template_is_persisted_and_only_sent_for_note_tasks() -> None:
    assert 'id="noteTemplate"' in PAGE
    assert "'note_template_id'" in SCRIPT.split("const GLOBAL_PREF_KEYS =", 1)[1].split("];", 1)[0]
    builder = SCRIPT.split("function buildSummarizeConfig(", 1)[1].split("\n}\n", 1)[0]
    transcript_branch, note_branch = builder.split("} else {", 1)
    assert "note_template_id" not in transcript_branch
    assert "note_template_id" in note_branch


def test_feishu_preferences_are_stored_and_only_sent_for_note_tasks() -> None:
    assert 'id="feishuUploadEnabled"' in PAGE
    assert 'id="feishuFolder"' in PAGE
    keys = SCRIPT.split("const GLOBAL_PREF_KEYS =", 1)[1].split("];", 1)[0]
    assert "'feishu_upload_enabled'" in keys
    assert "'feishu_folder'" in keys
    assert "values.feishu_upload_enabled = byId('feishuUploadEnabled').checked" in SCRIPT
    builder = SCRIPT.split("function buildSummarizeConfig(", 1)[1].split("\n}\n", 1)[0]
    transcript_branch, note_branch = builder.split("} else {", 1)
    assert "feishu_upload_enabled" not in transcript_branch
    assert "feishu_upload_enabled" in note_branch


def test_feishu_retry_button_confirms_before_publication_only_retry() -> None:
    """重试只走发布端点，且必须先确认可能产生重复远端文件。"""
    assert 'id="feishuRetryBtn"' in PAGE
    assert "/feishu-upload" in SCRIPT
    retry = SCRIPT.split("async function retryFeishuUpload(", 1)[1].split("\n}\n", 1)[0]
    assert "window.confirm" in retry
    assert "POST" in retry


def test_feishu_ui_defaults_off_and_describes_online_doc_with_native_images() -> None:
    tag = re.search(r'<input type="checkbox" id="feishuUploadEnabled"[^>]*>', PAGE)
    assert tag, "必须存在飞书 opt-in 勾选框"
    assert "checked" not in tag.group(0), "飞书发布必须默认关闭"
    assert "在线文档" in PAGE
    assert "原生图片" in PAGE


def test_feishu_publication_renders_document_and_legacy_results() -> None:
    fn = SCRIPT.split("function renderFeishuPublication(", 1)[1].split("\n}\n", 1)[0]
    assert "publication.document" in fn
    assert "已创建飞书在线文档" in fn
    # 历史已完成任务的 markdown/zip 成功结果仍须可展示，不得因字段缺失报错
    assert "publication.markdown" in fn
    assert "publication.zip" in fn


def test_feishu_publication_link_is_safe_and_never_innerHTML() -> None:
    fn = SCRIPT.split("function renderFeishuPublication(", 1)[1].split("\n}\n", 1)[0]
    assert "innerHTML" not in fn, "不得用 innerHTML 渲染 CLI 数据或 URL"
    assert "createElement('a')" in fn
    assert "https://" in fn


def test_feishu_publication_surfaces_partial_warning_without_retry() -> None:
    fn = SCRIPT.split("function renderFeishuPublication(", 1)[1].split("\n}\n", 1)[0]
    assert "publication.warning" in fn
    assert "warning.message" in fn
    assert "retryBtn.hidden = true" in fn


def test_feishu_readiness_hint_uses_docs_command() -> None:
    fn = SCRIPT.split("function renderFeishuReadiness(", 1)[1].split("\n}\n", 1)[0]
    assert "docs" in fn


def test_obsidian_vault_selection_fills_existing_destination_field() -> None:
    """Vault 选择只是对 noteDestination 的便捷填充，不引入第二套目的地字段。"""
    assert 'id="obsidianVaultSelect"' in PAGE
    assert 'id="obsidianSubfolder"' in PAGE
    assert 'id="obsidianRefreshBtn"' in PAGE
    assert "note-destinations" in SCRIPT
    assert "byId('noteDestination').value =" in SCRIPT


def test_note_submit_is_blocked_until_template_list_is_ready() -> None:
    """模板列表加载中/加载失败时提交笔记会静默退回默认模板，覆盖用户保存的选择。"""
    start = SCRIPT.split("async function startSummary(", 1)[1].split("\n}\n", 1)[0]
    assert "noteTemplatesStatus" in start
    assert SCRIPT.count("noteTemplatesStatus = 'ready'") == 1


def test_template_load_error_hint_survives_detail_refresh() -> None:
    """回归：error 分支里 updateNoteTemplateDetails() 会把说明清空成空串，
    错误提示必须在它之后写入，否则用户看不到加载失败的原因。"""
    renderer = SCRIPT.split("function renderNoteTemplateOptions(", 1)[1].split("\n}\n", 1)[0]
    error_branch = renderer.split("noteTemplatesStatus === 'error'", 1)[1]
    hint_pos = error_branch.index("模板列表加载失败")
    refresh_pos = error_branch.index("updateNoteTemplateDetails()")
    assert refresh_pos < hint_pos, "错误提示必须在 updateNoteTemplateDetails() 之后写入"


def test_note_images_are_resolved_on_every_output_path() -> None:
    """截图只在预览里改路径、导出全是坏链，就是 1.4.1 修的那个问题。"""
    assert "(?:frames|images)" in SCRIPT, "预览要同时认 frames 与历史笔记里的 images"

    download_summary = SCRIPT.split("async function downloadSummary(", 1)[1].split("\n}\n", 1)[0]
    assert "inlineServedImages(" in download_summary, "HTML 导出必须内联截图"

    markdown_download = SCRIPT.split(
        "async function downloadMarkdownFile(", 1
    )[1].split("\n}\n", 1)[0]
    assert "serverFilename(" in markdown_download, "带截图时后端发的是 zip，后缀不能写死"


def test_browser_side_downloads_are_named_after_the_note() -> None:
    assert "let currentDownloadName = ''" in SCRIPT
    assert "function noteFileName(" in SCRIPT
    for name in (
        "downloadSummary",
        "downloadSrtFile",
        "exportSummaryImage",
        "downloadCanvasPages",
    ):
        body = SCRIPT.split(f"function {name}(", 1)[1].split("\n}\n", 1)[0]
        assert "noteFileName(" in body, f"{name} 里的下载没取后端下发的文件名"
    assert SCRIPT.count("task.download_name") == 2, "历史与轮询两条路都要带上下载名"
    complete = SCRIPT.split("async function completeTask(", 1)[1].split("\n}\n", 1)[0]
    assert "downloadName" in complete and "currentDownloadName" in complete
    reset = SCRIPT.split("function resetTaskView(", 1)[1].split("\n}\n", 1)[0]
    assert "currentDownloadName = ''" in reset
    markdown = SCRIPT.split(
        "async function downloadMarkdownFile(", 1
    )[1].split("\n}\n", 1)[0]
    assert "serverFilename(" in markdown and "noteFileName('.md')" in markdown
    srt = SCRIPT.split("async function downloadSrtFile(", 1)[1].split("\n}\n", 1)[0]
    assert "data.filename" in srt and "noteFileName('.srt')" in srt
    pages = SCRIPT.split(
        "async function downloadCanvasPages(", 1
    )[1].split("\n}\n", 1)[0]
    assert "-page-" in pages and "noteFileName(" in pages


def test_subtitle_source_mode_controls_accept_list_and_hides_recognition() -> None:
    assert '<option value="subtitle">字幕文件</option>' in PAGE
    assert 'id="recognitionSection"' in PAGE
    assert 'id="filePickerLabel"' in PAGE
    fn = SCRIPT.split("function toggleSourceType(", 1)[1].split("\n}\n", 1)[0]
    assert "SUBTITLE_ACCEPT" in fn, "字幕模式必须切换到 .srt,.vtt"
    assert "MEDIA_ACCEPT" in fn, "切回媒体模式必须恢复媒体 accept 列表"
    assert "recognitionSection" in fn, "字幕模式必须隐藏识别设置"
    assert "filePickerLabel" in fn


def test_subtitle_client_uses_separate_size_limit() -> None:
    assert "DEFAULT_MAX_SUBTITLE_MB" in SCRIPT
    assert "maxSubtitleBytes" in SCRIPT
    assert "maxSubtitleLabel" in SCRIPT
    fn = SCRIPT.split("function validateAndBuildRequestBase(", 1)[1].split("\n}\n", 1)[0]
    assert "maxSubtitleBytes" in fn
    assert "请选择字幕文件" in fn


def test_srt_export_is_rendered_by_backend_with_safe_filename() -> None:
    assert '<option value="srt">' in PAGE, "导出菜单里没有字幕这一项"
    assert "format === 'srt'" in SCRIPT
    body = SCRIPT.split("function downloadSrtFile(", 1)[1].split("\n}\n", 1)[0]
    assert "output_format=srt" in body
    assert "currentMarkdown" not in body, "SRT 不能由前端那份整秒 markdown 现拼"
    assert "data.filename" in body


def test_every_bound_element_id_exists_in_the_page() -> None:
    missing = sorted(set(BOUND_ID.findall(SCRIPT)) - set(DECLARED_ID.findall(PAGE)))
    assert not missing, f"script.js 绑定了页面里不存在的元素：{missing}"


def test_local_import_hint_guides_platform_exports() -> None:
    """选择“本地文件”时提示：小鹅通等平台先用平台允许的方式导出再上传。"""
    match = re.search(r'<p id="localImportHint"[^>]*>(.*?)</p>', PAGE, re.S)
    assert match, "页面必须有 localImportHint 提示元素"
    text = match.group(1)
    assert "小鹅通" in text
    assert "导出" in text or "下载" in text
    assert "绕过" in text, "必须明示不支持绕过付费/登录/内容保护"
    toggle = SCRIPT.split("function toggleSourceType()", 1)[1].split("\n}\n", 1)[0]
    assert "localImportHint" in toggle, "提示的显隐必须跟随来源切换"


def test_media_retention_preferences_and_request() -> None:
    assert 'id="mediaRetentionDays"' in PAGE
    assert 'id="mediaRetentionCleanupBtn"' in PAGE
    assert 'id="mediaRetentionStatus"' in PAGE
    keys = SCRIPT.split("const GLOBAL_PREF_KEYS =", 1)[1].split("];", 1)[0]
    assert "'media_retention_days'" in keys
    assert "media_retention_days: 'forever'" in SCRIPT
    assert "values.media_retention_days" in SCRIPT
    health = SCRIPT.split("async function loadAppVersion()", 1)[1].split("\n}\n", 1)[0]
    assert "maybeCleanupRetainedMedia()" in health
    cleanup = SCRIPT.split("async function requestMediaRetentionCleanup(days)", 1)[1].split("\n}\n", 1)[0]
    assert "/media-retention/cleanup" in cleanup
    assert "JSON.stringify({ days })" in cleanup
    assert "catch" in cleanup
    manual = SCRIPT.split("async function cleanupRetainedMedia()", 1)[1].split("\n}\n", 1)[0]
    assert "window.confirm" in manual


def test_retention_browser_behavior_without_network() -> None:
    """Execute the actual JS in DOM/storage/fetch stubs, without network."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    harness = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const nodes = {};
const storage = {};
const calls = [];
const context = vm.createContext({
    console, setTimeout, clearTimeout, AbortController,
    window: { confirm: () => true, addEventListener() {}, setTimeout, clearTimeout },
    document: {
        addEventListener() {},
        querySelector: () => null,
        getElementById(id) {
            return nodes[id] ||= { value: '', textContent: '', disabled: false, checked: false };
        }
    },
    localStorage: {
        getItem: key => storage[key] || null,
        setItem: (key, value) => { storage[key] = value; },
        removeItem: key => { delete storage[key]; }
    },
    calls, assert
});
vm.runInContext(fs.readFileSync(0, 'utf8'), context);
(async () => {
    await vm.runInContext(`(async () => {
        updateMediaRetentionControls();
        assert.equal(byId('mediaRetentionCleanupBtn').disabled, true);
        fetchWithTimeout = async (url, options) => {
            calls.push({ url, options });
            return { ok: true, json: async () => ({
                scanned: 4, eligible: 2, removed_count: 3, warnings: []
            }) };
        };
        maybeCleanupRetainedMedia();
        mediaRetentionConnected = true;
        maybeCleanupRetainedMedia();
        assert.equal(calls.length, 0);
        prefs.global.media_retention_days = '7';
        persistPrefs();
        prefs = mergePrefs(readStoredPrefs());
        assert.equal(prefs.global.media_retention_days, '7');
        mediaRetentionStartupAttempted = false;
        maybeCleanupRetainedMedia();
        maybeCleanupRetainedMedia();
        await new Promise(resolve => setTimeout(resolve, 0));
        assert.equal(calls.length, 1);
        assert.equal(calls[0].url, '/api/media-retention/cleanup');
        assert.equal(calls[0].options.method, 'POST');
        assert.equal(calls[0].options.body, '{"days":7}');
        assert.match(byId('mediaRetentionStatus').textContent, /删除 3/);
        window.confirm = () => false;
        await cleanupRetainedMedia();
        assert.equal(calls.length, 1);
        window.confirm = () => true;
        await Promise.all([cleanupRetainedMedia(), cleanupRetainedMedia()]);
        assert.equal(calls.length, 2);
        fetchWithTimeout = async () => { throw new Error('private-path-secret'); };
        await requestMediaRetentionCleanup(7);
        assert.equal(mediaRetentionBusy, false);
        assert.match(byId('mediaRetentionStatus').textContent, /生成笔记仍可继续/);
        assert.equal(byId('mediaRetentionStatus').textContent.includes('secret'), false);
        prefs.global.media_retention_days = 'forever';
        updateMediaRetentionControls();
        await cleanupRetainedMedia();
        assert.equal(calls.length, 2);
    })()`, context);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, "-e", harness], input=SCRIPT, text=True, encoding="utf-8",
        capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def _builtin_providers() -> dict[str, dict[str, str]]:
    config = SCRIPT.split("const PROVIDER_CONFIG = ", 1)[1]
    found: dict[str, dict[str, str]] = {}
    for provider in ("deepseek", "openai", "glm", "qwen", "moonshot"):
        section = config.split(f"\n    {provider}: {{", 1)[1].split("\n    }},", 1)[0]
        found[provider] = {
            "baseUrl": re.search(r"baseUrl: '([^']*)'", section).group(1),
            "defaultModel": re.search(r"defaultModel: '([^']*)'", section).group(1),
        }
    return found


def test_builtin_provider_defaults_agree_between_front_and_back() -> None:
    """前端下拉的默认档/地址必须与后端 ``PROVIDER_DEFAULTS`` 是同一个值。

    两处各写一份（前端要显示名字，后端要兜住不带 model 的请求，例如 MCP 与 skill），
    换模型时只改一边就会出现"页面上选的是新模型、实际请求打到旧 ID"这种没人看得见
    的错——1.4.2 换 DeepSeek/GLM/Qwen 档位时就是这个形状。
    """
    from backend.llm_summarizer import PROVIDER_DEFAULTS

    for provider, fields in _builtin_providers().items():
        base_url, model = PROVIDER_DEFAULTS[provider]
        assert fields["baseUrl"] == base_url, f"{provider} 接口地址两边不一致"
        assert fields["defaultModel"] == model, (
            f"{provider} 默认模型两边不一致：前端 {fields['defaultModel']} "
            f"≠ 后端 {model}"
        )
