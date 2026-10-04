"""笔记模板契约测试：内置模板、后端 CRUD、布局安全校验、任务快照与确定性渲染。

测试先行：本文件里的用例在当前实现下必须失败（backend.note_templates 尚不存在、
SummarizeRequest 没有 note_template_id、渲染/frontmatter 尚未接入流水线）。
"""
import asyncio
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main, note_templates
from backend.note_templates import (
    ALLOWED_PLACEHOLDERS,
    CORNELL_TEMPLATE_ID,
    DEFAULT_TEMPLATE_ID,
    GENERAL_TEMPLATE_ID,
    INTERVIEW_TEMPLATE_ID,
    TUTORIAL_TEMPLATE_ID,
    TemplateImmutableError,
    TemplateNotFoundError,
    TemplateStore,
    TemplateValidationError,
)


def _store(tmp_path: Path) -> TemplateStore:
    return TemplateStore(tmp_path / "note_templates")


# ---------------------------------------------------------------------------
# 内置模板与默认值
# ---------------------------------------------------------------------------

def test_four_builtin_templates_exist_and_general_is_default(tmp_path: Path) -> None:
    store = _store(tmp_path)
    templates = store.list_templates()
    ids = {template.id for template in templates}
    assert ids == {
        GENERAL_TEMPLATE_ID,
        CORNELL_TEMPLATE_ID,
        TUTORIAL_TEMPLATE_ID,
        INTERVIEW_TEMPLATE_ID,
    }
    assert DEFAULT_TEMPLATE_ID == GENERAL_TEMPLATE_ID
    assert store.get(DEFAULT_TEMPLATE_ID).built_in is True
    for template in templates:
        assert template.built_in is True
        assert template.version >= 1
        assert template.layout.count("{{content}}") == 1
        # 内置布局本身必须通过安全校验
        assert note_templates.validate_layout(template.layout)


def test_builtin_templates_are_immutable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for template_id in (
        GENERAL_TEMPLATE_ID,
        CORNELL_TEMPLATE_ID,
        TUTORIAL_TEMPLATE_ID,
        INTERVIEW_TEMPLATE_ID,
    ):
        with pytest.raises(TemplateImmutableError):
            store.update(template_id, name="改名")
        with pytest.raises(TemplateImmutableError):
            store.delete(template_id)
    # 不可变指的不只是报错：名单与内容保持原样
    assert len(store.list_templates()) == 4


# ---------------------------------------------------------------------------
# 自定义模板 CRUD 与版本递增
# ---------------------------------------------------------------------------

def test_custom_template_crud_persists_and_increments_version(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create(
        name="我的模板",
        description="描述",
        instructions="按话题组织",
        layout="# {{title}}\n\n{{content}}\n\n> 来源：{{platform}}",
    )
    assert created.built_in is False
    assert created.version == 1
    # 后端持久化：文件落在 store 目录，重新打开仍在
    persisted_file = store.directory / f"{created.id}.json"
    assert persisted_file.is_file()
    reloaded = TemplateStore(store.directory).get(created.id)
    assert reloaded.name == "我的模板"
    assert reloaded.layout == created.layout

    updated = store.update(created.id, layout="# {{title}}\n\n{{content}}\n\n尾注")
    assert updated.version == 2
    again = store.update(created.id, name="新名字")
    assert again.version == 3
    assert again.name == "新名字"
    assert TemplateStore(store.directory).get(created.id).version == 3

    store.delete(created.id)
    assert store.get(created.id) is None
    assert not persisted_file.exists()
    assert len(store.list_templates()) == 4  # 只剩内置


def test_store_unknown_id_raises_not_found(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(TemplateNotFoundError):
        store.update("custom-missing", name="x")
    with pytest.raises(TemplateNotFoundError):
        store.delete("custom-missing")


def test_empty_update_is_rejected_without_version_bump(tmp_path: Path) -> None:
    """不带任何字段的更新是无意义增版：直接拒绝，版本号不动。"""
    store = _store(tmp_path)
    created = store.create(name="模板", layout="# {{title}}\n\n{{content}}")
    with pytest.raises(TemplateValidationError, match="没有需要更新的字段"):
        store.update(created.id)
    assert store.get(created.id).version == 1


def test_corrupt_custom_template_file_is_ignored(tmp_path: Path) -> None:
    """损坏的自定义模板文件：列表忽略、按 ID 取视为不存在，不影响内置模板。"""
    store = _store(tmp_path)
    created = store.create(name="好模板", layout="# {{title}}\n\n{{content}}")
    broken = store.directory / "custom-broken.json"
    broken.write_text("{ not valid json", encoding="utf-8")
    builtin_shaped = store.directory / "custom-evil.json"
    builtin_shaped.write_text(
        '{"id":"custom-evil","name":"x","layout":"{{content}}","built_in":true}',
        encoding="utf-8",
    )
    ids = {template.id for template in store.list_templates()}
    assert created.id in ids
    assert "custom-broken" not in ids
    assert "custom-evil" not in ids
    assert len(ids) == 5
    assert store.get("custom-broken") is None
    assert store.get("custom-evil") is None


@pytest.mark.parametrize(
    "payload",
    [
        # version 不是正整数：字符串、布尔、零、负数
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "layout": "{{content}}", "version": "oops", "built_in": False},
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "layout": "{{content}}", "version": True, "built_in": False},
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "layout": "{{content}}", "version": 0, "built_in": False},
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "layout": "{{content}}", "version": -2, "built_in": False},
        # id 与文件名不一致 / id 形态非法
        {"id": "custom-ffffffffffff", "name": "x", "layout": "{{content}}", "version": 1, "built_in": False},
        {"id": "../escape", "name": "x", "layout": "{{content}}", "version": 1, "built_in": False},
        # name 为空或超长
        {"id": "custom-a1b2c3d4e5f6", "name": "  ", "layout": "{{content}}", "version": 1, "built_in": False},
        {"id": "custom-a1b2c3d4e5f6", "name": "名" * 81, "layout": "{{content}}", "version": 1, "built_in": False},
        # description / instructions 超长
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "description": "说" * 301, "layout": "{{content}}", "version": 1, "built_in": False},
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "instructions": "指" * 4001, "layout": "{{content}}", "version": 1, "built_in": False},
        # layout 缺 content / 含未知占位符 / 含可执行语法 / 超长
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "layout": "# {{title}}", "version": 1, "built_in": False},
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "layout": "{{content}} {{unknown}}", "version": 1, "built_in": False},
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "layout": "{{content}} {% if x %}y{% endif %}", "version": 1, "built_in": False},
        {"id": "custom-a1b2c3d4e5f6", "name": "x", "layout": "{{content}}" + "x" * 8001, "version": 1, "built_in": False},
    ],
    ids=[
        "version_string", "version_bool", "version_zero", "version_negative",
        "id_mismatch", "id_traversal", "name_blank", "name_too_long",
        "description_too_long", "instructions_too_long",
        "layout_no_content", "layout_unknown_placeholder", "layout_executable", "layout_too_long",
    ],
)
def test_schema_damaged_custom_template_is_isolated(
    tmp_path: Path, payload: dict
) -> None:
    """合法 JSON 但 schema/字段损坏的自定义模板：列表忽略、按 id 取返回 None，不改写文件、不影响其他模板。"""
    store = _store(tmp_path)
    good = store.create(name="好模板", layout="# {{title}}\n\n{{content}}")
    damaged = store.directory / "custom-a1b2c3d4e5f6.json"
    damaged.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    before = damaged.read_bytes()

    templates = store.list_templates()
    ids = {template.id for template in templates}
    assert "custom-a1b2c3d4e5f6" not in ids
    assert good.id in ids  # 正常自定义模板不受影响
    assert len(ids) == 5  # 四个内置 + 一个好的自定义
    assert store.get("custom-a1b2c3d4e5f6") is None
    assert damaged.read_bytes() == before  # 隔离而不是改写


def test_template_field_length_limits(tmp_path: Path) -> None:
    store = _store(tmp_path)
    valid_layout = "# {{title}}\n\n{{content}}"
    with pytest.raises(TemplateValidationError, match="名称过长"):
        store.create(name="名" * 81, layout=valid_layout)
    with pytest.raises(TemplateValidationError, match="说明过长"):
        store.create(name="a", description="说" * 301, layout=valid_layout)
    with pytest.raises(TemplateValidationError, match="指令过长"):
        store.create(name="a", instructions="指" * 4001, layout=valid_layout)
    with pytest.raises(TemplateValidationError, match="布局过长"):
        store.create(name="a", layout="{{content}}" + "x" * 8001)
    created = store.create(name="a", layout=valid_layout)
    with pytest.raises(TemplateValidationError, match="名称过长"):
        store.update(created.id, name="名" * 81)


# ---------------------------------------------------------------------------
# 布局安全校验：白名单占位符、唯一 {{content}}、拒绝可执行语法
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "layout",
    [
        "# {{title}}\n\n正文，没有内容占位符",
        "# {{title}}\n\n{{content}}\n\n{{content}}",
        "# {{title}}\n\n{{content}}\n\n{{unknown_field}}",
        "# {{title}}\n\n{{content}}\n\n{{作者}}",
        "# {{title}}\n\n{{content}}\n\n{{content",  # 残缺占位符
        "# {{title}}\n\n{{content}}\n\n{% if x %}boom{% endif %}",
        "# {{title}}\n\n{{content}}\n\n{# 注释 #}",
        "# {{title}}\n\n{{content}}\n\n${HOME}",
        "# {{title}}\n\n{{content}}\n\n<% eval() %>",
        "# {{title}}\n\n{{content}}\n\n{!! raw !!}",
    ],
)
def test_layout_validation_rejects_unsafe_or_malformed_layouts(
    tmp_path: Path, layout: str
) -> None:
    store = _store(tmp_path)
    with pytest.raises(TemplateValidationError):
        store.create(name="坏模板", layout=layout)


def test_layout_validation_error_messages_are_stable(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(TemplateValidationError, match="必须包含且只能包含一个"):
        store.create(name="a", layout="# {{title}}")
    with pytest.raises(TemplateValidationError, match="不支持的占位符"):
        store.create(name="b", layout="{{content}}\n\n{{mystery}}")
    with pytest.raises(TemplateValidationError, match="可执行模板语法"):
        store.create(name="c", layout="{{content}}\n\n{% for x in y %}{{x}}{% endfor %}")
    with pytest.raises(TemplateValidationError, match="无法识别的占位符写法"):
        store.create(name="d", layout="{{content}}\n\n{{oops")
    with pytest.raises(TemplateValidationError, match="不能为空"):
        store.create(name="  ", layout="{{content}}")


def test_layout_validation_accepts_full_allowlist_and_normalizes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    layout = "\n".join(
        f"{{{{ {name} }}}}" if name != "content" else "{{content}}"
        for name in ALLOWED_PLACEHOLDERS
    )
    template = store.create(name="全占位符", layout=layout)
    # 带空白的占位符写法被规范化，渲染时不需要二次处理
    for name in ALLOWED_PLACEHOLDERS:
        assert f"{{{{{name}}}}}" in template.layout


# ---------------------------------------------------------------------------
# 确定性渲染：YAML Frontmatter + 唯一 Markdown 正文
# ---------------------------------------------------------------------------

def test_render_note_produces_frontmatter_plus_single_document() -> None:
    layout = "# {{title}}\n\n{{content}}\n\n> {{author}} · {{platform}}"
    values = {
        "title": "测试视频",
        "source_url": "https://www.bilibili.com/video/BV1xx",
        "platform": "bilibili",
        "author": "作者甲",
        "created_at": "2026-10-04T12:00:00+00:00",
        "transcript_source": "platform_subtitle",
        "template": "通用结构化笔记",
    }
    rendered = note_templates.render_note(layout, values, "## 草稿正文")
    assert rendered.startswith("---\n")
    assert "\n---\n" in rendered[4:]
    body = rendered.split("\n---\n", 1)[1]
    assert body.lstrip().startswith("# 测试视频")
    assert "## 草稿正文" in body
    assert "> 作者甲 · bilibili" in body


def test_apply_layout_never_resubstitutes_inserted_values() -> None:
    """回归：占位符替换只扫描原始布局一次，插入的正文/元数据里的占位符字面量必须原样保留。"""
    layout = "# {{title}}\n\n{{content}}"
    rendered = note_templates.apply_layout(
        layout, {"title": "讲解 {{author}} 用法的教程"}, "正文示例：{{title}} 与 {{content}}"
    )
    assert "讲解 {{author}} 用法的教程" in rendered
    assert "{{title}} 与 {{content}}" in rendered


def test_builtin_layouts_are_document_shells_without_empty_sections(tmp_path: Path) -> None:
    """内置布局只负责文档外壳：正文槽在末尾，之后不再追加无填充路径的空分区。"""
    store = _store(tmp_path)
    for template in store.list_templates():
        assert template.layout.strip().endswith("{{content}}"), template.id
        assert set(("title", "content")) >= set(
            re.findall(r"\{\{(\w+)\}\}", template.layout)
        )
    # 组织要求与长转录分段提示词（“不要总结全片”）不能互相矛盾
    for template in store.list_templates():
        assert "总结全片" not in template.instructions


def test_render_frontmatter_omits_missing_values() -> None:
    values = {
        "title": "只有标题",
        "source_url": None,
        "platform": "",
        "author": None,
        "created_at": "2026-10-04T12:00:00+00:00",
        "template": "通用结构化笔记",
        "transcript_source": "faster_whisper",
    }
    frontmatter = note_templates.render_frontmatter(values)
    assert 'title: "只有标题"' in frontmatter
    assert "source_url" not in frontmatter
    assert "platform" not in frontmatter
    assert "author" not in frontmatter
    assert 'template: "通用结构化笔记"' in frontmatter
    assert 'transcript_source: "faster_whisper"' in frontmatter


def test_render_frontmatter_quotes_safely_without_dependencies() -> None:
    values = {
        "title": '带"引号"和\\反斜杠\n与换行',
        "source_url": "https://example.com/a?b=1&c=2",
        "platform": "bilibili",
        "author": None,
        "created_at": "2026-10-04T12:00:00+00:00",
        "template": "模板",
        "transcript_source": "faster_whisper",
    }
    frontmatter = note_templates.render_frontmatter(values)
    assert '\\"引号\\"' in frontmatter
    assert "\\\\反斜杠" in frontmatter
    assert "\n与换行" not in frontmatter  # 换行被转义成 \n 序列，保持单行安全
    for line in frontmatter.splitlines():
        assert line == line.strip()


def test_render_frontmatter_escapes_tabs_and_control_characters() -> None:
    """制表符与控制字符必须被转义成 YAML 双引号标量里的安全序列，结果仍可通过 YAML 解析回来。"""
    values = {
        "title": "有\t制表符\x07控制符",
        "source_url": None,
        "platform": None,
        "author": None,
        "created_at": "2026-10-04T12:00:00+00:00",
        "template": "模板",
        "transcript_source": "faster_whisper",
    }
    frontmatter = note_templates.render_frontmatter(values)
    assert "\t" not in frontmatter.replace("\\t", "")
    assert "\x07" not in frontmatter
    assert "\\t" in frontmatter
    assert "\\u0007" in frontmatter
    parsed = note_templates.json.loads(
        frontmatter.splitlines()[1].split(": ", 1)[1]
    )
    assert parsed == values["title"]


def test_render_frontmatter_is_valid_yaml_for_unicode_control_characters() -> None:
    """回归：U+0085/U+007F 等字符在 JSON 里是合法字面量，在 YAML 里会被当成换行或直接报错；

    frontmatter 必须对它们转义，且整块能被真正的 YAML 解析器原样读回。
    """
    yaml = pytest.importorskip("yaml")
    values = {
        "title": "前\x07后\x85尾",
        "source_url": "https://example.com/\x7fx",
        "platform": "bilibili",
        "author": None,
        "created_at": "2026-10-04T12:00:00+00:00",
        "template": "模板\u2028名字",
        "transcript_source": "faster_whisper",
    }
    lines = note_templates.render_frontmatter(values).splitlines()
    assert lines[0] == "---" and lines[-1] == "---"
    parsed = yaml.safe_load("\n".join(lines[1:-1]))
    assert parsed == {key: value for key, value in values.items() if value}

# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------

def test_template_api_lists_builtins_and_supports_crud(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    client = TestClient(main.app)

    listed = client.get("/api/note-templates")
    assert listed.status_code == 200
    templates = listed.json()["templates"]
    assert len(templates) == 4
    assert all("layout" in item and "instructions" in item for item in templates)

    created = client.post(
        "/api/note-templates",
        json={
            "name": "API 模板",
            "description": "d",
            "instructions": "i",
            "layout": "# {{title}}\n\n{{content}}",
        },
    )
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["version"] == 1
    assert created_body["built_in"] is False

    updated = client.put(
        f"/api/note-templates/{created_body['id']}",
        json={"layout": "# {{title}}\n\n{{content}}\n\n尾部"},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    deleted = client.delete(f"/api/note-templates/{created_body['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    remaining = client.get("/api/note-templates").json()["templates"]
    assert len(remaining) == 4


def test_template_api_rejects_invalid_layout_with_stable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    client = TestClient(main.app)
    response = client.post(
        "/api/note-templates", json={"name": "坏", "layout": "# {{title}}"}
    )
    assert response.status_code == 400
    assert "必须包含且只能包含一个" in response.json()["detail"]


def test_template_api_builtins_cannot_be_changed_or_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    client = TestClient(main.app)
    changed = client.put(
        f"/api/note-templates/{GENERAL_TEMPLATE_ID}", json={"name": "改名"}
    )
    assert changed.status_code == 400
    assert "内置模板" in changed.json()["detail"]
    deleted = client.delete(f"/api/note-templates/{CORNELL_TEMPLATE_ID}")
    assert deleted.status_code == 400
    assert "内置模板" in deleted.json()["detail"]


def test_template_api_unknown_ids_are_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    client = TestClient(main.app)
    assert client.put("/api/note-templates/custom-nope", json={"name": "x"}).status_code == 404
    assert client.delete("/api/note-templates/custom-nope").status_code == 404


# ---------------------------------------------------------------------------
# 任务集成：提交时解析与快照、指令进入 summarizer、复用转录换模板
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_submit_resolves_and_snapshots_template_into_task_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(main.config_store, "load_bili_credentials", lambda: None)
    store = main.get_template_store()
    custom = store.create(
        name="快照模板",
        description="d",
        instructions="按访谈整理",
        layout="# {{title}}\n\n{{content}}\n\n—— 完 ——",
    )
    request = main.SummarizeRequest(
        video_url="https://www.bilibili.com/video/BV1xx",
        note_template_id=custom.id,
        llm_config=main.LLMConfig(model_type="deepseek", api_key="test-key"),
    )
    submitted = await main.submit_video_task(request, origin="web")
    task_id = submitted["task_id"]
    # 后台任务一经调度立即取消：本测试只验证提交时解析与落盘，不触发任何平台/网络访问
    job = main.running_jobs.get(task_id)
    if job is not None:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)

    manifest = json.loads((tmp_path / task_id / "task.json").read_text(encoding="utf-8"))
    assert manifest["note_template"] == {"id": custom.id, "version": 1}
    snapshot = manifest["note_template_snapshot"]
    assert snapshot["id"] == custom.id
    assert snapshot["version"] == 1
    assert snapshot["layout"] == custom.layout
    assert snapshot["instructions"] == "按访谈整理"

    # 之后的修改与删除不能改写已提交任务的快照
    store.update(custom.id, layout="# {{title}}\n\n{{content}}\n\n改过")
    store.delete(custom.id)
    manifest_again = json.loads(
        (tmp_path / task_id / "task.json").read_text(encoding="utf-8")
    )
    assert manifest_again["note_template_snapshot"]["layout"] == custom.layout
    assert manifest_again["note_template"]["version"] == 1


@pytest.mark.asyncio
async def test_submit_rejects_unknown_template_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import HTTPException

    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    request = main.SummarizeRequest(
        video_url="https://www.bilibili.com/video/BV1xx",
        note_template_id="custom-missing",
        llm_config=main.LLMConfig(model_type="deepseek", api_key="test-key"),
    )
    with pytest.raises(HTTPException) as excinfo:
        await main.submit_video_task(request, origin="web")
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_submit_without_template_id_snapshots_general_builtin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """回归：普通笔记提交不传模板 ID 时解析为通用内置模板，而不是拿空串查库返回 404。"""
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(main.config_store, "load_bili_credentials", lambda: None)
    for template_id in (None, "", "   "):
        request = main.SummarizeRequest(
            video_url="https://www.bilibili.com/video/BV1xx",
            note_template_id=template_id,
            llm_config=main.LLMConfig(model_type="deepseek", api_key="test-key"),
        )
        submitted = await main.submit_video_task(request, origin="web")
        task_id = submitted["task_id"]
        job = main.running_jobs.get(task_id)
        if job is not None:
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)
        manifest = json.loads(
            (tmp_path / task_id / "task.json").read_text(encoding="utf-8")
        )
        assert manifest["note_template"]["id"] == GENERAL_TEMPLATE_ID
        assert manifest["note_template_snapshot"]["built_in"] is True


@pytest.mark.asyncio
async def test_template_instructions_reach_summarizer_and_layout_is_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模板指令作为组织指导进入现有 summarizer 调用；summary_style 保持独立。"""
    old_task_id = "tpl-old-task"
    new_task_id = "tpl-new-task"
    old_dir = tmp_path / old_task_id
    old_dir.mkdir()
    (tmp_path / new_task_id).mkdir()
    (old_dir / "transcript.json").write_text(
        '{"language":"zh","source":"faster_whisper","segments":'
        '[{"start":0,"end":12,"text":"这是一段原始内容"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    store = main.get_template_store()
    custom = store.create(
        name="访谈模板",
        description="d",
        instructions="按发言人整理观点",
        layout="# {{title}}\n\n## 观点\n\n{{content}}\n\n## 出处\n\n{{platform}} · {{author}}",
    )

    async def forbidden(*args, **kwargs):
        raise AssertionError("reuse path must not call the platform or Whisper")

    class FakeProcessor:
        @staticmethod
        def detect_source(*args, **kwargs):
            return main.VideoSource.BILIBILI

        get_video_info = forbidden
        fetch_subtitles = forbidden
        download_audio = forbidden

    seen: dict[str, object] = {}

    class FakeSummarizer:
        def __init__(self, **kwargs):
            pass

        def describe_effort(self, reasoning_effort: str, style: str) -> str:
            return reasoning_effort

        async def generate_summary(
            self, title, segments, metadata, style="detailed", reasoning_effort="auto",
            progress_callback=None, should_abort=None, organization_instructions="",
        ):
            seen["style"] = style
            seen["organization_instructions"] = organization_instructions
            return "# 草稿\n\n正文内容"

    monkeypatch.setattr(main, "video_processor", FakeProcessor())
    monkeypatch.setattr(main, "transcriber", type("T", (), {"transcribe": forbidden})())
    monkeypatch.setattr(main, "LLMSummarizer", FakeSummarizer)
    main.tasks[new_task_id] = main.new_task()
    main.tasks[new_task_id]["resume_task_id"] = old_task_id
    request = main.SummarizeRequest(
        video_url="https://www.bilibili.com/video/BV1xx",
        note_template_id=custom.id,
        summary_style="concise",
        llm_config=main.LLMConfig(model_type="glm", api_key="test-key"),
    )

    await main.process_video_task(new_task_id, request)

    assert seen["style"] == "concise"  # summary_style 不被模板替换
    assert "按发言人整理观点" in seen["organization_instructions"]
    task = main.tasks[new_task_id]
    assert task["status"] == "completed"
    assert task["result"]["note_template_id"] == custom.id
    assert task["result"]["note_template_version"] == 1
    note = (tmp_path / new_task_id / "notes.md").read_text(encoding="utf-8")
    assert note.startswith("---\n")
    assert 'template: "访谈模板"' in note
    assert 'transcript_source: "faster_whisper"' in note
    assert "## 观点" in note
    assert "正文内容" in note
    assert "## 出处" in note
    assert note.rstrip().endswith("---") is False  # 页脚仍跟在正文之后
    assert "来源：https://www.bilibili.com/video/BV1xx" in note
    assert "笔记风格：精简摘要" in note


@pytest.mark.asyncio
async def test_deleted_custom_template_still_renders_queued_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """任务入队后删除模板：处理时仍用提交时的快照，任务不失败。"""
    old_task_id = "del-old-task"
    new_task_id = "del-new-task"
    old_dir = tmp_path / old_task_id
    old_dir.mkdir()
    (tmp_path / new_task_id).mkdir()
    (old_dir / "transcript.json").write_text(
        '{"language":"zh","source":"faster_whisper","segments":'
        '[{"start":0,"end":12,"text":"内容"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    store = main.get_template_store()
    custom = store.create(
        name="将被删除",
        description="d",
        instructions="i",
        layout="# {{title}}\n\n{{content}}\n\n删除后仍在",
    )
    # 提交时落盘快照
    request = main.SummarizeRequest(
        video_url="https://www.bilibili.com/video/BV1xx",
        note_template_id=custom.id,
        llm_config=main.LLMConfig(model_type="glm", api_key="test-key"),
    )
    submitted = await main.submit_video_task(request, origin="web")
    submitted_id = submitted["task_id"]
    # 立即取消后台任务，避免它真的去访问平台；快照此时已经落盘
    job = main.running_jobs.get(submitted_id)
    if job is not None:
        job.cancel()
        await asyncio.gather(job, return_exceptions=True)
    store.delete(custom.id)

    async def forbidden(*args, **kwargs):
        raise AssertionError("reuse path must not call the platform or Whisper")

    class FakeProcessor:
        @staticmethod
        def detect_source(*args, **kwargs):
            return main.VideoSource.BILIBILI

        get_video_info = forbidden
        fetch_subtitles = forbidden
        download_audio = forbidden

    class FakeSummarizer:
        def __init__(self, **kwargs):
            pass

        def describe_effort(self, reasoning_effort: str, style: str) -> str:
            return reasoning_effort

        async def generate_summary(self, *args, **kwargs):
            return "# 草稿"

    monkeypatch.setattr(main, "video_processor", FakeProcessor())
    monkeypatch.setattr(main, "transcriber", type("T", (), {"transcribe": forbidden})())
    monkeypatch.setattr(main, "LLMSummarizer", FakeSummarizer)
    main.tasks[submitted_id]["resume_task_id"] = old_task_id

    await main.process_video_task(submitted_id, request)

    task = main.tasks[submitted_id]
    assert task["status"] == "completed"
    assert task["result"]["note_template_id"] == custom.id
    note = (tmp_path / submitted_id / "notes.md").read_text(encoding="utf-8")
    assert "删除后仍在" in note


@pytest.mark.asyncio
async def test_reuse_with_different_template_preserves_archived_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一转录换模板重新生成：跳过平台/ASR，产生新的防撞名笔记，旧笔记原样保留。"""
    old_task_id = "reuse-old-task"
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    old_dir = tmp_path / old_task_id
    old_dir.mkdir()
    (old_dir / "transcript.json").write_text(
        '{"language":"zh","source":"platform_subtitle","segments":'
        '[{"start":0,"end":12,"text":"原始内容"}]}',
        encoding="utf-8",
    )
    # 第一次：默认通用模板
    first_task_id = "reuse-first"
    (tmp_path / first_task_id).mkdir()
    await _run_reuse_task(
        tmp_path, monkeypatch, old_task_id, first_task_id, template_id=None
    )
    assert main.tasks[first_task_id]["status"] == "completed"
    first_note = (tmp_path / first_task_id / "notes.md").read_text(encoding="utf-8")
    assert 'template: "通用结构化笔记"' in first_note

    # 第二次：康奈尔模板；平台与转写一律不允许再被调用
    second_task_id = "reuse-second"
    (tmp_path / second_task_id).mkdir()

    async def forbidden(*args, **kwargs):
        raise AssertionError("reuse with another template must not call platform or Whisper")

    class ForbiddenProcessor:
        @staticmethod
        def detect_source(*args, **kwargs):
            return main.VideoSource.BILIBILI

        get_video_info = forbidden
        fetch_subtitles = forbidden
        download_audio = forbidden

    seen_kwargs: dict[str, object] = {}

    class FakeSummarizer:
        def __init__(self, **kwargs):
            pass

        def describe_effort(self, reasoning_effort: str, style: str) -> str:
            return reasoning_effort

        async def generate_summary(self, *args, **kwargs):
            seen_kwargs["organization_instructions"] = kwargs.get("organization_instructions", "")
            return "# 第二次草稿\n\n[00:00] 要点"

    monkeypatch.setattr(main, "video_processor", ForbiddenProcessor())
    monkeypatch.setattr(main, "transcriber", type("T", (), {"transcribe": forbidden})())
    monkeypatch.setattr(main, "LLMSummarizer", FakeSummarizer)
    main.tasks[second_task_id] = main.new_task()
    main.tasks[second_task_id]["resume_task_id"] = old_task_id
    second_request = main.SummarizeRequest(
        video_url="https://www.bilibili.com/video/BV1xx",
        note_template_id=CORNELL_TEMPLATE_ID,
        llm_config=main.LLMConfig(model_type="glm", api_key="test-key"),
    )
    await main.process_video_task(second_task_id, second_request)

    assert main.tasks[second_task_id]["status"] == "completed"
    assert any("跳过字幕、音频和 Whisper" in log for log in main.tasks[second_task_id]["logs"])
    second_note = (tmp_path / second_task_id / "notes.md").read_text(encoding="utf-8")
    assert 'template: "康奈尔复习笔记"' in second_note
    assert "[00:00] 要点" in second_note
    # 康奈尔的分区组织通过整理指令进入摘要管线（布局只是文档外壳）
    assert "康奈尔" in seen_kwargs["organization_instructions"]

    # 归档：两篇笔记都在 workspace/notes，同名时后者拿到 -2 后缀，前者一字未改
    archived = sorted((tmp_path / "notes").glob("*.md"))
    assert len(archived) == 2
    archived_texts = [path.read_text(encoding="utf-8") for path in archived]
    assert any("通用结构化笔记" in text for text in archived_texts)
    assert any("康奈尔复习笔记" in text for text in archived_texts)
    first_archived = next(
        text for text in archived_texts if "通用结构化笔记" in text
    )
    assert first_archived == (tmp_path / first_task_id / "notes.md").read_text(
        encoding="utf-8"
    ).replace(f"../{first_task_id}/", "")


async def _run_reuse_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old_task_id: str,
    task_id: str,
    template_id: str | None,
) -> None:
    async def fake_info(*args, **kwargs):
        return {"title": "标题", "source": "bilibili", "duration": 12, "owner": "作者"}

    class FakeProcessor:
        @staticmethod
        def detect_source(*args, **kwargs):
            return main.VideoSource.BILIBILI

        get_video_info = staticmethod(fake_info)
        fetch_subtitles = staticmethod(fake_info)

        @staticmethod
        async def download_audio(*args, **kwargs):
            raise AssertionError("must not download on reuse")

    class FakeTranscriber:
        @staticmethod
        async def transcribe(*args, **kwargs):
            raise AssertionError("must not transcribe on reuse")

    class FakeSummarizer:
        def __init__(self, **kwargs):
            pass

        def describe_effort(self, reasoning_effort: str, style: str) -> str:
            return reasoning_effort

        async def generate_summary(self, *args, **kwargs):
            return "# 第一次草稿\n\n要点"

    monkeypatch.setattr(main, "video_processor", FakeProcessor())
    monkeypatch.setattr(main, "transcriber", FakeTranscriber())
    monkeypatch.setattr(main, "LLMSummarizer", FakeSummarizer)
    main.tasks[task_id] = main.new_task()
    main.tasks[task_id]["resume_task_id"] = old_task_id
    request = main.SummarizeRequest(
        video_url="https://www.bilibili.com/video/BV1xx",
        note_template_id=template_id,
        llm_config=main.LLMConfig(model_type="glm", api_key="test-key"),
    )
    await main.process_video_task(task_id, request)


def test_summarize_request_defaults_to_general_builtin_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "WORKSPACE_DIR", tmp_path)
    request = main.SummarizeRequest(
        llm_config=main.LLMConfig(model_type="deepseek", api_key="k")
    )
    assert request.note_template_id is None  # None → 服务端解析为通用内置模板
    resolved = main.get_template_store().get(
        request.note_template_id or note_templates.DEFAULT_TEMPLATE_ID
    )
    assert resolved.id == GENERAL_TEMPLATE_ID
    assert resolved.built_in
