"""Markdown 笔记编辑器。

在 :class:`QPlainTextEdit` 之上补齐写作工具的基本能力：

- 行号槽（当前行高亮）
- 未保存标记与自动保存
- 快捷键：保存 ``Ctrl+S``、新建 ``Ctrl+N``、查找
- wiki 链接补全与跳转（``Ctrl+点击`` 打开目标笔记）

编辑器只负责**编辑与信号**，不碰磁盘——保存由调用方通过 ``saveRequested``
信号交给 :class:`~core.note_store.NoteStore`，避免 GUI 与存储耦合。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from gui.editor.markdown_highlighter import MarkdownHighlighter
from gui.editor.wiki_completer import WikiLinkCompleter
from gui.styles.variables import FONT_MONO, TEXT_SIZES, TOKENS_DARK, TOKENS_LIGHT


class LineNumberArea(QWidget):
    """行号槽。由 :class:`MarkdownEditor` 负责把尺寸事件转发过来。"""

    def __init__(self, editor: "MarkdownEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 — Qt 接口命名
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt 接口命名
        self._editor.paint_line_numbers(event)


class MarkdownEditor(QWidget):
    """带行号、高亮、自动保存的 Markdown 编辑器。"""

    #: 内容变化（未保存）
    textChangedSignal = Signal(str)
    #: 用户请求保存
    saveRequested = Signal()
    #: 请求打开某条笔记，参数为 wiki 链接目标
    openLinkRequested = Signal(str)
    #: 保存状态变化，参数为是否已保存
    dirtyChanged = Signal(bool)

    AUTOSAVE_INTERVAL_MS = 2000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dirty = False
        self._current_path: str | None = None
        self._candidates_provider = lambda fragment: []
        self._link_resolver = lambda target: None

        layout = self._layout()
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("MarkdownEditorText")
        self.editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.editor.setTabStopDistance(32)

        self.line_number_area = LineNumberArea(self)
        self.highlighter = MarkdownHighlighter(self.editor.document())
        self.completer = WikiLinkCompleter(self.editor, self._candidates_provider)

        layout.addWidget(self.line_number_area)
        layout.addWidget(self.editor)

        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(self.AUTOSAVE_INTERVAL_MS)
        self._autosave.timeout.connect(self._on_autosave_timeout)

        self.editor.blockCountChanged.connect(self._update_line_number_width)
        self.editor.updateRequest.connect(self._update_line_number)
        self.editor.cursorPositionChanged.connect(self._highlight_current_line)
        self.editor.textChanged.connect(self._on_text_changed)
        # 快捷键必须挂在真正的输入控件上：编辑器文本在外层 QPlainTextEdit 里编辑，
        # 覆写外层 keyPressEvent 收不到按键
        self.editor.installEventFilter(self)

        self._update_line_number_width()
        self._highlight_current_line()

    def _layout(self):
        from PySide6.QtWidgets import QHBoxLayout

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        return layout

    # ---------------------------------------------------------------- 主题

    def set_theme(self, theme: str) -> None:
        """切换配色主题。"""
        self.highlighter.set_theme(theme)
        self._highlight_current_line()
        self.update()

    def _tokens(self) -> dict:
        return TOKENS_DARK if self.highlighter._theme == "dark" else TOKENS_LIGHT

    # ---------------------------------------------------------------- 内容

    def set_text(self, text: str, path: str | None = None) -> None:
        """载入笔记内容，并重置脏状态。"""
        self._autosave.stop()
        self.editor.setPlainText(text or "")
        self._current_path = path
        self._set_dirty(False)

    def text(self) -> str:
        """返回当前内容。"""
        return self.editor.toPlainText()

    def set_path(self, path: str | None) -> None:
        """更新当前笔记路径。"""
        self._current_path = path

    def path(self) -> str | None:
        return self._current_path

    def is_dirty(self) -> bool:
        return self._dirty

    def mark_clean(self) -> None:
        """由外部在保存成功后调用。"""
        self._set_dirty(False)

    def set_candidates_provider(self, provider) -> None:
        """设置 wiki 链接补全的候选来源。"""
        self._candidates_provider = provider
        self.completer.candidates_provider = provider

    def set_link_resolver(self, resolver) -> None:
        """设置链接解析回调，用于断链配色与 ``Ctrl+点击`` 跳转。"""
        self._link_resolver = resolver
        self.highlighter.set_resolver(lambda target: resolver(target, self._current_path))

    # ---------------------------------------------------------------- 行号

    def line_number_width(self) -> int:
        """行号槽宽度，随行数位数自适应。"""
        digits = max(2, len(str(max(1, self.editor.blockCount()))))
        metrics = QFontMetricsF(self.editor.font())
        return int(metrics.horizontalAdvance("9" * digits)) + 18

    def _update_line_number_width(self) -> None:
        self.line_number_area.setFixedWidth(self.line_number_width())
        self._update_line_number()

    def _update_line_number(self, rect: QRect = QRect(), dy: int = 0) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.editor.viewport().rect()):
            self._update_line_number_width()

    def _highlight_current_line(self) -> None:
        """高亮光标所在行的背景。"""
        from PySide6.QtWidgets import QTextEdit

        selection = QTextEdit.ExtraSelection()
        selection.cursor = self.editor.textCursor()
        selection.cursor.clearSelection()

        tokens = self._tokens()
        selection.format.setBackground(QColor(tokens["bg-raised"]))
        selection.format.setProperty(QTextFormat.FullWidthSelection, True)

        self.editor.setExtraSelections([selection])

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt 接口命名
        super().resizeEvent(event)
        self._update_line_number()

    def paint_line_numbers(self, event) -> None:
        """绘制行号与当前行背景。"""
        painter = QPainter(self.line_number_area)
        tokens = self._tokens()

        painter.fillRect(event.rect(), QColor(tokens["bg-inset"]))

        block = self.editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).top()
        bottom = top + self.editor.blockBoundingRect(block).height()

        current = self.editor.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                if block_number == current:
                    painter.fillRect(
                        0, int(top), self.line_number_area.width(), int(bottom - top),
                        QColor(tokens["bg-raised"]),
                    )

                painter.setPen(QColor(tokens["fg-muted"]))
                painter.drawText(
                    0,
                    int(top),
                    self.line_number_area.width() - 8,
                    self.editor.fontMetrics().height(),
                    Qt.AlignRight,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + self.editor.blockBoundingRect(block).height()
            block_number += 1

    # ---------------------------------------------------------------- 脏状态

    def _on_text_changed(self) -> None:
        self._set_dirty(True)
        self._autosave.start()
        self.textChangedSignal.emit(self.text())

    def _on_autosave_timeout(self) -> None:
        if self._dirty:
            self.saveRequested.emit()

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirtyChanged.emit(dirty)

    # ---------------------------------------------------------------- 链接

    def link_at(self, position) -> str | None:
        """返回指定视口位置处的 wiki 链接目标，无链接时返回 ``None``。"""
        from core.links import extract_links

        text = self.editor.toPlainText()
        offset = self.editor.cursorForPosition(position).position()

        for link in extract_links(text):
            if link.start <= offset <= link.end:
                return link.target
        return None

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt 接口命名
        """``Ctrl+点击`` 打开链接目标。"""
        if event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
            target = self.link_at(event.pos())
            if target:
                self.openLinkRequested.emit(target)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    # ---------------------------------------------------------------- 快捷键

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt 接口命名
        """拦截编辑器按键：``Ctrl+S`` 转为保存请求。"""
        from PySide6.QtCore import QEvent

        if obj is self.editor and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_S and event.modifiers() & Qt.ControlModifier:
                self.saveRequested.emit()
                return True
        return super().eventFilter(obj, event)

    def apply_content_font(self) -> None:
        """应用等宽内容字体。"""
        font = QFont()
        font.setFamilies(["Consolas", "Cascadia Code", "monospace"])
        font.setPointSize(TEXT_SIZES["base"])
        self.editor.setFont(font)
        self.editor.setTabStopDistance(int(QFontMetricsF(font).horizontalAdvance(" ") * 4))

    def font_family(self) -> str:
        """返回内容字体族，供测试与主题模块断言。"""
        return FONT_MONO