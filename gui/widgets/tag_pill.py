"""标签 Pill 控件。

设计文档 §8.4 / §9.2 要求的可选中标签胶囊：

- ``--radius-full`` 胶囊外形、内边距 4px 10px、``--text-xs``
- 选中：``--accent-primary`` 15% 底 + 强调色文字与边框
- hover：``--bg-raised``

以 ``QPushButton`` 为基类，因此天然可获得键盘焦点与可访问性，
选中态通过动态属性 ``selected`` 暴露给 QSS。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton


class TagPill(QPushButton):
    """可选中的标签胶囊。"""

    toggledState = Signal(str, bool)

    def __init__(self, name: str, count: int = 0, parent=None):
        super().__init__(parent)
        self._name = name
        self._count = count
        self._selected = False

        self.setObjectName("TagPill")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setProperty("selected", False)
        self._render()

        self.toggled.connect(self._on_toggled)

    # ---------------------------------------------------------------- 状态

    def _render(self) -> None:
        """刷新显示文本。``#标签 · 3``。"""
        text = f"#{self._name}"
        if self._count:
            text += f" · {self._count}"
        self.setText(text)
        self.setToolTip(f"标签：{self._name}" + (f"（{self._count} 篇）" if self._count else ""))

    def _on_toggled(self, checked: bool) -> None:
        self._selected = checked
        self.setProperty("selected", checked)
        # 动态属性变化后必须重新 polish 才会应用新样式
        self.style().unpolish(self)
        self.style().polish(self)
        self.toggledState.emit(self._name, checked)

    # ---------------------------------------------------------------- 访问器

    def tag_name(self) -> str:
        """标签名（不含 ``#``）。"""
        return self._name

    def count(self) -> int:
        """关联文档数。"""
        return self._count

    def set_count(self, count: int) -> None:
        """更新计数并刷新显示。"""
        self._count = max(0, int(count))
        self._render()

    def set_tag_name(self, name: str) -> None:
        """重命名并刷新显示。"""
        self._name = name
        self._render()

    def is_selected(self) -> bool:
        return self._selected

    def set_selected_state(self, selected: bool) -> None:
        """以编程方式切换选中态（不经过用户点击）。"""
        self.setChecked(selected)