"""笔记模板：四个只读内置模板 + 后端持久化的自定义模板 + 确定性渲染。

契约（见 DECISIONS.md「Separate summary strategy from safe note templates」）：

- 布局只接受白名单占位符，且必须恰好包含一个 ``{{content}}``；绝不执行
  Jinja / Python / JavaScript / shell 等任何模板代码。
- 渲染是纯字符串替换：先按布局包一层 LLM 草稿，再确定性生成 YAML Frontmatter，
  不新增任何依赖，也不额外调用大模型。
- 任务提交时把选中模板整体快照落盘（见 backend.main），之后的模板修改或删除
  不影响已排队与历史任务。
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 布局可用的占位符白名单。content 是 LLM 草稿注入点，其余字段来自任务元信息。
ALLOWED_PLACEHOLDERS: tuple[str, ...] = (
    "title",
    "source_url",
    "platform",
    "author",
    "published_at",
    "duration",
    "created_at",
    "transcript_source",
    "template_name",
    "content",
)
_ALLOWED_PLACEHOLDER_SET = frozenset(ALLOWED_PLACEHOLDERS)

GENERAL_TEMPLATE_ID = "builtin-general-structured"
CORNELL_TEMPLATE_ID = "builtin-cornell-review"
TUTORIAL_TEMPLATE_ID = "builtin-tutorial-howto"
INTERVIEW_TEMPLATE_ID = "builtin-interview-viewpoint"
DEFAULT_TEMPLATE_ID = GENERAL_TEMPLATE_ID

# Frontmatter 固定字段顺序；缺失值直接省略。
FRONTMATTER_KEYS: tuple[str, ...] = (
    "title",
    "source_url",
    "platform",
    "author",
    "created_at",
    "template",
    "transcript_source",
)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
# YAML 对 C0/C1 控制字符之外的几个码位也敏感：NEL（U+0085）会被当成换行、
# DEL（U+007F）与其他 C1 控制符会被 PyYAML 的 Reader 直接拒绝，LS/PS 在部分
# 解析器里同样按换行处理。json.dumps 不会转义这些 ≥0x7F 的码位，需要补一道。
_YAML_UNSAFE_RE = re.compile("[\x7f-\x9f\u2028\u2029]")
# 可执行模板语法黑名单：Jinja 语句/注释、shell/JS 插值、ERB、Blade 原始块。
_EXECUTABLE_PATTERNS = (
    re.compile(r"\{%.*?%\}", re.S),
    re.compile(r"\{#.*?#\}", re.S),
    re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_.]*\}"),
    re.compile(r"<%.*?%>", re.S),
    re.compile(r"\{!!.*?!!\}", re.S),
)

_LAYOUT_REQUIRED_CONTENT = "布局必须包含且只能包含一个 {{content}} 占位符"
_LAYOUT_UNKNOWN_PLACEHOLDER = "布局包含不支持的占位符"
_LAYOUT_MALFORMED_PLACEHOLDER = "布局包含无法识别的占位符写法（占位符格式为 {{名称}}）"
_LAYOUT_EXECUTABLE = "布局包含不允许的可执行模板语法（仅支持占位符替换，不支持脚本或模板引擎）"
_LAYOUT_EMPTY = "笔记布局不能为空"
_NAME_EMPTY = "模板名称不能为空"
_BUILTIN_IMMUTABLE = "内置模板不可修改或删除"
_TEMPLATE_NOT_FOUND = "笔记模板不存在"
_UPDATE_EMPTY = "没有需要更新的字段"

# 字段长度上限：模板要整体快照进每个任务的 task.json，无界输入会放大落盘体积。
MAX_NAME_LENGTH = 80
MAX_DESCRIPTION_LENGTH = 300
MAX_INSTRUCTIONS_LENGTH = 4000
MAX_LAYOUT_LENGTH = 8000

# 自定义模板 ID 只允许 create() 生成的形态：custom- 前缀 + 12 位小写十六进制。
# 加载磁盘文件时按这个形态重校验，顺带挡住路径分隔符等异常字符。
_CUSTOM_ID_RE = re.compile("^custom-[0-9a-f]{12}$")


class TemplateError(Exception):
    """模板子系统的统一基类。"""


class TemplateValidationError(TemplateError, ValueError):
    """布局或名称不合法；报错文案保持稳定，直接展示给用户。"""


class TemplateNotFoundError(TemplateError, KeyError):
    """模板 ID 不存在。"""


class TemplateImmutableError(TemplateError, PermissionError):
    """尝试修改或删除内置模板。"""


def validate_layout(layout: str) -> str:
    """校验布局并返回规范化版本（占位符统一写成 {{name}}）。

    校验顺序刻意固定：可执行语法 → 未知占位符 → 残缺写法 → content 唯一性，
    保证同一布局永远得到同一条报错。
    """
    if not isinstance(layout, str) or not layout.strip():
        raise TemplateValidationError(_LAYOUT_EMPTY)
    text = layout.replace("\r\n", "\n")
    for pattern in _EXECUTABLE_PATTERNS:
        if pattern.search(text):
            raise TemplateValidationError(_LAYOUT_EXECUTABLE)
    unknown: list[str] = []
    content_count = 0
    for match in _PLACEHOLDER_RE.finditer(text):
        name = match.group(1).strip()
        if name == "content":
            content_count += 1
        elif name not in _ALLOWED_PLACEHOLDER_SET:
            unknown.append(name)
    if unknown:
        allowed = "、".join(ALLOWED_PLACEHOLDERS)
        raise TemplateValidationError(
            f"{_LAYOUT_UNKNOWN_PLACEHOLDER}：{'、'.join(sorted(set(unknown)))}"
            f"（仅支持：{allowed}）"
        )
    stripped = _PLACEHOLDER_RE.sub("", text)
    if "{{" in stripped or "}}" in stripped:
        raise TemplateValidationError(_LAYOUT_MALFORMED_PLACEHOLDER)
    if content_count != 1:
        raise TemplateValidationError(_LAYOUT_REQUIRED_CONTENT)
    return _PLACEHOLDER_RE.sub(lambda m: "{{" + m.group(1).strip() + "}}", text)


def _validate_length(label: str, value: str, limit: int) -> None:
    if len(value) > limit:
        raise TemplateValidationError(f"{label}过长（最多 {limit} 字符）")


def _validate_stored_custom(data: dict[str, Any], stem: str) -> NoteTemplate:
    """重校验从磁盘读出的自定义模板；任何字段不合法都抛错，由调用方隔离。

    与 create()/update() 走同一套长度与布局校验，外加只有持久化文件才有的
    约束：id 与文件名一致、version 是真正的正整数（bool 不算）、built_in
    必须显式为 false。不做任何静默修复或改写。
    """
    template_id = data.get("id")
    if (
        not isinstance(template_id, str)
        or template_id != stem
        or not _CUSTOM_ID_RE.fullmatch(template_id)
    ):
        raise TemplateValidationError("自定义模板 ID 不合法或与文件名不一致")
    if data.get("built_in") is not False:
        raise TemplateValidationError("自定义模板 built_in 必须为 false")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise TemplateValidationError(_NAME_EMPTY)
    _validate_length("模板名称", name.strip(), MAX_NAME_LENGTH)
    description = data.get("description", "")
    instructions = data.get("instructions", "")
    if not isinstance(description, str) or not isinstance(instructions, str):
        raise TemplateValidationError("模板说明与整理指令必须是字符串")
    _validate_length("模板说明", description, MAX_DESCRIPTION_LENGTH)
    _validate_length("整理指令", instructions, MAX_INSTRUCTIONS_LENGTH)
    layout = data.get("layout")
    if not isinstance(layout, str):
        raise TemplateValidationError(_LAYOUT_EMPTY)
    _validate_length("笔记布局", layout, MAX_LAYOUT_LENGTH)
    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise TemplateValidationError("模板版本必须是正整数")
    return NoteTemplate(
        id=template_id,
        name=name.strip(),
        description=description,
        instructions=instructions,
        layout=validate_layout(layout),
        version=version,
        built_in=False,
    )


@dataclass
class NoteTemplate:
    id: str
    name: str
    description: str
    instructions: str
    layout: str
    version: int = 1
    built_in: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "layout": self.layout,
            "version": self.version,
            "built_in": self.built_in,
        }

    def snapshot(self) -> dict[str, Any]:
        """提交任务时落盘的不可变快照：包含布局与指令全文。"""
        return self.to_dict()


def _builtin_templates() -> list[NoteTemplate]:
    """每次调用构造新实例：内置模板对调用方是不可变的。"""
    return [
        NoteTemplate(
            id=GENERAL_TEMPLATE_ID,
            name="通用结构化笔记",
            description="默认模板：按内容自然组织，保留时间轴要点与元信息。",
            instructions=(
                "按视频内容的时间顺序组织笔记，保留关键论点、例子与时间点；"
                "不补充外部知识，结构与详略以内容为准。"
            ),
            layout="# 视频笔记：《{{title}}》\n\n{{content}}",
            version=1,
            built_in=True,
        ),
        NoteTemplate(
            id=CORNELL_TEMPLATE_ID,
            name="康奈尔复习笔记",
            description="康奈尔笔记法：笔记区 + 线索区 + 总结区，便于自测复习。",
            instructions=(
                "按康奈尔笔记法整理：主体按主题归纳要点（笔记区），"
                "并为每个主题给出可以自测的提示线索（线索区）；结构与详略以内容为准。"
            ),
            # 布局只是文档外壳：分区由整理指令让模型写进正文，避免无填充路径的空分区
            layout="# {{title}}\n\n{{content}}",
            version=1,
            built_in=True,
        ),
        NoteTemplate(
            id=TUTORIAL_TEMPLATE_ID,
            name="教程 / 操作指南笔记",
            description="面向教程与 how-to 内容：目标概述、操作步骤与常见问题。",
            instructions=(
                "把内容整理成可照着做的步骤笔记：先概述目标，"
                "再按顺序列出操作步骤与注意事项，最后给出常见问题和易错点。"
            ),
            layout="# {{title}}\n\n{{content}}",
            version=1,
            built_in=True,
        ),
        NoteTemplate(
            id=INTERVIEW_TEMPLATE_ID,
            name="访谈 / 观点分析笔记",
            description="面向访谈、对话与观点输出：核心观点、论据与值得引用的表述。",
            instructions=(
                "整理访谈或观点类内容：按发言人或主题归纳核心观点与论据，"
                "保留有信息量的原话表述并标注时间点。"
            ),
            layout="# {{title}}\n\n{{content}}",
            version=1,
            built_in=True,
        ),
    ]


class TemplateStore:
    """内置模板 + 工作区内 JSON 文件持久化的自定义模板。"""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _custom_path(self, template_id: str) -> Path:
        safe = Path(template_id).name
        return self.directory / f"{safe}.json"

    def list_templates(self) -> list[NoteTemplate]:
        customs: list[NoteTemplate] = []
        for path in sorted(self.directory.glob("*.json")):
            template = self._load_custom(path)
            if template is not None:
                customs.append(template)
        customs.sort(key=lambda item: (item.name, item.id))
        return _builtin_templates() + customs

    def get(self, template_id: str) -> NoteTemplate | None:
        for template in _builtin_templates():
            if template.id == template_id:
                return template
        path = self._custom_path(template_id)
        if not path.is_file():
            return None
        return self._load_custom(path)

    def _load_custom(self, path: Path) -> NoteTemplate | None:
        """读取单个自定义模板文件；语法或 schema 有任何损坏都返回 None。

        只隔离不改写：损坏文件原样留在磁盘上，列表与按 id 查询都跳过它。
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        try:
            return _validate_stored_custom(data, path.stem)
        except TemplateValidationError:
            return None

    def create(
        self,
        *,
        name: str,
        layout: str,
        description: str = "",
        instructions: str = "",
    ) -> NoteTemplate:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise TemplateValidationError(_NAME_EMPTY)
        _validate_length("模板名称", cleaned_name, MAX_NAME_LENGTH)
        _validate_length("模板说明", description or "", MAX_DESCRIPTION_LENGTH)
        _validate_length("整理指令", instructions or "", MAX_INSTRUCTIONS_LENGTH)
        _validate_length("笔记布局", layout or "", MAX_LAYOUT_LENGTH)
        template = NoteTemplate(
            id=f"custom-{uuid.uuid4().hex[:12]}",
            name=cleaned_name,
            description=description or "",
            instructions=instructions or "",
            layout=validate_layout(layout),
            version=1,
            built_in=False,
        )
        self._save(template)
        return template

    def update(
        self,
        template_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        layout: str | None = None,
    ) -> NoteTemplate:
        template = self.get(template_id)
        if template is None:
            raise TemplateNotFoundError(_TEMPLATE_NOT_FOUND)
        if template.built_in:
            raise TemplateImmutableError(_BUILTIN_IMMUTABLE)
        if (
            name is None
            and description is None
            and instructions is None
            and layout is None
        ):
            raise TemplateValidationError(_UPDATE_EMPTY)
        if name is not None:
            cleaned_name = name.strip()
            if not cleaned_name:
                raise TemplateValidationError(_NAME_EMPTY)
            _validate_length("模板名称", cleaned_name, MAX_NAME_LENGTH)
            template.name = cleaned_name
        if description is not None:
            _validate_length("模板说明", description, MAX_DESCRIPTION_LENGTH)
            template.description = description
        if instructions is not None:
            _validate_length("整理指令", instructions, MAX_INSTRUCTIONS_LENGTH)
            template.instructions = instructions
        if layout is not None:
            _validate_length("笔记布局", layout, MAX_LAYOUT_LENGTH)
            template.layout = validate_layout(layout)
        template.version += 1
        self._save(template)
        return template

    def delete(self, template_id: str) -> None:
        template = self.get(template_id)
        if template is None:
            raise TemplateNotFoundError(_TEMPLATE_NOT_FOUND)
        if template.built_in:
            raise TemplateImmutableError(_BUILTIN_IMMUTABLE)
        self._custom_path(template_id).unlink(missing_ok=True)

    def _save(self, template: NoteTemplate) -> None:
        path = self._custom_path(template.id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(template.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(path)


def apply_layout(layout: str, values: dict[str, Any], content: str) -> str:
    """按布局做纯字符串替换；缺失的占位符值为空字符串。

    单次正则回调只扫描原始布局：已插入的正文或元数据里若含 {{占位符}} 字面量，
    不会被二次解释。
    """
    def substitute(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        if name == "content":
            return content
        value = values.get(name)
        return "" if value is None else str(value)

    return _PLACEHOLDER_RE.sub(substitute, layout)


def render_frontmatter(values: dict[str, Any]) -> str:
    """只输出可用的 Frontmatter 字段，顺序固定，值一律安全加引号。"""
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        value = values.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        # YAML 双引号标量与 JSON 字符串字面量基本同构：先复用 json.dumps 完成
        # 引号、反斜杠、换行、制表符与 C0 控制字符的转义（不新增依赖），再补转
        # json.dumps 原样放行但 YAML 敏感的码位（U+007F-U+009F、U+2028、U+2029）。
        literal = json.dumps(text, ensure_ascii=False)
        literal = _YAML_UNSAFE_RE.sub(
            lambda m: "\\u{:04x}".format(ord(m.group(0))), literal
        )
        lines.append(f"{key}: {literal}")
    lines.append("---")
    return "\n".join(lines)


def render_note(layout: str, values: dict[str, Any], content: str) -> str:
    """确定性渲染：YAML Frontmatter + 布局包裹后的唯一 Markdown 正文。"""
    body = apply_layout(layout, values, content).strip()
    return f"{render_frontmatter(values)}\n{body}\n"
