"""页面背景绘制组件。

承载纯色或图片背景，位于主窗口内容层之下。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

DEFAULT_BACKGROUND = "#0F1115"


def compute_draw_rect(mode: str, image_size: QSize, widget_size: QSize) -> QRect:
    """计算图片在控件内的绘制矩形。

    Args:
        mode: cover / contain / tile。
        image_size: 原图尺寸。
        widget_size: 控件尺寸。

    Returns:
        绘制矩形；cover 时可能大于控件区域（由控件裁剪）。
    """
    if mode == "tile":
        return QRect(0, 0, widget_size.width(), widget_size.height())
    if image_size.isEmpty() or widget_size.isEmpty():
        return QRect()

    scale_x = widget_size.width() / image_size.width()
    scale_y = widget_size.height() / image_size.height()
    scale = max(scale_x, scale_y) if mode == "cover" else min(scale_x, scale_y)

    width = max(1, round(image_size.width() * scale))
    height = max(1, round(image_size.height() * scale))
    x = (widget_size.width() - width) // 2
    y = (widget_size.height() - height) // 2
    return QRect(x, y, width, height)


class BackgroundWidget(QWidget):
    """可绘制纯色 / 图片背景的容器控件。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "default"
        self._color = DEFAULT_BACKGROUND
        self._image_path = ""
        self._fit = "cover"
        self._overlay = 0.0
        self._pixmap = QPixmap()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_appearance(
        self,
        mode: str = "default",
        color: str = DEFAULT_BACKGROUND,
        image_path: str = "",
        fit: str = "cover",
        overlay: float = 0.0,
    ) -> None:
        """更新背景设置并触发重绘。"""
        self._mode = mode if mode in ("default", "color", "image") else "default"
        self._color = color or DEFAULT_BACKGROUND
        self._fit = fit if fit in ("cover", "contain", "tile") else "cover"
        self._overlay = max(0.0, min(1.0, overlay))

        if self._mode == "image" and image_path:
            self._image_path = image_path
            loaded = QPixmap(image_path)
            self._pixmap = loaded if not loaded.isNull() else QPixmap()
        else:
            self._image_path = image_path
            self._pixmap = QPixmap()

        self.update()

    def image_loaded(self) -> bool:
        """图片是否已成功加载（用于测试与降级提示）。"""
        return not self._pixmap.isNull()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(self._color))

        if self._mode == "image" and not self._pixmap.isNull():
            if self._fit == "tile":
                painter.drawTiledPixmap(self.rect(), self._pixmap)
            else:
                rect = compute_draw_rect(self._fit, self._pixmap.size(), self.size())
                painter.drawPixmap(rect, self._pixmap)

            if self._overlay > 0:
                shade = QColor(0, 0, 0)
                shade.setAlphaF(self._overlay)
                painter.fillRect(self.rect(), shade)

        painter.end()
