"""状态指示点控件。

8px 圆形状态指示器，支持脉动动画。
"""

from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from gui.styles.variables import TOKENS_DARK

_STATUS_COLOR_MAP = {
    "indexed": TOKENS_DARK["status-success"],
    "success": TOKENS_DARK["status-success"],
    "indexing": TOKENS_DARK["status-warning"],
    "warning": TOKENS_DARK["status-warning"],
    "pending": TOKENS_DARK["fg-muted"],
    "failed": TOKENS_DARK["status-error"],
    "error": TOKENS_DARK["status-error"],
    "info": TOKENS_DARK["status-info"],
}


class StatusDot(QWidget):
    """8px 圆形状态指示器。

    Args:
        status: 状态键（indexed/indexing/pending/failed/info/success/warning/error）。
        reduce_motion: 是否禁用脉动动画。
        parent: 父控件。
    """

    def __init__(self, status: str = "pending", reduce_motion: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._status = status
        self._reduce_motion = reduce_motion
        self._opacity = 1.0
        self._pulse_animation: QPropertyAnimation | None = None

        if not reduce_motion:
            self._start_pulse_if_needed()

    def _start_pulse_if_needed(self):
        if self._status in ("indexing", "warning"):
            self._pulse_animation = QPropertyAnimation(self, b"opacity")
            self._pulse_animation.setDuration(1500)
            self._pulse_animation.setStartValue(1.0)
            self._pulse_animation.setKeyValueAt(0.5, 0.3)
            self._pulse_animation.setEndValue(1.0)
            self._pulse_animation.setLoopCount(-1)
            self._pulse_animation.start()

    def _stop_pulse(self):
        if self._pulse_animation:
            self._pulse_animation.stop()
            self._pulse_animation = None
        self._opacity = 1.0
        self.update()

    @Property(float)
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, value: float):
        self._opacity = value
        self.update()

    def set_status(self, status: str):
        self._status = status
        self._stop_pulse()
        if not self._reduce_motion:
            self._start_pulse_if_needed()
        self.update()

    def get_color(self) -> QColor:
        color_str = _STATUS_COLOR_MAP.get(self._status, TOKENS_DARK["fg-muted"])
        return QColor(color_str)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = self.get_color()
        color.setAlphaF(self._opacity)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 8, 8)
        painter.end()