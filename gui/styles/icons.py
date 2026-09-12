"""图标系统。

Lucide 风格 SVG 图标（2px 描边、圆角线帽），
通过 `gui/styles/icons/{name}.svg` 模板加载，
渲染时将 {{COLOR}} 占位符替换为具体色值实现动态着色。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICONS_DIR = Path(__file__).parent / "icons"

# 设计文档 2.7 图标映射表
ICON_NAMES = (
    "upload",
    "settings",
    "search",
    "file-text",
    "trash-2",
    "folder",
    "folder-plus",
    "folder-input",
    "tag",
    "tags",
    "refresh-cw",
    "external-link",
)

# 默认前景色（中性灰，深浅主题均可用）
_DEFAULT_COLOR = "#6B7280"


@lru_cache(maxsize=128)
def _render_pixmap(name: str, size: int, color: str) -> QPixmap:
    svg_path = _ICONS_DIR / f"{name}.svg"
    svg = svg_path.read_text(encoding="utf-8").replace("{{COLOR}}", color)

    renderer = QSvgRenderer(svg.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def icon(name: str, size: int = 16, color: str | None = None) -> QIcon:
    """按名称获取图标。

    Args:
        name: 图标名（见 ICON_NAMES）。
        size: 像素尺寸（工具栏 16 / 行内 14 / 空状态 20）。
        color: 十六进制色值；None 用默认中性前景色。

    Returns:
        渲染后的 QIcon；名称不存在时返回空 QIcon。
    """
    if name not in ICON_NAMES:
        return QIcon()
    pixmap = _render_pixmap(name, size, color or _DEFAULT_COLOR)
    return QIcon(pixmap)
