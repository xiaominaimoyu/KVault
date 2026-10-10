"""底部状态栏面板。

替换原 QStatusBar，提供结构化状态显示：状态点 + 文字 + 统计摘要 + 进度条 + Ollama 指示。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QWidget,
)

from gui.widgets.status_dot import StatusDot


class StatusBar(QWidget):
    """底部状态栏，高 32px。

    Methods:
        set_status(text, color_key): 更新状态点颜色与文字。
        set_stats_summary(text): 更新中间统计摘要。
        set_progress(percent, label): 设置进度条值。
        show_progress(visible): 显示/隐藏进度条。
        set_ollama_status(connected): 更新 Ollama 指示。
        show_message(text): 兼容 QStatusBar.showMessage 的便捷方法。
    """

    def __init__(self, reduce_motion: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setObjectName("StatusBar")
        self._reduce_motion = reduce_motion
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self._status_dot = StatusDot("pending", self._reduce_motion, self)
        layout.addWidget(self._status_dot)

        self._status_label = QLabel("就绪")
        self._status_label.setObjectName("StatusMessage")
        layout.addWidget(self._status_label)

        # §3.6 统计摘要：--text-xs 等宽 fg-muted
        self._stats_label = QLabel("")
        self._stats_label.setObjectName("StatusStats")
        self._stats_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._stats_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._ollama_dot = StatusDot("pending", self._reduce_motion, self)
        layout.addWidget(self._ollama_dot)

        self._ollama_label = QLabel("Ollama")
        self._ollama_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._ollama_label)

    def set_status(self, text: str, color_key: str = "pending"):
        self._status_label.setText(text)
        self._status_dot.set_status(color_key)

    def set_stats_summary(self, text: str):
        self._stats_label.setText(text)

    def set_progress(self, percent: int, label: str = ""):
        self._progress_bar.setValue(percent)
        if label:
            self._status_label.setText(label)

    def show_progress(self, visible: bool):
        self._progress_bar.setVisible(visible)

    def set_ollama_status(self, connected: bool):
        if connected:
            self._ollama_dot.set_status("success")
            self._ollama_label.setText("Ollama ✓")
        else:
            self._ollama_dot.set_status("error")
            self._ollama_label.setText("Ollama ✗")

    def show_message(self, text: str, timeout: int = 0):
        """兼容 QStatusBar.showMessage 的便捷方法。"""
        self._status_label.setText(text)