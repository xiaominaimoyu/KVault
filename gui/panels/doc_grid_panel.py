"""文档卡片网格面板。

以图标模式 QListWidget 承载 DocCard，
选择语义与表格视图保持一致（ExtendedSelection）。
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.doc_card import CARD_WIDTH, DocCard


class DocGridPanel(QWidget):
    """卡片网格视图面板。

    Signals:
        documentSelected(object): 选中变化，参数为 doc_id（str）或 None。
    """

    documentSelected = Signal(object)

    def __init__(self, reduce_motion: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("DocGridPanel")
        self._reduce_motion = reduce_motion

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._list = QListWidget()
        self._list.setObjectName("DocGridList")
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setMovement(QListWidget.Static)
        self._list.setSpacing(12)
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.setUniformItemSizes(True)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

    # ---- 数据填充 ----

    def set_documents(self, docs: list) -> None:
        """填充卡片。

        Args:
            docs: 文档对象列表，字段要求同 DocCard。
        """
        self._list.clear()
        for doc in docs:
            card = DocCard(doc, self._reduce_motion)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, doc.id)
            item.setSizeHint(QSize(CARD_WIDTH, card.sizeHint().height()))
            self._list.addItem(item)
            self._list.setItemWidget(item, card)

    def row_count(self) -> int:
        return self._list.count()

    # ---- 选中状态 ----

    def selected_doc_ids(self) -> list[str]:
        return [item.data(Qt.UserRole) for item in self._list.selectedItems()]

    def select_doc(self, doc_id: str) -> bool:
        """按 doc_id 选中对应卡片。

        Returns:
            是否找到并选中。
        """
        for row in range(self._list.count()):
            if self._list.item(row).data(Qt.UserRole) == doc_id:
                self._list.item(row).setSelected(True)
                return True
        return False

    def clear_selection(self) -> None:
        self._list.clearSelection()

    # ---- 内部事件 ----

    def _on_selection_changed(self):
        ids = self.selected_doc_ids()
        self.documentSelected.emit(ids[0] if ids else None)
