"""全局键盘快捷键模块。

按设计规范 5.6 集中定义快捷键表，
ShortcutManager 负责注册与分发，便于测试与后续扩展。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

# action_id -> 快捷键序列（设计文档 5.6）
DEFAULT_SHORTCUTS: dict[str, str] = {
    "import_docs": "Ctrl+I",
    "focus_global_search": "Ctrl+F",
    "focus_semantic_search": "Ctrl+K",
    "open_settings": "Ctrl+S",
    "refresh_status": "Ctrl+R",
    "delete_selected": "Delete",
    "clear_selection": "Esc",
    "tab_preview": "Ctrl+1",
    "tab_search": "Ctrl+2",
    "tab_metadata": "Ctrl+3",
}


class ShortcutManager:
    """在给定父控件上注册全局快捷键并分发到处理器。

    Args:
        parent: 快捷键所属的父控件（通常是主窗口）。
        handlers: action_id -> 回调 的映射；
            只注册在 DEFAULT_SHORTCUTS 中且提供了回调的项。
    """

    def __init__(self, parent: QWidget, handlers: dict[str, Callable]):
        self._parent = parent
        self.shortcuts: dict[str, QShortcut] = {}
        for action_id, key in DEFAULT_SHORTCUTS.items():
            handler = handlers.get(action_id)
            if handler is None:
                continue
            shortcut = QShortcut(QKeySequence(key), parent)
            shortcut.activated.connect(handler)
            self.shortcuts[action_id] = shortcut
