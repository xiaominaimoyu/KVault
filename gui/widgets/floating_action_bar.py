"""批量操作浮动工具条控件。

文档多选时浮现在列表上方的操作条，
通过 actionTriggered 信号统一对外发布按钮事件。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class FloatingActionBar(QFrame):
    """批量操作浮动工具条。

    Args:
        actions: (action_id, 按钮文案) 列表。
        parent: 父控件。
    """

    actionTriggered = Signal(str)

    def __init__(self, actions: list[tuple[str, str]] | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("FloatingActionBar")

        self._action_buttons: dict[str, QPushButton] = {}

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 6, 12, 6)
        self._layout.setSpacing(8)

        self._info_label = QLabel()
        self._info_label.setObjectName("FloatingActionBarInfo")
        self._layout.addWidget(self._info_label)

        self.set_actions(actions or [])

    def set_info_text(self, text: str) -> None:
        """设置左侧信息文案，如"已选 3 项"。"""
        self._info_label.setText(text)

    def set_actions(self, actions: list[tuple[str, str]]) -> None:
        """整体替换操作按钮集合。"""
        self.clear()
        for action_id, text in actions:
            self._add_action(action_id, text)

    def clear(self) -> None:
        """移除全部操作按钮。"""
        for btn in self._action_buttons.values():
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._action_buttons.clear()

    def set_action_enabled(self, action_id: str, enabled: bool) -> None:
        """启用/禁用指定操作按钮。"""
        btn = self._action_buttons.get(action_id)
        if btn is not None:
            btn.setEnabled(enabled)

    def _add_action(self, action_id: str, text: str) -> None:
        btn = QPushButton(text)
        btn.setObjectName("FloatingActionButton")
        btn.clicked.connect(lambda: self.actionTriggered.emit(action_id))
        self._layout.addWidget(btn)
        self._action_buttons[action_id] = btn
