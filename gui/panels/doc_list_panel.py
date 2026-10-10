"""文档列表面板。

封装文档表格与卡片网格两种视图：文件名、格式徽章、大小、状态点 + 文字、块数、导入时间。
支持视图切换、多选批量操作浮动条、拖拽文件导入。
过滤逻辑由上层（MainWindow）完成后传入最终文档列表。
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.panels.doc_grid_panel import DocGridPanel
from gui.widgets.empty_state import EmptyState
from gui.widgets.floating_action_bar import FloatingActionBar
from gui.widgets.format_badge import FormatBadge
from gui.widgets.motion import fade_in, fade_slide_in
from gui.widgets.status_dot import StatusDot

STATUS_LABELS = {
    "indexed": "已索引",
    "indexing": "索引中",
    "pending": "待处理",
    "failed": "失败",
}

_COLUMNS = ["文件名", "格式", "大小", "状态", "块数", "导入时间", "doc_id"]
_COL_DOC_ID = 6

_BATCH_ACTIONS = [
    ("move", "移动"),
    ("tag", "标签"),
    ("reindex", "重索引"),
    ("delete", "删除"),
]


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ["KB", "MB", "GB"]:
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value / 1024:.1f} TB"


def format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


class StatusCell(QWidget):
    """状态列单元格：8px 状态点 + 状态文字。"""

    def __init__(self, status: str, reduce_motion: bool = True, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)
        self._dot = StatusDot(status, reduce_motion)
        layout.addWidget(self._dot)
        self._label = QLabel(STATUS_LABELS.get(status, status))
        layout.addWidget(self._label)
        layout.addStretch(1)


class DocListPanel(QWidget):
    """文档列表面板（表格 / 卡片双视图）。

    Signals:
        documentSelected(object): 选中变化，参数为 doc_id（str）或 None。
        contextMenuRequested(object, list): 右键菜单请求，参数为 (全局坐标 QPoint, [doc_id])。
        importRequested(): 空状态 CTA 按钮点击，请求导入文档。
        filesDropped(list): 拖拽释放导入，参数为本地文件路径列表。
        batchActionRequested(str, list): 批量操作请求，参数为 (action_id, [doc_id])。
    """

    documentSelected = Signal(object)
    contextMenuRequested = Signal(object, list)
    importRequested = Signal()
    filesDropped = Signal(list)
    batchActionRequested = Signal(str, list)

    def __init__(self, reduce_motion: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("DocListPanel")
        self._reduce_motion = reduce_motion
        self._theme = "dark"
        self._config = None
        self._overlay_anim = None
        self._empty_anim = None
        self._view_mode = "table"
        self._init_ui()

    def _init_ui(self):
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- 视图切换头 ----
        header = QHBoxLayout()
        header.setContentsMargins(8, 4, 8, 4)
        header.addStretch(1)

        self._table_view_btn = QPushButton("列表")
        self._table_view_btn.setObjectName("ViewToggleButton")
        self._table_view_btn.setCheckable(True)
        self._table_view_btn.setChecked(True)
        self._table_view_btn.clicked.connect(lambda: self.set_view_mode("table"))
        header.addWidget(self._table_view_btn)

        self._card_view_btn = QPushButton("卡片")
        self._card_view_btn.setObjectName("ViewToggleButton")
        self._card_view_btn.setCheckable(True)
        self._card_view_btn.clicked.connect(lambda: self.set_view_mode("grid"))
        header.addWidget(self._card_view_btn)
        layout.addLayout(header)

        # ---- 视图堆栈 ----
        self._stacked = QStackedWidget()
        layout.addWidget(self._stacked, 1)

        # §7.1 规定图标 / 标题 / 副标题文案
        self._empty_state = EmptyState(
            "🔍",
            "还没有文档",
            "拖拽文件到此处，或点击导入",
            cta_text="导入文档",
        )
        self._empty_state.ctaClicked.connect(self.importRequested)
        self._stacked.addWidget(self._empty_state)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.hideColumn(_COL_DOC_ID)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._stacked.addWidget(self._table)

        self._grid = DocGridPanel(self._reduce_motion)
        self._grid.documentSelected.connect(self._on_grid_selection_changed)
        self._stacked.addWidget(self._grid)

        # ---- 批量操作浮动条 ----
        self._action_bar = FloatingActionBar(_BATCH_ACTIONS, self)
        self._action_bar.setObjectName("FloatingActionBar")
        self._action_bar.actionTriggered.connect(self._on_batch_action)
        self._action_bar.hide()

        # ---- 拖拽导入遮罩 ----
        self._drop_overlay = QLabel("释放导入", self)
        self._drop_overlay.setObjectName("DropOverlay")
        self._drop_overlay.setAlignment(Qt.AlignCenter)
        self._drop_overlay.hide()

    # ---- 数据填充 ----

    def set_documents(self, docs: list):
        """填充文档行与卡片。

        Args:
            docs: 文档对象列表，需含 id/file_name/file_ext/file_size/status/chunk_count/created_at。
        """
        from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

        tokens = TOKENS_DARK if getattr(self, "_theme", "dark") == "dark" else TOKENS_LIGHT

        self._table.setRowCount(0)
        self._grid.set_documents(docs)
        for doc in docs:
            row = self._table.rowCount()
            self._table.insertRow(row)

            # §3.3.1 文档名：--text-base --fg-primary；失败态用 --status-error
            name_item = QTableWidgetItem(doc.file_name)
            if doc.status == "failed":
                name_item.setForeground(QColor(tokens["status-error"]))
            self._table.setItem(row, 0, name_item)

            self._table.setCellWidget(row, 1, FormatBadge(doc.file_ext))
            self._table.setCellWidget(
                row, 3, StatusCell(doc.status, self._reduce_motion)
            )

            # §3.3.1 块数 / 大小：--text-sm 等宽、右对齐、--fg-secondary
            size_item = QTableWidgetItem(format_size(doc.file_size))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, 2, size_item)

            chunk_item = QTableWidgetItem(str(doc.chunk_count))
            chunk_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, 4, chunk_item)

            time_item = QTableWidgetItem(format_time(doc.created_at))
            time_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, 5, time_item)

            self._table.setItem(row, _COL_DOC_ID, QTableWidgetItem(doc.id))
        self._sync_view()

    def set_theme(self, theme: str) -> None:
        """记录当前主题，供失败态着色使用。"""
        self._theme = theme

    def row_count(self) -> int:
        return self._table.rowCount()

    # ---- 视图模式 ----

    def view_mode(self) -> str:
        """返回当前视图模式：``"table"``（列表）或 ``"grid"``（卡片网格）。"""
        return self._view_mode

    def set_view_mode(self, mode: str) -> None:
        """切换视图模式，无效值将被忽略。

        §3.3.3：切换结果会写入 ``config.view_mode`` 以记忆用户选择。
        """
        if mode not in ("table", "grid"):
            return
        self._view_mode = mode
        self._table_view_btn.setChecked(mode == "table")
        self._card_view_btn.setChecked(mode == "grid")
        self._sync_view()
        self._persist_view_mode()

    def _persist_view_mode(self) -> None:
        """把视图模式写入配置。"""
        config = getattr(self, "_config", None)
        if config is not None:
            config.view_mode = self._view_mode

    def attach_config(self, config) -> None:
        """绑定配置：读取记忆的视图模式并启用持久化。"""
        self._config = config
        if config is not None:
            self.set_view_mode(getattr(config, "view_mode", "table"))

    def _sync_view(self):
        """根据文档数与视图模式刷新当前页。"""
        if self.row_count() == 0:
            self._stacked.setCurrentWidget(self._empty_state)
            # 空状态出现：上移淡入（300ms，reduce_motion 时跳过）
            self._empty_anim = fade_slide_in(
                self._empty_state, duration=300, offset=12,
                reduce_motion=self._reduce_motion,
            )
        else:
            self._stacked.setCurrentWidget(
                self._table if self._view_mode == "table" else self._grid
            )
        self._update_action_bar()

    # ---- 选中状态 ----

    def _active_view(self):
        return self._table if self._view_mode == "table" else self._grid

    def selected_doc_ids(self) -> list[str]:
        if self._view_mode == "grid":
            return self._grid.selected_doc_ids()
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        return [self._table.item(row, _COL_DOC_ID).text() for row in rows]

    def select_doc(self, doc_id: str) -> bool:
        """按 doc_id 选中（当前视图）。

        Returns:
            是否找到并选中。
        """
        if self._view_mode == "grid":
            return self._grid.select_doc(doc_id)
        for row in range(self._table.rowCount()):
            if self._table.item(row, _COL_DOC_ID).text() == doc_id:
                self._table.selectRow(row)
                return True
        return False

    def clear_selection(self):
        self._table.clearSelection()
        self._grid.clear_selection()

    # ---- 批量操作浮动条 ----

    def _update_action_bar(self):
        ids = self.selected_doc_ids()
        if len(ids) >= 2:
            self._action_bar.set_info_text(f"已选 {len(ids)} 项")
            self._action_bar.adjustSize()
            self._position_overlays()
            self._action_bar.show()
            self._action_bar.raise_()
        else:
            self._action_bar.hide()

    def _on_batch_action(self, action_id: str):
        self.batchActionRequested.emit(action_id, self.selected_doc_ids())

    def _position_overlays(self):
        """将浮动条与拖拽遮罩定位到面板底部。"""
        bar = self._action_bar
        bar.move(
            max((self.width() - bar.width()) // 2, 0),
            max(self.height() - bar.height() - 12, 0),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlays()
        self._drop_overlay.setGeometry(self.rect())

    # ---- 拖拽导入 ----

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop_overlay.setGeometry(self.rect())
            self._drop_overlay.raise_()
            self._drop_overlay.show()
            # 拖拽遮罩：透明度淡入（200ms，reduce_motion 时跳过）
            self._overlay_anim = fade_in(
                self._drop_overlay, duration=200,
                reduce_motion=self._reduce_motion,
            )
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._drop_overlay.hide()
        event.accept()

    def dropEvent(self, event):
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        self._drop_overlay.hide()
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
        else:
            event.ignore()

    # ---- 内部事件 ----

    def _on_selection_changed(self):
        ids = self.selected_doc_ids()
        self.documentSelected.emit(ids[0] if ids else None)
        self._update_action_bar()

    def _on_grid_selection_changed(self, doc_id):
        self.documentSelected.emit(doc_id)
        self._update_action_bar()

    def _on_context_menu(self, position):
        ids = self.selected_doc_ids()
        if not ids:
            return
        global_pos = self._table.viewport().mapToGlobal(position)
        self.contextMenuRequested.emit(global_pos, ids)
