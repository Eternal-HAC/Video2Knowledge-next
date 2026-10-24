"""Video2Knowledge 产品元数据的唯一来源。

launcher、backend、构建脚本（scripts/build_exe.ps1）与发布流程
（.github/workflows/release.yml）都从这里读产品名与版本号，避免各处散落一份
会漂移的常量。本模块只依赖标准库，且不得 import launcher / backend——
是它们 import 本模块，反向会造成循环；PyInstaller 也会顺着 import 把它打进
onefile 产物，无需额外的 --add-data。
"""

from __future__ import annotations

import os
import re

# 面向用户的新品牌：启动器标题、托盘提示、后端页面、构建产物名都以此为准
PRODUCT_NAME = "Video2Knowledge"
# 旧服务 ID：/api/health 的 service 字段继续原样返回它，既有启动器 / MCP /
# Skill 的发现逻辑因此仍能认出改名后的服务
LEGACY_SERVICE_ID = "VideoToNo"
VERSION = "1.0.0-beta.4"
# 健康接口兼容级别：只加字段不 bump，破坏旧字段语义时才 +1
API_COMPAT = 1
GITHUB_REPO = "Eternal-HAC/Video2Knowledge-next"
APP_NAME = f"{PRODUCT_NAME} v{VERSION}"

# 环境变量别名：新名（VIDEO2KNOWLEDGE_*）优先，旧名（VIDEOTONOTES_*）继续生效，
# 老脚本与旧版便携版只认识旧名
ENV_PREFIX = "VIDEO2KNOWLEDGE_"
LEGACY_ENV_PREFIX = "VIDEOTONOTES_"


def env_value(name: str, default: str | None = None) -> str | None:
    """按 新名 > 旧名 > default 读取环境变量（name 是 WORKSPACE 这类后缀）。

    判断标准是"是否设置"而不是"是否非空"：新名被显式设成空串时依旧优先，
    由调用方决定空值怎么处理（例如 configure_runtime_dirs 退回默认目录）。
    """
    for prefix in (ENV_PREFIX, LEGACY_ENV_PREFIX):
        key = f"{prefix}{name}"
        if key in os.environ:
            return os.environ[key]
    return default


def set_env_aliases(name: str, value: str) -> None:
    """把解析出的值同步写进两个名字，让下游进程拿到同一份配置。

    不能用 setdefault：旧名若还留着上一个解析周期的值，两个名字会各说各话，
    backend / ASR 子进程按新名优先读到的和 launcher 解析出的就不是同一份。
    """
    os.environ[f"{ENV_PREFIX}{name}"] = value
    os.environ[f"{LEGACY_ENV_PREFIX}{name}"] = value


# ---------------------------------------------------------------------------
# 版本排序
# ---------------------------------------------------------------------------
# 两条版本线：
#   过渡线 v1.4.2-v2k.N（沿用上游主版本号 + successor 后缀）——整体低于独立线
#   独立线 v1.0.0-beta.N → v1.0.0-rc.N → v1.0.0（同号段内 beta < rc < stable）
# 无法识别的版本号返回最小键：它作为远端版本时永远不会被判成"有更新"。

_NUMERIC_WIDTH = 4
_TRANSITION_RE = re.compile(r"^(\d+(?:\.\d+)*)-v2k\.(\d+)$", re.IGNORECASE)
_INDEPENDENT_RE = re.compile(r"^(\d+(?:\.\d+)*)(?:-(beta|rc)\.?(\d+))?$", re.IGNORECASE)
_STAGE_ORDER = {"beta": 1, "rc": 2, "": 3}
INVALID_VERSION_KEY = (-1, (0, 0, 0, 0), 0, 0)


def _numeric_parts(text: str) -> tuple[int, ...] | None:
    parts = text.split(".")
    if len(parts) > _NUMERIC_WIDTH:
        return None
    try:
        numbers = tuple(int(part) for part in parts)
    except ValueError:
        return None
    return numbers + (0,) * (_NUMERIC_WIDTH - len(numbers))


def version_key(value: object) -> tuple[int, tuple[int, ...], int, int]:
    """把版本字符串转成可比较元组；无法识别时返回 INVALID_VERSION_KEY。"""
    text = str(value or "").strip().lstrip("vV")
    if not text:
        return INVALID_VERSION_KEY
    transition = _TRANSITION_RE.match(text)
    if transition:
        numbers = _numeric_parts(transition.group(1))
        if numbers is None:
            return INVALID_VERSION_KEY
        # line 0：过渡线永远低于独立线，与数字大小无关
        return (0, numbers, 0, int(transition.group(2)))
    independent = _INDEPENDENT_RE.match(text)
    if not independent:
        return INVALID_VERSION_KEY
    numbers = _numeric_parts(independent.group(1))
    if numbers is None:
        return INVALID_VERSION_KEY
    stage = _STAGE_ORDER[(independent.group(2) or "").lower()]
    stage_num = int(independent.group(3)) if independent.group(3) else 0
    return (1, numbers, stage, stage_num)


def is_update(remote: object, current: object = VERSION) -> bool:
    """remote 是否比 current 新；远端版本无法识别时按"不更新"处理。"""
    remote_key = version_key(remote)
    if remote_key == INVALID_VERSION_KEY:
        return False
    return remote_key > version_key(current)
