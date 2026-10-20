"""前端结构约束测试。

这里盯的都是历史上只能靠线上事故发现的那类问题：漏 bump `?v=` 让浏览器拿旧 JS
配新字段（所有模型显示"未缓存"）、HTML 改了 id 而 JS 还在绑旧 id（按钮"点了没反应"）、
以及把密钥写进浏览器存储。没有引入 JS 测试框架，这几条用源码结构就能钉住。
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = REPO_ROOT / "frontend"
SCRIPT = (FRONTEND / "script.js").read_text(encoding="utf-8")
PAGE = (FRONTEND / "index.html").read_text(encoding="utf-8")
CSS = (FRONTEND / "style.css").read_text(encoding="utf-8")
DESIGN_DOC = (REPO_ROOT / "DESIGN.md").read_text(encoding="utf-8")

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


def test_preference_namespace_is_v2k_with_vtn_fallback() -> None:
    """改名迁移：新键 v2k_prefs 优先，旧键 vtn_prefs 只读不删。"""
    assert "const PREFS_KEY = 'v2k_prefs'" in SCRIPT
    assert "const LEGACY_PREFS_KEY = 'vtn_prefs'" in SCRIPT
    reader = SCRIPT.split("function readStoredPrefs()", 1)[1].split("\n}", 1)[0]
    assert reader.index("PREFS_KEY") < reader.index("LEGACY_PREFS_KEY")
    assert "removeItem(LEGACY_PREFS_KEY)" not in SCRIPT
    assert "removeItem('vtn_prefs')" not in SCRIPT
    bootstrap = (FRONTEND / "theme-bootstrap.js").read_text(encoding="utf-8")
    assert bootstrap.index("'v2k_prefs'") < bootstrap.index("'vtn_prefs'")


def test_theme_bootstrap_falls_back_from_corrupt_v2k_to_vtn() -> None:
    """在存储桩里真跑 theme-bootstrap：v2k_prefs 损坏（非法 JSON）时
    必须落到 vtn_prefs.ui.theme，再坏才落到散装 'theme' 键；两个 prefs 键都只读不写。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    harness = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const storage = {
    v2k_prefs: '{corrupt json',
    vtn_prefs: JSON.stringify({ ui: { theme: 'dark' } })
};
const dataset = {};
const context = vm.createContext({
    console, setTimeout, clearTimeout,
    window: { addEventListener() {}, setTimeout, clearTimeout },
    document: {
        documentElement: { dataset },
        addEventListener() {},
        createElement: () => ({ setAttribute() {} }),
        body: { appendChild() {} }
    },
    localStorage: {
        getItem: key => (key in storage ? storage[key] : null),
        setItem: (key, value) => { storage[key] = value; },
        removeItem: key => { delete storage[key]; }
    }
});
const source = fs.readFileSync(0, 'utf8');
vm.runInContext(source, context);
// 新键损坏 -> 读旧键的主题
assert.equal(dataset.theme, 'dark');
// 两个键都只读：损坏的新键原样保留，旧键不动
assert.equal(storage.v2k_prefs, '{corrupt json');
assert.ok(storage.vtn_prefs.includes('dark'));
// 新键缺席、旧键解析出非对象 -> 落到更老的散装 theme 键
delete storage.v2k_prefs;
storage.vtn_prefs = '42';
storage.theme = 'light';
vm.runInContext(source, context);
assert.equal(dataset.theme, 'light');
// 全部不可用 -> system
delete storage.vtn_prefs;
delete storage.theme;
vm.runInContext(source, context);
assert.equal(dataset.theme, 'system');
"""
    bootstrap = (FRONTEND / "theme-bootstrap.js").read_text(encoding="utf-8")
    result = subprocess.run(
        [node, "-e", harness], input=bootstrap, text=True, encoding="utf-8",
        capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_console_prefixes_use_the_new_brand() -> None:
    """用户/开发者可见的 console 前缀一律 [Video2Knowledge]；
    兼容变量名（__videoToNoReady 等）与归属说明里的旧名不在此列。"""
    assert "[VideoToNo]" not in SCRIPT
    assert "[Video2Knowledge]" in SCRIPT
    bootstrap = (FRONTEND / "theme-bootstrap.js").read_text(encoding="utf-8")
    assert "[VideoToNo]" not in bootstrap


def test_vtn_prefs_migrate_to_v2k_without_losing_or_leaking() -> None:
    """在 DOM/存储桩里真跑迁移：vtn_prefs 的偏好进 v2k_prefs，旧键原样保留，敏感字段不进新键。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    harness = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const storage = {
    vtn_prefs: JSON.stringify({
        provider: 'qwen',
        global: { summary_style: 'concise' },
        ui: { theme: 'dark' },
        api_key: 'sk-legacysecret123456'
    })
};
const context = vm.createContext({
    console, setTimeout, clearTimeout, AbortController,
    window: { confirm: () => true, addEventListener() {}, setTimeout, clearTimeout },
    document: {
        addEventListener() {},
        querySelector: () => null,
        getElementById: () => null
    },
    localStorage: {
        getItem: key => (key in storage ? storage[key] : null),
        setItem: (key, value) => { storage[key] = value; },
        removeItem: key => { delete storage[key]; }
    },
    assert, storage
});
vm.runInContext(fs.readFileSync(0, 'utf8'), context);
vm.runInContext(`
    // 新键缺席：读到的是旧键内容
    assert.equal(readStoredPrefs().provider, 'qwen');
    prefs = mergePrefs(readStoredPrefs());
    assert.equal(prefs.global.summary_style, 'concise');
    assert.equal(prefs.ui.theme, 'dark');
    persistPrefs();
    // 迁移结果落进新键，且不带任何敏感字段
    const migratedRaw = storage['v2k_prefs'];
    assert.ok(migratedRaw, 'v2k_prefs 应被写入');
    const migrated = JSON.parse(migratedRaw);
    assert.equal(migrated.provider, 'qwen');
    assert.equal(migrated.ui.theme, 'dark');
    assert.ok(!migratedRaw.includes('sk-legacysecret123456'));
    // 旧键原样保留（不删不改）
    assert.ok(storage['vtn_prefs'].includes('sk-legacysecret123456'));
    // 新键存在后优先于旧键
    storage['v2k_prefs'] = JSON.stringify({ provider: 'glm' });
    assert.equal(readStoredPrefs().provider, 'glm');
`, context);
"""
    result = subprocess.run(
        [node, "-e", harness], input=SCRIPT, text=True, encoding="utf-8",
        capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


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


def test_completed_notice_prefers_archived_file() -> None:
    assert 'id="outputPathLabel"' in PAGE
    assert 'id="taskDirNotice"' in PAGE
    assert 'id="taskDirPath"' in PAGE
    assert 'id="archivedPath"' not in PAGE
    fn = SCRIPT.split("async function showResult(", 1)[1].split("\n}\n", 1)[0]
    assert "archivedPath || outputDirectory" in fn
    assert "'已保存到'" in fn
    assert "taskDirNotice" in fn and "taskDirPath" in fn
    reset = SCRIPT.split("function resetTaskView(", 1)[1].split("\n}\n", 1)[0]
    assert "taskDirPath" in reset


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


# ---- Knowledge Studio 布局交互（DESIGN.md 合同） ----
# 下面三组行为测试共用一个 DOM 桩：只实现设置抽屉、方案摘要、运行记录真正
# 触到的那一小面 DOM（hidden/aria/focus/事件分发/select options）。
# window 上的定时器是 no-op，否则 showToast 的 4.2s 定时器会拖住进程退出。

_DOM_STUB_PRELUDE = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');

const __focusLog = [];
const __documentListeners = {};
function __makeElement(id) {
    return {
        id: id || '',
        hidden: false,
        value: '',
        textContent: '',
        className: '',
        checked: false,
        disabled: false,
        open: false,
        selectedIndex: 0,
        options: [],
        style: {},
        dataset: {},
        attrs: {},
        listeners: {},
        scrollTop: 0,
        scrollHeight: 0,
        setAttribute(name, value) { this.attrs[name] = String(value); },
        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
        },
        addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); },
        dispatch(type, event = {}) {
            (this.listeners[type] || []).slice().forEach((handler) => handler(event));
        },
        focus() { __focusLog.push(this.id || '(anonymous)'); },
        remove() {},
        appendChild() {},
        replaceChildren() {},
        scrollIntoView() {},
        querySelector() { return __makeElement(); },
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } }
    };
}
const __elements = {};
const __el = (id) => (__elements[id] ||= __makeElement(id));
const document = {
    documentElement: { dataset: {} },
    getElementById: (id) => __el(id),
    addEventListener(type, handler) { (__documentListeners[type] ||= []).push(handler); },
    dispatch(type, event = {}) {
        (__documentListeners[type] || []).slice().forEach((handler) => handler(event));
    },
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: () => __makeElement(),
    body: __makeElement('body')
};
const __storage = {};
const context = vm.createContext({
    console, setTimeout, clearTimeout, AbortController,
    window: {
        addEventListener() {},
        confirm: () => true,
        setTimeout: () => 1,
        clearTimeout() {},
        setInterval: () => 1,
        clearInterval() {}
    },
    document,
    localStorage: {
        getItem: (key) => (key in __storage ? __storage[key] : null),
        setItem: (key, value) => { __storage[key] = String(value); },
        removeItem: (key) => { delete __storage[key]; }
    },
    fetch: async () => { throw new Error('network disabled in test'); },
    assert, __el, __elements, __focusLog
});
vm.runInContext(fs.readFileSync(0, 'utf8'), context);
"""


def _run_script_with_dom_stub(scenario: str) -> None:
    """在 DOM/存储桩里真跑整份 script.js，然后执行 scenario 片段做断言。"""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is unavailable")
    harness = (
        _DOM_STUB_PRELUDE
        + "\nvm.runInContext("
        + json.dumps(scenario)
        + ", context);\n"
    )
    result = subprocess.run(
        [node, "-e", harness], input=SCRIPT, text=True, encoding="utf-8",
        capture_output=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_settings_drawer_open_close_escape_and_focus_return() -> None:
    """设置抽屉合同（DESIGN.md「Components / Accessibility」）：
    settingsToggleBtn 开合；关闭按钮、遮罩、Escape 都能关；aria-expanded 同步；
    打开时焦点进面板（关闭按钮），关闭后焦点回到触发按钮。"""
    _run_script_with_dom_stub(r"""
const panel = __el('settingsPanel');
const backdrop = __el('settingsBackdrop');
const toggle = __el('settingsToggleBtn');
const closeButton = __el('settingsCloseBtn');
// 镜像 index.html 初始状态：面板与遮罩隐藏，aria-expanded=false
panel.hidden = true;
backdrop.hidden = true;
toggle.setAttribute('aria-expanded', 'false');
bindSettingsPanel();
assert.equal(isSettingsPanelOpen(), false);

// 设置按钮打开：面板 + 遮罩显示、aria-expanded 同步、焦点进入面板
toggle.dispatch('click');
assert.equal(isSettingsPanelOpen(), true);
assert.equal(panel.hidden, false);
assert.equal(backdrop.hidden, false);
assert.equal(toggle.getAttribute('aria-expanded'), 'true');
assert.equal(__focusLog.at(-1), 'settingsCloseBtn');

// Escape 关闭：焦点回到触发按钮
document.dispatch('keydown', { key: 'Escape' });
assert.equal(isSettingsPanelOpen(), false);
assert.equal(panel.hidden, true);
assert.equal(backdrop.hidden, true);
assert.equal(toggle.getAttribute('aria-expanded'), 'false');
assert.equal(__focusLog.at(-1), 'settingsToggleBtn');

// 关闭按钮关闭
toggle.dispatch('click');
assert.equal(isSettingsPanelOpen(), true);
closeButton.dispatch('click');
assert.equal(isSettingsPanelOpen(), false);
assert.equal(toggle.getAttribute('aria-expanded'), 'false');
assert.equal(__focusLog.at(-1), 'settingsToggleBtn');

// 遮罩点击关闭
toggle.dispatch('click');
backdrop.dispatch('click');
assert.equal(isSettingsPanelOpen(), false);
assert.equal(__focusLog.at(-1), 'settingsToggleBtn');

// 打开状态下再点设置按钮 = 关闭（开关语义）
toggle.dispatch('click');
assert.equal(isSettingsPanelOpen(), true);
toggle.dispatch('click');
assert.equal(isSettingsPanelOpen(), false);

// 已关闭时按 Escape 不应再抢焦点（early return）
const focusCount = __focusLog.length;
document.dispatch('keydown', { key: 'Escape' });
assert.equal(__focusLog.length, focusCount);
""")


def test_plan_summary_follows_mode_model_template_destination_and_feishu() -> None:
    """方案摘要合同：一行实时跟随输出类型、档案/模型、模板、目的地与飞书开关。"""
    _run_script_with_dom_stub(r"""
const outputRadios = [__el('outputModeNote'), __el('outputModeTranscript')];
outputRadios[0].value = 'note';
outputRadios[0].checked = true;
outputRadios[1].value = 'transcript';
document.querySelector = (selector) =>
    selector === 'input[name="outputMode"]:checked'
        ? outputRadios.find((radio) => radio.checked) || null
        : null;
document.querySelectorAll = (selector) =>
    selector === 'input[name="outputMode"]' ? outputRadios : [];

const llmModel = __el('llmModel');
llmModel.options = [
    { value: 'deepseek-flash', textContent: 'DeepSeek V4.1 Flash' },
    { value: 'deepseek-v4-pro', textContent: 'DeepSeek V4 Pro' },
    { value: '__custom__', textContent: '手动输入' }
];
llmModel.value = 'deepseek-flash';
llmModel.selectedIndex = 0;
const whisperModel = __el('whisperModel');
whisperModel.options = [
    { value: 'base', textContent: 'base（默认，下载较小）' },
    { value: 'small', textContent: 'small（中文更准确）' }
];
whisperModel.value = 'base';
whisperModel.selectedIndex = 0;

// 绑定前建好所有被监听的元素（bindListener 只在绑定时取一次元素）
['llmProfile', 'noteTemplate', 'feishuUploadEnabled', 'obsidianVaultSelect',
    'obsidianSubfolder', 'noteDestination', 'customModelName', 'planSummary']
    .forEach((id) => __el(id));
bindPlanSummary();
const summary = __el('planSummary');
// 默认（笔记模式）：产物 + 档案/模型 + 模板 + 默认目的地，不提飞书
assert.ok(summary.textContent.includes('生成笔记'));
assert.ok(summary.textContent.includes('DeepSeek · DeepSeek V4.1 Flash'));
assert.ok(summary.textContent.includes('模板：默认模板'));
assert.ok(summary.textContent.includes('保存到：workspace/notes'));
assert.ok(!summary.textContent.includes('飞书'));

// 飞书开关
__el('feishuUploadEnabled').checked = true;
__el('feishuUploadEnabled').dispatch('change');
assert.ok(summary.textContent.includes('完成后上传飞书'));
__el('feishuUploadEnabled').checked = false;
__el('feishuUploadEnabled').dispatch('change');
assert.ok(!summary.textContent.includes('飞书'));

// 目的地输入（input 即时更新）
__el('noteDestination').value = 'D:/vault/inbox';
__el('noteDestination').dispatch('input');
assert.ok(summary.textContent.includes('保存到：D:/vault/inbox'));

// 模板切换
noteTemplates.push({ id: 'tpl-weekly', name: '周报模板', description: '', built_in: false });
const noteTemplate = __el('noteTemplate');
noteTemplate.value = 'tpl-weekly';
noteTemplate.dispatch('change');
assert.ok(summary.textContent.includes('模板：周报模板'));

// 模型切换
llmModel.selectedIndex = 1;
llmModel.value = 'deepseek-v4-pro';
llmModel.dispatch('change');
assert.ok(summary.textContent.includes('DeepSeek · DeepSeek V4 Pro'));

// 手动模型 ID
llmModel.selectedIndex = 2;
llmModel.value = '__custom__';
__el('customModelName').value = 'proxy-model-x';
__el('customModelName').dispatch('input');
assert.ok(summary.textContent.includes('proxy-model-x'));

// 切到仅转录：摘要换成转写路线，跟 Whisper 档位走
outputRadios[0].checked = false;
outputRadios[1].checked = true;
outputRadios[1].dispatch('change');
assert.ok(summary.textContent.includes('仅转录字幕'));
assert.ok(summary.textContent.includes('本地识别：base（默认，下载较小）'));
assert.ok(!summary.textContent.includes('生成笔记'));
whisperModel.selectedIndex = 1;
whisperModel.value = 'small';
whisperModel.dispatch('change');
assert.ok(summary.textContent.includes('本地识别：small（中文更准确）'));
""")


def test_task_log_details_collapsed_by_default_open_on_failure_recollapse_on_new_task() -> None:
    """运行记录合同（DESIGN.md「Interaction states」）：默认折叠；任务失败自动展开；
    新任务开始（resetTaskView 是提交/重开任务的公共入口）回到折叠。"""
    _run_script_with_dom_stub(r"""
document.querySelector = (selector) =>
    selector === '[role="progressbar"]' ? __el('progressBar') : null;
const details = __el('taskLogDetails');
assert.equal(details.open, false);

// 失败：自动展开运行记录，失败原因与最后一段日志直接可见
failTask('网络中断');
assert.equal(details.open, true);
assert.equal(__el('taskError').hidden, false);

// 新任务开始：重新折叠，失败面板同时收起
resetTaskView();
assert.equal(details.open, false);
assert.equal(__el('taskError').hidden, true);

// 再次失败再次展开
failTask('转写失败');
assert.equal(details.open, true);
""")


def test_settings_panel_keeps_four_named_groups_in_fixed_order() -> None:
    """设置面板四组、顺序固定（DESIGN.md「Information architecture」）。"""
    assert PAGE.count('class="settings-group"') == 4
    groups = [
        ("settingsGroupNoteTitle", "笔记生成"),
        ("settingsGroupTranscribeTitle", "本地转录"),
        ("settingsGroupDestinationTitle", "输出目的地"),
        ("settingsGroupStorageTitle", "存储与接入"),
    ]
    positions = []
    for group_id, title in groups:
        tag = re.search(
            rf'<h2 id="{group_id}" class="settings-group-title">{title}</h2>', PAGE
        )
        assert tag, f"设置分组缺失或标题被改：{group_id} {title}"
        positions.append(tag.start())
    assert positions == sorted(positions), "四个设置分组的顺序被改动"


def test_main_reading_axis_order_and_drawer_placement() -> None:
    """主阅读轴顺序：composer（输出类型单选 → 方案摘要）→ 最近任务 → 进度 → 结果；
    设置抽屉与遮罩在 </main> 之外，首屏不常驻。"""
    assert PAGE.index('name="outputMode"') < PAGE.index('id="planSummary"'), (
        "方案摘要必须紧跟输出类型单选"
    )
    axis = [
        'class="source-panel"',
        'id="planSummary"',
        'id="recentTasksPanel"',
        'id="progressArea"',
        'id="resultArea"',
    ]
    positions = [PAGE.index(marker) for marker in axis]
    assert positions == sorted(positions), "主阅读轴顺序被改动"
    main_end = PAGE.index("</main>")
    assert main_end < PAGE.index('id="settingsBackdrop"') < PAGE.index('id="settingsPanel"')


def test_drawer_summary_and_log_accessibility_hooks() -> None:
    toggle = re.search(r'<button id="settingsToggleBtn"[^>]*>', PAGE)
    assert toggle, "设置入口按钮缺失"
    assert 'aria-expanded="false"' in toggle.group(0)
    assert 'aria-controls="settingsPanel"' in toggle.group(0)
    panel = re.search(r'<aside id="settingsPanel"[^>]*>', PAGE)
    assert panel, "设置抽屉缺失"
    assert "aria-label" in panel.group(0) and "hidden" in panel.group(0)
    assert 'id="settingsCloseBtn"' in PAGE, "抽屉内必须有关闭按钮"
    backdrop = re.search(r'<div id="settingsBackdrop"[^>]*>', PAGE)
    assert backdrop and "hidden" in backdrop.group(0), "遮罩必须默认隐藏"
    summary = re.search(r'<p id="planSummary"[^>]*>', PAGE)
    assert summary and 'aria-live="polite"' in summary.group(0), "方案摘要必须 aria-live"
    details = re.search(r'<details id="taskLogDetails"[^>]*>', PAGE)
    assert details, "运行记录必须是语义化 <details>"
    assert "open" not in details.group(0), "运行记录默认折叠，不得带 open 属性"
    assert re.search(r'<details id="taskLogDetails"[\s\S]*?<summary', PAGE), (
        "运行记录必须配 <summary>"
    )


def test_css_keeps_responsive_focus_motion_and_overflow_contracts() -> None:
    """CSS 合同：1024/680 两档响应式、focus-visible 描边、reduced-motion、
    页面级 overflow-x 兜底、移动端设置面板全宽覆盖。"""
    assert "@media (max-width: 1024px)" in CSS
    assert "@media (max-width: 680px)" in CSS
    mobile = CSS.split("@media (max-width: 680px)", 1)[1]
    panel_rule = re.search(r"\.settings-panel \{[^}]*\}", mobile)
    assert panel_rule and "100vw" in panel_rule.group(0), (
        "移动端设置面板必须是全宽覆盖层"
    )
    assert re.search(r"html, body \{[^}]*overflow-x: clip", CSS), (
        "页面级横向滚动兜底被移除"
    )
    assert "button:focus-visible" in CSS
    assert "outline: 2px solid var(--primary)" in CSS
    assert "outline-offset: 2px" in CSS
    motion = CSS.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert "animation-duration" in motion and "transition-duration" in motion
    # 主阅读轴居中上限（>1024px 档）
    assert re.search(r"\.workspace \{[^}]*max-width: 880px", CSS)


def test_brand_assets_regenerate_byte_identical() -> None:
    """品牌资产可重复生成：用仓库脚本在内存里重渲染，必须与 Git 里的
    sources/icon.png / sources/icon.ico 逐字节一致（禁止手工编辑图片）。"""
    pytest.importorskip("PIL")
    spec = importlib.util.spec_from_file_location(
        "make_brand_assets", REPO_ROOT / "scripts" / "make_brand_assets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    image = module.render_mark(module.FINAL_SIZE)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    assert buffer.getvalue() == (REPO_ROOT / "sources" / "icon.png").read_bytes(), (
        "sources/icon.png 与脚本输出不一致：请用 scripts/make_brand_assets.py 重新生成"
    )

    frames = [
        (size, image.resize((size, size), module.Image.Resampling.LANCZOS))
        for size in module.make_icon.SIZES
    ]
    assert module.make_icon.build_ico(frames) == (
        REPO_ROOT / "sources" / "icon.ico"
    ).read_bytes(), "sources/icon.ico 与脚本输出不一致"


def test_brand_tokens_and_geometry_agree_across_design_script_and_css() -> None:
    """DESIGN.md 是设计基线：标志取色、几何与关键 token 必须和
    scripts/make_brand_assets.py、frontend/style.css 说的是同一组值。"""
    source = (REPO_ROOT / "scripts" / "make_brand_assets.py").read_text(encoding="utf-8")
    icon_script = (REPO_ROOT / "scripts" / "make_icon.py").read_text(encoding="utf-8")
    css = CSS.lower()

    # 渐变取色与节点色：脚本常量、DESIGN.md、CSS token 三处一致
    assert "INDIGO = (79, 70, 229)" in source  # #4F46E5
    assert "CYAN = (8, 145, 178)" in source    # #0891B2
    assert "NODE = (165, 243, 252)" in source  # #A5F3FC
    for hex_token in ("#4F46E5", "#0891B2", "#A5F3FC"):
        assert hex_token in DESIGN_DOC, f"DESIGN.md 丢了品牌色 {hex_token}"
    assert "--primary: #4f46e5" in css
    assert "--accent: #0891b2" in css

    # 主色三档（DESIGN.md 表格与 style.css 实际 token 对齐）
    assert "--primary-hover" in DESIGN_DOC
    assert "--primary-hover: #4338ca" in css and "#4338CA" in DESIGN_DOC
    assert "--primary-hover: #6366f1" in css and "#6366F1" in DESIGN_DOC

    # 几何与构造：圆角 22%、1024 PNG、4 倍超采样、ICO 七档尺寸
    assert "CORNER_RADIUS = 0.22" in source
    assert "22%" in DESIGN_DOC
    assert "FINAL_SIZE = 1024" in source
    assert "1024×1024" in DESIGN_DOC
    assert "SUPERSAMPLE = 4" in source
    sizes = re.search(r"SIZES = \[([\d, ]+)\]", icon_script)
    assert sizes, "make_icon.py 的 ICO 尺寸表被改动"
    for size in ("16", "24", "32", "48", "64", "128", "256"):
        assert size in sizes.group(1).split(", ")
    assert "16/24/32/48/64/128/256" in DESIGN_DOC
