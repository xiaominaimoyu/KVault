"""反链与出链面板。

知识库的价值在于「笔记之间如何连接」，这两个面板把它显式化：

- :class:`BacklinkPanel` —— 谁引用了我（反链），带上下文预览
- :class:`OutgoingLinkPanel` —— 我引用了谁，区分已解析与断链

点击任意条目都会上抛 :attr:`noteSelected`，由外部完成跳转。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from core.note_store import LinkRecord


class _LinkListBase(QWidget):
    """链接列表面板基类。"""

    #: 用户选择了一条记录
    noteSelected = Signal(str)
    #: 用户请求创建缺失的笔记（断链修复）
    createRequested = Signal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._header = QLabel(title)
        self._header.setObjectName("LinkPanelHeader")
        self._list = QListWidget(self)
        self._list.setObjectName("LinkPanelList")
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._empty = QLabel("暂无")
        self._empty.setObjectName("LinkPanelEmpty")
        self._empty.setAlignment(Qt.AlignCenter)

        layout.addWidget(self._header)
        layout.addWidget(self._list)
        layout.addWidget(self._empty)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self.noteSelected.emit(path)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """断链条目双击时提供「创建该笔记」的快捷操作。"""
        item = self._list.item(self._list.row(item))
        if item is None:
            return
        if item.data(Qt.UserRole + 1) == "broken":
            target = item.data(Qt.UserRole + 2)
            if target:
                self.createRequested.emit(target)

    def clear_list(self) -> None:
        """清空列表。"""
        self._list.clear()
        self._list.setVisible(False)
        self._empty.setVisible(True)

    def _finish(self, count: int) -> None:
        self._list.setVisible(count > 0)
        self._empty.setVisible(count == 0)

    @property
    def list_widget(self) -> QListWidget:
        """暴露内部列表，便于测试。"""
        return self._list

    @property
    def header(self) -> QLabel:
        return self._header

    @property
    def empty_label(self) -> QLabel:
        return self._empty


class BacklinkPanel(_LinkListBase):
    """反链面板：列出引用了当前笔记的所有位置。"""

    def __init__(self, parent=None):
        super().__init__("反向链接", parent)

    def set_links(self, links: list[LinkRecord]) -> None:
        """填充反链列表。"""
        self._list.clear()
        self._header.setText(f"反向链接 ({len(links)})")

        for link in links:
            item = QListWidgetItem(self._compose(link))
            item.setData(Qt.UserRole, link.source_path)
            item.setToolTip(link.context or link.source_path)
            self._list.addItem(item)

        self._finish(len(links))

    @staticmethod
    def _compose(link: LinkRecord) -> str:
        source = link.source_path.rsplit("/", 1)[-1]
        if source.endswith(".md"):
            source = source[:-3]

        context = link.context.strip()
        # 上下文里已经包含目标链接本身时，去掉重复的 [[...]] 让文字更干净
        context = context.replace(f"[[{link.target_path}", "").replace("]]", "").strip()

        if context:
            preview = context if len(context) <= 60 else context[:59] + "…"
            return f"{source}\n{preview}"
        return source


class OutgoingLinkPanel(_LinkListBase):
    """出链面板：列出当前笔记引用的所有目标。"""

    def __init__(self, parent=None):
        super().__init__("出链", parent)

    def set_links(self, links: list[LinkRecord]) -> None:
        """填充出链列表，断链单独标色。"""
        self._list.clear()
        broken = sum(1 for link in links if link.is_broken)
        self._header.setText(f"出链 ({len(links)})" + (f" · 断链 {broken}" if broken else ""))

        for link in links:
            target = link.target_path
            if link.heading:
                target += f"#{link.heading}"
            label = f"{'! ' if link.is_embed else ''}{target}"

            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, link.target_resolved)
            item.setData(Qt.UserRole + 1, "broken" if link.is_broken else "ok")
            item.setData(Qt.UserRole + 2, link.target_path)
            if link.is_broken:
                item.setToolTip("目标不存在，双击可创建该笔记")
            self._list.addItem(item)

        self._finish(len(links))

    def broken_targets(self) -> list[str]:
        """返回所有断链的目标文本。"""
        targets: list[str] = []
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.UserRole + 1) == "broken":
                target = item.data(Qt.UserRole + 2)
                if target:
                    targets.append(target)
        return targets