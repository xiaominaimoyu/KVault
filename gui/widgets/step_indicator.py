"""步骤指示器控件。

横向步骤条，用于模型切换、增量更新等多步流程的进度展示。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StepIndicator(QWidget):
    """步骤指示器。

    Args:
        steps: 步骤名称列表。
        parent: 父控件。
    """

    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("StepIndicator")

        self._steps = list(steps)
        self._current = 0
        self._step_labels: list[QLabel] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for i, name in enumerate(self._steps):
            index_label = QLabel(str(i + 1))
            index_label.setObjectName("StepIndexLabel")
            index_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(index_label)

            step_label = QLabel(name)
            step_label.setObjectName("StepLabel")
            step_label.setAlignment(Qt.AlignCenter)
            self._step_labels.append(step_label)
            layout.addWidget(step_label, 1)

            if i < len(self._steps) - 1:
                separator = QLabel("—")
                separator.setObjectName("StepSeparator")
                separator.setAlignment(Qt.AlignCenter)
                layout.addWidget(separator)

        self._refresh()

    def current_step(self) -> int:
        """返回当前步骤索引（从 0 开始）。"""
        return self._current

    def set_current_step(self, index: int) -> None:
        """设置当前步骤索引，自动夹取到有效范围。"""
        if not self._steps:
            return
        self._current = min(len(self._steps) - 1, max(0, int(index)))
        self._refresh()

    def is_completed(self, index: int) -> bool:
        """判断指定步骤是否已完成（严格早于当前步骤）。"""
        return 0 <= index < self._current

    def _refresh(self) -> None:
        """根据当前步骤刷新各标签状态。"""
        for i, label in enumerate(self._step_labels):
            if i < self._current:
                label.setProperty("state", "completed")
            elif i == self._current:
                label.setProperty("state", "current")
            else:
                label.setProperty("state", "pending")
            label.style().unpolish(label)
            label.style().polish(label)
