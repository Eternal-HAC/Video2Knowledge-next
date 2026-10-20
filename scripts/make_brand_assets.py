"""可重复生成 Video2Knowledge 原创品牌资产（只依赖已有的 Pillow，无第三方素材）。

几何构成（构造规则与取色同时记录在 DESIGN.md「Brand」一节）：

- 圆角方形底：Indigo ``#4F46E5`` → Cyan ``#0891B2`` 对角渐变，圆角半径 22%。
- 白色播放三角：代表「视频输入」，指向右侧。
- 三枚知识节点：从三角尖端向右上连出的浅 Cyan 圆点（白描边、逐级变小），
  代表视频被沉淀为互相连接的知识点。

输出（均被 Git 跟踪，可被本脚本完全重建）：

- ``sources/icon.png``  1024×1024 RGBA，供网页 ``/icon.png`` 与品牌位使用
- ``sources/icon.ico``  复用 ``scripts/make_icon.py`` 的多尺寸 ICO 构造（16–256）

用法：``python scripts/make_brand_assets.py``
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

# 复用同目录 make_icon.py 的 ICO 构造（多尺寸、256 帧 PNG 编码、小帧 32bit BMP）。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_icon  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
PNG_PATH = BASE_DIR / "sources" / "icon.png"
ICO_PATH = BASE_DIR / "sources" / "icon.ico"

# 品牌色（与 DESIGN.md / frontend/style.css 的 token 一致）
INDIGO = (79, 70, 229)     # #4F46E5
CYAN = (8, 145, 178)       # #0891B2
NODE = (165, 243, 252)     # #A5F3FC（cyan-200，节点填充）
WHITE = (255, 255, 255)

FINAL_SIZE = 1024
SUPERSAMPLE = 4  # 4 倍超采样绘制再 LANCZOS 缩小，边缘抗锯齿且结果确定

# 以下几何全部是相对画布边长的比例（0–1），构造含义见模块 docstring
CORNER_RADIUS = 0.22
TRIANGLE = [(0.30, 0.28), (0.30, 0.72), (0.66, 0.50)]
NODE_PATH = [(0.66, 0.50), (0.72, 0.42), (0.81, 0.33), (0.90, 0.245)]
NODE_RADII = [0.046, 0.037, 0.028]
NODE_LINE_WIDTH = 0.016
NODE_RING_WIDTH = 0.009


def _scale(points: list[tuple[float, float]], size: int) -> list[tuple[float, float]]:
    return [(x * size, y * size) for x, y in points]


def _diagonal_gradient(size: int, start: tuple[int, int, int], end: tuple[int, int, int]) -> Image.Image:
    """start（左上）→ end（右下）的对角线性渐变。

    先把竖直渐变放大旋转 45°，再中心裁回原尺寸：裁切区恰好是旋转后
    菱形的内接正方形，因此边缘不会出现填充色接缝。
    """
    ramp = Image.linear_gradient("L").resize((size, size), Image.Resampling.BILINEAR)
    ramp = ramp.rotate(45, resample=Image.Resampling.BICUBIC, expand=True)
    left = (ramp.width - size) // 2
    top = (ramp.height - size) // 2
    ramp = ramp.crop((left, top, left + size, top + size))
    return Image.composite(
        Image.new("RGB", (size, size), end),
        Image.new("RGB", (size, size), start),
        ramp,
    )


def render_mark(size: int = FINAL_SIZE) -> Image.Image:
    """按固定几何规则绘制标志，返回 RGBA 图像；同一 size 下输出逐像素确定。"""
    canvas = size * SUPERSAMPLE

    base = _diagonal_gradient(canvas, INDIGO, CYAN)
    mask = Image.new("L", (canvas, canvas), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [0, 0, canvas - 1, canvas - 1], radius=int(CORNER_RADIUS * canvas), fill=255
    )

    mark = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    mark.paste(base, (0, 0), mask)

    draw = ImageDraw.Draw(mark)
    # 播放三角：视频输入
    draw.polygon(_scale(TRIANGLE, canvas), fill=WHITE)
    # 知识节点连线：从三角尖端向右上生长
    draw.line(
        _scale(NODE_PATH, canvas),
        fill=NODE,
        width=max(1, int(NODE_LINE_WIDTH * canvas)),
        joint="curve",
    )
    for (cx, cy), radius in zip(_scale(NODE_PATH[1:], canvas), NODE_RADII):
        r = radius * canvas
        ring = NODE_RING_WIDTH * canvas
        draw.ellipse(
            [cx - r - ring, cy - r - ring, cx + r + ring, cy + r + ring], fill=WHITE
        )
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=NODE)

    return mark.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    image = render_mark(FINAL_SIZE)
    image.save(PNG_PATH)
    print(f"已生成: {PNG_PATH}（{FINAL_SIZE}x{FINAL_SIZE} RGBA）")

    frames = [
        (size, image.resize((size, size), Image.Resampling.LANCZOS))
        for size in make_icon.SIZES
    ]
    ICO_PATH.write_bytes(make_icon.build_ico(frames))
    print(f"已生成: {ICO_PATH}（{len(make_icon.SIZES)} 个尺寸: "
          + "/".join(str(size) for size in make_icon.SIZES) + "）")


if __name__ == "__main__":
    main()
