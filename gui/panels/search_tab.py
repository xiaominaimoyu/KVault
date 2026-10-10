"""检索标签页。

对应设计文档 §3.4.2 与 §7.2：

- 搜索框高 40px，聚焦时强调色边框
- 结果为卡片：文档名 + 块号 + 相似度分数条 + 内容预览（3 行截断）
- 检索中：按钮禁用并显示 loading 文案，输入框右侧 spinner
- 空结果：``search-x`` 图标 + "未找到相关结果" + 副标题
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.score_bar import ScoreBar

#: 结果内容预览的最大字符数
PREVIEW_CHARS = 300


class _ResultCard(QWidget):
    """单条检索结果卡片。

    §3.4.2：文档名 + 块号 + 分数条 + 内容预览。
    """

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.setObjectName("SearchResultCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        self._name = QLabel(result.document_name)
        self._name.setObjectName("SearchResultName")
        header.addWidget(self._name, 1)

        self._meta = QLabel(f"块 {result.chunk_index + 1}")
        self._meta.setObjectName("SearchResultMeta")
        header.addWidget(self._meta)
        layout.addLayout(header)

        self._score_bar = ScoreBar(getattr(result, "score", 0.0))
        layout.addWidget(self._score_bar)

        self._preview = QLabel(result.content[:PREVIEW_CHARS])
        self._preview.setObjectName("SearchResultPreview")
        self._preview.setWordWrap(True)
        # 3 行截断
        self._preview.setMaximumHeight(3 * 20)
        layout.addWidget(self._preview)

    def set_selected_state(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def score(self) -> float:
        return self._score_bar.score()


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
        self._unavailable_reason = ""
        self._init_ui()
        self._init_spinner()
        self._show_empty()

    # ---------------------------------------------------------------- 构建

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        # 输入框容器：承载右侧 spinner（§7.2）
        input_container = QWidget(self)
        input_row = QHBoxLayout(input_container)
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)

        self._input = QLineEdit(input_container)
        self._input.setObjectName("SearchQueryInput")
        self._input.setPlaceholderText("输入自然语言查询...")
        self._input.returnPressed.connect(self._on_search_clicked)
        input_row.addWidget(self._input, 1)

        self._spinner = QLabel("", input_container)
        self._spinner.setObjectName("SearchSpinner")
        self._spinner.setVisible(False)
        input_row.addWidget(self._spinner)
        self._input_container = input_container

        input_layout.addWidget(input_container, 1)

        self._top_k_spin = QSpinBox()
        self._top_k_spin.setRange(1, 20)
        self._top_k_spin.setValue(self._default_top_k)
        self._top_k_spin.setPrefix("Top-")
        self._top_k_spin.setFixedHeight(40)
        input_layout.addWidget(self._top_k_spin)

        self._search_btn = QPushButton("检索")
        self._search_btn.setProperty("btnType", "primary")
        self._search_btn.setFixedHeight(40)
        self._search_btn.clicked.connect(self._on_search_clicked)
        input_layout.addWidget(self._search_btn)

        layout.addLayout(input_layout)

        # 结果区：空状态 / 结果列表 / 错误
        self._stack = QStackedWidget(self)

        from gui.widgets.empty_state import EmptyState

        self._empty = EmptyState(
            "🔍", "未找到相关结果", "试试调整关键词或增大 Top-K"
        )
        self._stack.addWidget(self._empty)

        self._result_list = QListWidget()
        self._result_list.setObjectName("SearchResultList")
        self._result_list.setSpacing(4)
        self._result_list.itemClicked.connect(self._on_result_clicked)
        self._stack.addWidget(self._result_list)

        self._error_view = QTextBrowser()
        self._error_view.setObjectName("SearchErrorView")
        self._error_view.setOpenExternalLinks(False)
        self._stack.addWidget(self._error_view)

        layout.addWidget(self._stack, 1)

    def _init_spinner(self) -> None:
        """§7.2 检索中的 loading 指示（帧动画）。"""
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_index = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(80)
        self._spinner_timer.timeout.connect(self._advance_spinner)

    def _advance_spinner(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        self._spinner.setText(self._spinner_frames[self._spinner_index])

    # ---------------------------------------------------------------- 形态

    def _show_empty(self) -> None:
        self._stack.setCurrentWidget(self._empty)

    def set_unavailable_reason(self, reason: str) -> None:
        """标记检索不可用（受限模式）或恢复可用。

        复用既有的 error 视图承载原因，避免用户点击后才看到报错。
        """
        self._unavailable_reason = reason
        enabled = not reason
        self._input.setEnabled(enabled)
        self._search_btn.setEnabled(enabled)
        self._top_k_spin.setEnabled(enabled)
        if reason:
            self._input.setPlaceholderText(reason)
            self._show_error()
        else:
            self._input.setPlaceholderText("输入自然语言查询...")
            self._show_empty()

    def _show_results(self) -> None:
        self._stack.setCurrentWidget(self._result_list)

    def _show_error(self) -> None:
        self._stack.setCurrentWidget(self._error_view)

    # ---------------------------------------------------------------- 交互

    def _on_search_clicked(self) -> None:
        query = self._input.text().strip()
        if not query:
            return
        self.searchRequested.emit(query, self._top_k_spin.value())

    def _on_result_clicked(self, item: QListWidgetItem) -> None:
        result = item.data(Qt.UserRole)
        if result is not None:
            # §3.4.2 选中态
            self._mark_selected(item)
            self.resultClicked.emit(result)

    def _mark_selected(self, selected: QListWidgetItem) -> None:
        for row in range(self._result_list.count()):
            widget = self._result_list.itemWidget(self._result_list.item(row))
            if isinstance(widget, _ResultCard):
                widget.set_selected_state(widget is self._result_list.itemWidget(selected))

    # ---------------------------------------------------------------- 状态

    def get_query(self) -> str:
        return self._input.text()

    def top_k(self) -> int:
        return self._top_k_spin.value()

    def set_busy(self, busy: bool) -> None:
        """§7.2 检索中：按钮禁用 + loading 文案 + 输入框右侧 spinner。"""
        self._search_btn.setEnabled(not busy)
        self._search_btn.setText("检索中…" if busy else "检索")
        self._top_k_spin.setEnabled(not busy)

        if busy:
            self._spinner_index = 0
            self._spinner.setText(self._spinner_frames[0])
            self._spinner.setVisible(True)
            self._spinner_timer.start()
        else:
            self._spinner_timer.stop()
            self._spinner.setVisible(False)
            self._spinner.setText("")

    def is_busy(self) -> bool:
        return self._search_btn.isEnabled() is False

    # ---------------------------------------------------------------- 结果

    def show_results(self, results: list, score_color: Callable[[float], str] | None = None) -> None:
        """填充结果卡片列表。

        :param results: 结果对象列表，需含 document_name/chunk_index/score/content。
        :param score_color: 保留兼容；实际着色由 ScoreBar 的区间属性完成。
        """
        del score_color
        self._result_list.clear()

        if not results:
            self._show_empty()
            return

        for result in results:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, result)
            card = _ResultCard(result)
            self._result_list.addItem(item)
            self._result_list.setItemWidget(item, card)

        self._show_results()

    def show_error(self, error: str) -> None:
        import html as _html

        self._error_view.setHtml(
            '<div style="padding:16px;color:#F87171;">检索失败：'
            f"{_html.escape(str(error))}</div>"
        )
        self._show_error()

    def clear_results(self) -> None:
        self._result_list.clear()
        self._show_empty()

    def focus_search(self) -> None:
        self._input.setFocus()
        self._input.selectAll()

    # ---------------------------------------------------------------- 测试

    @property
    def result_list(self) -> QListWidget:
        """暴露结果列表，便于测试。"""
        return self._result_list

    @property
    def empty_state(self):
        """暴露空状态组件，便于测试。"""
        return self._empty

    @property
    def spinner(self) -> QLabel:
        return self._spinner

    def result_count(self) -> int:
        return self._result_list.count()