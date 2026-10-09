"""媒体清理测试的跨平台断言 helper。

Windows 用已验证句柄做原子身份删除；其它平台按实现保守保留媒体并返回固定
脱敏 warning。清理结果断言统一走这里，通用筛选测试因此保持跨平台一致。
"""
from __future__ import annotations

import os
from pathlib import Path

from backend.media_retention import WARNING_MEDIA_DELETE

IS_WINDOWS = os.name == "nt"


def assert_media_removed(path: Path, message: str = "") -> None:
    if IS_WINDOWS:
        assert not path.exists(), message or f"Windows 应删除 {path.name}"
    else:
        assert path.exists(), f"非 Windows 平台必须保留 {path.name}"


def assert_removed_count(result: dict, *, windows: int) -> None:
    if IS_WINDOWS:
        assert result["removed_count"] == windows
        return
    assert result["removed_count"] == 0, "非 Windows 平台必须保留全部媒体"
    assert WARNING_MEDIA_DELETE in result["warnings"], "非 Windows 必须返回固定脱敏 warning"
