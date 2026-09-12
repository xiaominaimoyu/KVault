"""检索标签页。

搜索框 + Top-K 选择器 + 检索按钮 + 结果列表。
检索业务逻辑由上层（MainWindow）通过信号接入。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SearchTab(QWidget):
    """检索标签页。

    Signals:
        searchRequested(str, int): 发起检索，参数为 (query, top_k)。
        resultClicked(object): 结果被点击，参数为结果对象。
    """

    searchRequested = Signal(str, int)
    resultClicked = Signal(object)

    def __init__(self, default_top_k: int = 5, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchTab")
        self._default_top_k = default_top_k
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("输入自然语言查询...")
        self._input.returnPressed.connect(self._on_search_clicked)
        input_layout.addWidget(self._input, 1)

        self._top_k_spin = QSpinBox()
        self._top_k_spin.setRange(1, 20)
        self._top_k_spin.setValue(self._default_top_k)
        self._top_k_spin.setPrefix("Top-")
        input_layout.addWidget(self._top_k_spin)

        self._search_btn = QPushButton("检索")
        self._search_btn.setProperty("btnType", "primary")
        self._search_btn.clicked.connect(self._on_search_clicked)
        input_layout.addWidget(self._search_btn)

        layout.addLayout(input_layout)

        self._result_list = QListWidget()
        self._result_list.setSpacing(4)
        self._result_list.itemClicked.connect(self._on_result_clicked)
        layout.addWidget(self._result_list, 1)

    def _on_search_clicked(self):
        self.searchRequested.emit(self._input.text().strip(), self._top_k_spin.value())

    def _on_result_clicked(self, item: QListWidgetItem):
        result = item.data(Qt.UserRole)
        if result is not None:
            self.resultClicked.emit(result)

    # ---- 状态与结果 ----

    def get_query(self) -> str:
        return self._input.text()

    def top_k(self) -> int:
        return self._top_k_spin.value()

    def set_busy(self, busy: bool):
        self._search_btn.setEnabled(not busy)

    def show_results(self, results: list, score_color: Callable[[float], str]):
        """填充结果列表。

        Args:
            results: 结果对象列表，需含 document_name/chunk_index/score/content。
            score_color: 分数到颜色字符串的映射函数。
        """
        self._result_list.clear()
        if not results:
            self._result_list.addItem("未找到相关结果")
            return

        for result in results:
            item = QListWidgetItem()
            item.setText(
                f"{result.document_name} · 块 {result.chunk_index + 1} · "
                f"相似度 {result.score:.2f}"
            )
            item.setToolTip(result.content[:300])
            item.setData(Qt.UserRole, result)
            item.setForeground(QBrush(QColor(score_color(result.score))))
            self._result_list.addItem(item)

    def show_error(self, error: str):
        self._result_list.clear()
        self._result_list.addItem(f"检索失败: {error}")

    def clear_results(self):
        self._result_list.clear()

    def focus_search(self):
        self._input.setFocus()
