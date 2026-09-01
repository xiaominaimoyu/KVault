"""相似度分数条控件。

横向进度条 + 百分比文本，用于检索结果相似度展示。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget


class ScoreBar(QWidget):
    """相似度分数条，分数范围 0.0 ~ 1.0。

    Args:
        score: 初始分数。
        parent: 父控件。
    """

    def __init__(self, score: float = 0.0, parent=None):
        super().__init__(parent)
        self.setObjectName("ScoreBar")

        self._score = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._bar = QProgressBar()
        self._bar.setObjectName("ScoreBarTrack")
        self._bar.setTextVisible(False)
        self._bar.setRange(0, 100)
        layout.addWidget(self._bar, 1)

        self._score_label = QLabel()
        self._score_label.setObjectName("ScoreBarLabel")
        self._score_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._score_label.setFixedWidth(40)
        layout.addWidget(self._score_label)

        self.set_score(score)

    def score(self) -> float:
        """返回当前分数（0.0 ~ 1.0）。"""
        return self._score

    def set_score(self, value: float) -> None:
        """设置分数并更新展示，自动夹取到 [0, 1]。"""
        self._score = min(1.0, max(0.0, float(value)))
        self._bar.setValue(int(round(self._score * 100)))
        self._score_label.setText(f"{round(self._score * 100):d}%")
