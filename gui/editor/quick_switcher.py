"""快速切换器与命令面板。

对应 Obsidian 的 ``Ctrl+O``（快速打开）与 ``Ctrl+P``（命令面板）：

- :class:`QuickSwitcher` —— 按名称模糊匹配笔记，回车打开
- :class:`CommandPalette` —— 执行应用命令

两者共用同一套模糊匹配算法：子序列匹配 + 连续命中加成 + 命中位置加成，
因此 ``mltn`` 也能命中「机器学习笔记」。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def fuzzy_score(needle: str, haystack: str) -> float | None:
    """模糊匹配打分。

    命中返回 ``0~1`` 的分数（越大越靠前），不命中返回 ``None``。
    连续命中与靠前命中给予更高权重。
    """
    if not needle:
        return 0.5
    if not haystack:
        return None

    needle = needle.lower()
    haystack = haystack.lower()

    if needle in haystack:
        # 子串命中：越靠前分越高
        position = haystack.index(needle)
        return 1.0 - min(position / max(len(haystack), 1), 0.5) * 0.4

    score = 0.0
    index = 0
    previous = -2
    for ch in needle:
        found = haystack.find(ch, index)
        if found == -1:
            return None
        if found == previous + 1:
            score += 2.0  # 连续命中加成
        else:
            score += 1.0
        score -= min(found - index, 10) * 0.05
        previous = found
        index = found + 1

    # 按长度归一，避免长名称总是排在后面
    return min(score / (len(needle) * 2.0), 1.0)


@dataclass
class NoteCandidate:
    """快速切换器中的一个候选笔记。"""

    path: str
    title: str

    @property
    def display(self) -> str:
        return self.title or self.path


def rank_notes(candidates: list[NoteCandidate], query: str) -> list[NoteCandidate]:
    """按模糊匹配分数排序候选笔记。"""
    scored: list[tuple[float, NoteCandidate]] = []
    for candidate in candidates:
        score = fuzzy_score(query, candidate.display) or fuzzy_score(query, candidate.path)
        if score is not None:
            scored.append((score, candidate))

    scored.sort(key=lambda item: (-item[0], item[1].display))
    return [candidate for _score, candidate in scored]


class QuickSwitcherDialog(QDialog):
    """按名称快速打开笔记。"""

    #: 用户选择了一条笔记，参数为相对路径
    noteChosen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快速切换笔记")
        self.setModal(True)
        self.resize(560, 420)
        self.setObjectName("QuickSwitcher")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("输入笔记名称…")
        self._search.setObjectName("QuickSwitcherSearch")
        self._search.textChanged.connect(self._on_search_changed)

        self._status = QLabel("", self)
        self._status.setObjectName("QuickSwitcherStatus")

        self._list = QListWidget(self)
        self._list.setObjectName("QuickSwitcherList")

        buttons = QDialogButtonBox(self)
        open_button = QPushButton("打开", self)
        cancel_button = QPushButton("取消", self)
        open_button.clicked.connect(self._accept_current)
        cancel_button.clicked.connect(self.reject)
        buttons.addButton(open_button, QDialogButtonBox.AcceptRole)
        buttons.addButton(cancel_button, QDialogButtonBox.RejectRole)

        layout.addWidget(self._search)
        layout.addWidget(self._list)
        layout.addWidget(self._status)
        layout.addWidget(buttons)

        self._candidates: list[NoteCandidate] = []
        self._ranked: list[NoteCandidate] = []

    def set_candidates(self, candidates: list[NoteCandidate]) -> None:
        """设置候选笔记全集。"""
        self._candidates = list(candidates)
        self._refresh()

    def _on_search_changed(self, text: str) -> None:
        del text
        self._refresh()

    def _refresh(self) -> None:
        self._ranked = rank_notes(self._candidates, self._search.text().strip())
        self._list.clear()
        for candidate in self._ranked[:200]:
            self._list.addItem(candidate.display)
        self._status.setText(f"{len(self._ranked)} 条匹配")

    def current_path(self) -> str | None:
        """当前高亮项对应的笔记路径。"""
        row = self._list.currentRow()
        if row < 0 or row >= len(self._ranked):
            return self._ranked[0].path if self._ranked else None
        return self._ranked[row].path

    def _accept_current(self) -> None:
        path = self.current_path()
        if path:
            self.noteChosen.emit(path)
            self.accept()

    def _on_activated(self, item) -> None:
        """双击打开。"""
        row = self._list.row(item)
        if 0 <= row < len(self._ranked):
            self.noteChosen.emit(self._ranked[row].path)
            self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 — Qt 接口命名
        """下键切换、``Enter`` 打开。"""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._accept_current()
            event.accept()
            return
        if event.key() == Qt.Key_Down:
            self._list.setCurrentRow(min(self._list.count() - 1, self._list.currentRow() + 1))
            event.accept()
            return
        if event.key() == Qt.Key_Up:
            self._list.setCurrentRow(max(0, self._list.currentRow() - 1))
            event.accept()
            return
        super().keyPressEvent(event)


@dataclass
class Command:
    """一条可执行命令。"""

    name: str
    action: object
    shortcut: str = ""

    def display(self) -> str:
        return f"{self.name}    {self.shortcut}" if self.shortcut else self.name


class CommandPaletteDialog(QDialog):
    """命令面板。"""

    #: 用户选择了一条命令
    commandChosen = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("命令面板")
        self.setModal(True)
        self.resize(520, 380)
        self.setObjectName("CommandPalette")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("输入命令…")
        self._search.setObjectName("CommandPaletteSearch")
        self._search.textChanged.connect(self._on_search_changed)

        self._list = QListWidget(self)
        self._list.setObjectName("CommandPaletteList")
        self._list.itemActivated.connect(self._on_activated)

        self._empty = QLabel("没有匹配的命令", self)
        self._empty.setObjectName("CommandPaletteEmpty")

        layout.addWidget(self._search)
        layout.addWidget(self._list)
        layout.addWidget(self._empty)

        self._commands: list[Command] = []
        self._ranked: list[Command] = []

    def set_commands(self, commands: list[Command]) -> None:
        """注册可用命令。"""
        self._commands = list(commands)
        self._refresh()

    def _on_search_changed(self, text: str) -> None:
        del text
        self._refresh()

    def _refresh(self) -> None:
        query = self._search.text().strip()
        scored = []
        for command in self._commands:
            score = fuzzy_score(query, command.name)
            if score is not None:
                scored.append((score, command))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        self._ranked = [command for _score, command in scored]

        self._list.clear()
        for command in self._ranked:
            self._list.addItem(command.display())
        self._list.setVisible(bool(self._ranked))
        self._empty.setVisible(not self._ranked)

    def current_command(self) -> Command | None:
        """当前高亮的命令。"""
        row = self._list.currentRow()
        if 0 <= row < len(self._ranked):
            return self._ranked[row]
        return self._ranked[0] if self._ranked else None

    def _on_activated(self, item) -> None:
        """双击执行。"""
        row = self._list.row(item)
        if 0 <= row < len(self._ranked):
            self.commandChosen.emit(self._ranked[row])
            self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 — Qt 接口命名
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            command = self.current_command()
            if command is not None:
                self.commandChosen.emit(command)
                self.accept()
            event.accept()
            return
        super().keyPressEvent(event)


def show_quick_switcher(parent: QWidget, candidates: list[NoteCandidate]):
    """弹出快速切换器，返回对话框实例以便连接信号。"""
    dialog = QuickSwitcherDialog(parent)
    dialog.set_candidates(candidates)
    dialog.show()
    return dialog


def show_command_palette(parent: QWidget, commands: list[Command]):
    """弹出命令面板，返回对话框实例。"""
    dialog = CommandPaletteDialog(parent)
    dialog.set_commands(commands)
    dialog.show()
    return dialog