"""元数据标签页。

以键值表展示文档元数据，路径行支持点击复制。
"""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_PATH_KEYS = ("路径", "path", "Path")


def _is_path_key(key: str) -> bool:
    return any(marker in key for marker in _PATH_KEYS)


class MetadataTab(QWidget):
    """元数据标签页。

    Methods:
        set_metadata(pairs): 以 [(键, 值), ...] 填充键值表，路径行附带复制按钮。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MetadataTab")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["字段", "值", ""])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.setColumnWidth(0, 140)
        self._table.setColumnWidth(2, 60)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self._table)

    def set_metadata(self, pairs: list[tuple[str, str]]):
        """填充元数据键值表。

        Args:
            pairs: [(键, 值), ...]；含"路径"关键字的行附复制按钮。
        """
        self._table.setRowCount(0)
        for key, value in pairs:
            row = self._table.rowCount()
            self._table.insertRow(row)

            key_item = QTableWidgetItem(key)
            self._table.setItem(row, 0, key_item)
            self._table.setItem(row, 1, QTableWidgetItem(str(value)))

            if _is_path_key(key):
                self._table.setCellWidget(row, 2, self._build_copy_btn(str(value)))

    def _build_copy_btn(self, value: str) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        btn = QPushButton("复制")
        btn.setProperty("btnType", "secondary")
        btn.setToolTip("复制路径")
        btn.clicked.connect(lambda: self._copy_to_clipboard(value))
        layout.addWidget(btn)
        return container

    def _copy_to_clipboard(self, value: str):
        QGuiApplication.clipboard().setText(value)
