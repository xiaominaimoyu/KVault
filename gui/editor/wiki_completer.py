"""``[[`` 触发式的 wiki 链接补全。

用户在编辑器中键入 ``[[`` 后，本组件弹出候选列表；继续输入时实时过滤，
``Enter`` / ``Tab`` 接受，``Esc`` 取消。候选同时覆盖：

- 现有笔记的文件名与标题
- 已有链接中出现过的目标文本（可以补出「还没创建」的链接）

接受候选后补上 ``]]`` 并把光标停在中间，便于继续输入别名或小节。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QPlainTextEdit

#: 触发前缀
TRIGGER = "[["
CLOSE = "]]"

#: 匹配光标前紧邻 ``[[`` 且尚未闭合的链接语法
_OPEN_LINK = r"\[\[[^\]\n]*$"


class WikiLinkCompleter(QObject):
    """附着在编辑器上的补全器（组合而非继承，避免影响编辑器行为）。

    继承 :class:`QObject` 是必需的——Qt 要求事件过滤器本身是 ``QObject``。

    :param editor: 目标编辑器
    :param candidates_provider: ``(片段) -> list[str]``，返回候选路径列表
    """

    def __init__(self, editor: QPlainTextEdit, candidates_provider=None, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.candidates_provider = candidates_provider or (lambda fragment: [])
        self._popup: QListWidget | None = None
        self._start_pos = -1
        self._filter_installed = False

        editor.textChanged.connect(self._on_text_changed)

    # ---------------------------------------------------------------- 状态

    def is_active(self) -> bool:
        """当前是否处于补全状态。"""
        return self._popup is not None and self._popup.isVisible()

    def _current_fragment(self) -> str:
        """返回光标前、``[[`` 之后的片段文本。"""
        if self._start_pos < 0:
            return ""
        cursor = self.editor.textCursor()
        return self.editor.toPlainText()[self._start_pos : cursor.position()]

    # ---------------------------------------------------------------- 弹出

    def _on_text_changed(self) -> None:
        if self.is_active():
            # 补全过程中输入会触发本信号，交给 _refresh 处理
            self._refresh()
            return

        text = self.editor.toPlainText()
        cursor = self.editor.textCursor()
        head = text[: cursor.position()]

        match = _find_open_link(head)
        if match is None:
            return

        self._start_pos = match
        self._show()

    def _refresh(self) -> None:
        if not self.is_active():
            return
        text = self.editor.toPlainText()
        cursor = self.editor.textCursor()

        # 插入位置之后若出现了 ]]，说明用户已自行闭合，补全失效
        if CLOSE in text[cursor.position() :]:
            self.close()
            return

        self._select_all_preserving_cursor()
        fragment = self._current_fragment()

        items = self.candidates_provider(fragment) if fragment else self.candidates_provider("")
        self._fill(items, fragment)

    def _select_all_preserving_cursor(self) -> None:
        """保持当前输入不变的前提下重建列表。"""
        if self._popup is None:
            return
        self._popup.clear()
        fragment = self._current_fragment()

        for text in self.candidates_provider(fragment):
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, text)
            self._popup.addItem(item)

        if self._popup.count() == 0:
            self.close()
            return

        self._popup.setCurrentRow(0)

    def _show(self) -> None:
        if self._popup is None:
            self._popup = self._build_popup()

        if not self._filter_installed:
            self.editor.window().installEventFilter(self)
            self._filter_installed = True

        self._select_all_preserving_cursor()
        if self._popup.count() == 0:
            return

        cursor_rect = self.editor.cursorRect()
        point = self.editor.mapToGlobal(QPoint(cursor_rect.left(), cursor_rect.bottom() + 4))
        self._popup.move(point)
        self._popup.show()

    def _build_popup(self) -> QListWidget:
        popup = QListWidget(self.editor.window())
        popup.setObjectName("WikiLinkCompleterPopup")
        popup.setFrameShape(QListWidget.NoFrame)
        popup.setFocusPolicy(Qt.NoFocus)
        popup.setMaximumHeight(240)
        popup.setMinimumWidth(260)
        popup.itemActivated.connect(lambda _item: self.accept())
        return popup

    # ---------------------------------------------------------------- 接受

    def accept(self) -> None:
        """把选中候选写入编辑器。"""
        if not self.is_active() or self._popup is None:
            return

        item = self._popup.currentItem()
        if item is None:
            self.close()
            return

        chosen = item.data(Qt.UserRole)
        cursor = self.editor.textCursor()
        position = cursor.position()
        start = self._start_pos

        replacement = f"{TRIGGER}{chosen}{CLOSE}"
        cursor.setPosition(start)
        cursor.setPosition(position, QTextCursor.KeepAnchor)
        cursor.insertText(replacement)

        # 光标停在 ]] 之前，方便接着输入别名或 #小节
        after = self.editor.textCursor()
        after.setPosition(start + len(TRIGGER) + len(chosen))
        self.editor.setTextCursor(after)

        self.close()

    def close(self) -> None:
        """关闭补全弹窗。"""
        self._start_pos = -1
        if self._popup is not None:
            self._popup.hide()
        if self._filter_installed:
            try:
                self.editor.window().removeEventFilter(self)
            except RuntimeError:
                # 窗口已销毁时忽略
                pass
            self._filter_installed = False

    # ---------------------------------------------------------------- 事件

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt 接口命名
        """拦截按键：上下选择、Enter/Tab 接受、Esc 取消。"""
        if not self.is_active():
            return super().eventFilter(obj, event)

        if event.type() != event.KeyPress:
            return super().eventFilter(obj, event)

        if obj is not self._popup:
            key = event.key()
            if key == Qt.Key_Escape:
                self.close()
                return True
            if key in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Tab):
                self.accept()
                return True
            if key == Qt.Key_Down:
                self._move(1)
                return True
            if key == Qt.Key_Up:
                self._move(-1)
                return True

        if obj is self._popup and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key_Escape:
                self.close()
                return True

        return super().eventFilter(obj, event)

    def _move(self, delta: int) -> None:
        if self._popup is None or self._popup.count() == 0:
            return
        row = self._popup.currentRow()
        new_row = max(0, min(self._popup.count() - 1, row + delta))
        self._popup.setCurrentRow(new_row)


def _find_open_link(head: str) -> int | None:
    """返回光标前未闭合的 ``[[`` 起始位置，没有则返回 ``None``。"""
    start = head.rfind(TRIGGER)
    if start == -1:
        return None
    between = head[start + len(TRIGGER) :]
    if CLOSE in between:
        return None
    if "|" in between or "\n" in between:
        return None
    return start


def suggest(editor: QPlainTextEdit) -> bool:
    """手动触发补全（快捷键用）。"""
    cursor = editor.textCursor()
    cursor.insertText(TRIGGER)
    return True