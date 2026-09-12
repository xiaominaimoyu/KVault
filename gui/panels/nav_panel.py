"""左侧导航面板。

包含分区树、标签 pill 网格与可折叠状态摘要（工作区切换已由 TopNavBar 承担）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PanelSectionTitle")
    return label


class NavPanel(QWidget):
    """左侧导航面板。

    Signals:
        partitionSelected(object): 分区被点击，参数为分区 ID（str）或 None（所有文档）。
        tagSelected(object): 标签被点击，参数为标签 ID（str）或 None（全部标签）。
        partitionCreateRequested: 右键菜单请求新建分区。
        partitionRenameRequested(str): 右键菜单请求重命名分区。
        partitionDeleteRequested(str): 右键菜单请求删除分区。
        refreshStatsRequested: 请求刷新状态摘要。
    """

    partitionSelected = Signal(object)
    tagSelected = Signal(object)
    partitionCreateRequested = Signal()
    partitionRenameRequested = Signal(str)
    partitionDeleteRequested = Signal(str)
    refreshStatsRequested = Signal()

    def __init__(self, default_partition_id: str = "default", parent=None):
        super().__init__(parent)
        self.setObjectName("NavPanel")
        self._default_partition_id = default_partition_id
        self._current_partition_id: str | None = None
        self._current_tag_id: str | None = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 分区树
        layout.addWidget(_section_title("分区"))
        self._partition_tree = QTreeWidget()
        self._partition_tree.setHeaderHidden(True)
        self._partition_tree.itemClicked.connect(self._on_partition_clicked)
        self._partition_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._partition_tree.customContextMenuRequested.connect(
            self._on_partition_context_menu
        )
        layout.addWidget(self._partition_tree, 2)

        # 标签 pill 网格
        layout.addWidget(_section_title("标签"))
        self._tag_list = QListWidget()
        self._tag_list.setObjectName("TagPillList")
        self._tag_list.setFlow(QListWidget.LeftToRight)
        self._tag_list.setWrapping(True)
        self._tag_list.setResizeMode(QListWidget.Adjust)
        self._tag_list.itemClicked.connect(self._on_tag_clicked)
        layout.addWidget(self._tag_list, 1)

        # 可折叠状态摘要
        self._stats_card = QFrame()
        self._stats_card.setObjectName("StatsCard")
        card_layout = QVBoxLayout(self._stats_card)
        card_layout.setContentsMargins(12, 8, 12, 8)
        card_layout.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setSpacing(4)
        self._toggle_btn = QPushButton("▸")
        self._toggle_btn.setProperty("btnType", "icon")
        self._toggle_btn.setFixedSize(24, 24)
        self._toggle_btn.setToolTip("展开/折叠统计详情")
        self._toggle_btn.clicked.connect(self._toggle_stats_detail)
        header_row.addWidget(self._toggle_btn)

        self._summary_label = QLabel("")
        self._summary_label.setObjectName("StatsSummary")
        header_row.addWidget(self._summary_label, 1)

        self._refresh_btn = QPushButton("⟳")
        self._refresh_btn.setProperty("btnType", "icon")
        self._refresh_btn.setFixedSize(24, 24)
        self._refresh_btn.setToolTip("刷新状态")
        self._refresh_btn.clicked.connect(self.refreshStatsRequested.emit)
        header_row.addWidget(self._refresh_btn)

        card_layout.addLayout(header_row)

        self._detail_label = QLabel("")
        self._detail_label.setObjectName("StatsDetail")
        self._detail_label.setWordWrap(True)
        self._detail_label.setVisible(False)
        card_layout.addWidget(self._detail_label)

        layout.addWidget(self._stats_card)

    # ---- 数据填充 ----

    def set_partitions(self, partitions: list[dict], current_id: str | None = None):
        """填充分区树。

        Args:
            partitions: [{"id", "name", "doc_count"}, ...] 列表。
            current_id: 需选中的分区 ID；不匹配则选中"所有文档"。
        """
        self._partition_tree.clear()
        stats_total = sum(p.get("doc_count", 0) for p in partitions)

        all_item = QTreeWidgetItem(self._partition_tree)
        all_item.setText(0, f"所有文档 ({stats_total})")
        all_item.setData(0, Qt.UserRole, "")

        matched = False
        for p in partitions:
            item = QTreeWidgetItem(self._partition_tree)
            item.setText(0, f"{p['name']} ({p.get('doc_count', 0)})")
            item.setData(0, Qt.UserRole, p["id"])
            if current_id is not None and p["id"] == current_id:
                item.setSelected(True)
                matched = True

        if not matched:
            all_item.setSelected(True)
            self._current_partition_id = None
        else:
            self._current_partition_id = current_id
        self._partition_tree.expandAll()

    def set_tags(self, tags: list[dict], current_id: str | None = None):
        """填充标签 pill 网格。

        Args:
            tags: [{"id", "name", "doc_count"}, ...] 列表。
            current_id: 需选中的标签 ID；不匹配则选中"全部标签"。
        """
        self._tag_list.clear()
        all_item = QListWidgetItem("全部标签")
        all_item.setData(Qt.UserRole, "")
        self._tag_list.addItem(all_item)

        matched = False
        for t in tags:
            item = QListWidgetItem(f"#{t['name']} · {t.get('doc_count', 0)}")
            item.setData(Qt.UserRole, t["id"])
            self._tag_list.addItem(item)
            if current_id is not None and t["id"] == current_id:
                self._tag_list.setCurrentItem(item)
                matched = True

        if not matched:
            self._tag_list.setCurrentItem(all_item)
            self._current_tag_id = None
        else:
            self._current_tag_id = current_id

    def set_stats(self, summary: str, details: list[str] | None = None):
        """更新状态摘要与可选的展开详情。"""
        self._summary_label.setText(summary)
        if details:
            self._detail_label.setText("\n".join(details))

    # ---- 选中状态 ----

    def selected_partition_id(self) -> str | None:
        return self._current_partition_id

    def selected_tag_id(self) -> str | None:
        return self._current_tag_id

    def clear_selection(self):
        """清除分区与标签选中，回到"所有文档 / 全部标签"。"""
        self._partition_tree.clearSelection()
        self._tag_list.clearSelection()
        self._current_partition_id = None
        self._current_tag_id = None

    # ---- 内部事件 ----

    def _on_partition_clicked(self, item: QTreeWidgetItem, _column: int):
        self._current_partition_id = item.data(0, Qt.UserRole) or None
        self._current_tag_id = None
        self._tag_list.clearSelection()
        self.partitionSelected.emit(self._current_partition_id)

    def _on_tag_clicked(self, item: QListWidgetItem):
        self._current_tag_id = item.data(Qt.UserRole) or None
        self._current_partition_id = None
        self._partition_tree.clearSelection()
        self.tagSelected.emit(self._current_tag_id)

    def _toggle_stats_detail(self):
        # 按显式 hidden 状态取反，避免未显示窗口的歧义
        should_show = self._detail_label.isHidden()
        self._detail_label.setVisible(should_show)
        self._toggle_btn.setText("▾" if should_show else "▸")

    # ---- 分区右键菜单 ----

    def _on_partition_context_menu(self, position):
        item = self._partition_tree.itemAt(position)
        partition_id = item.data(0, Qt.UserRole) if item else ""
        menu = self._build_partition_menu(partition_id)
        menu.exec(self._partition_tree.mapToGlobal(position))

    def _build_partition_menu(self, partition_id: str) -> QMenu:
        """构建分区右键菜单（不弹出），供测试与右键处理复用。"""
        menu = QMenu(self)
        add_action = QAction("新建分区", menu)
        add_action.triggered.connect(self.partitionCreateRequested.emit)
        menu.addAction(add_action)

        if partition_id and partition_id != self._default_partition_id:
            rename_action = QAction("重命名分区", menu)
            rename_action.triggered.connect(
                lambda: self.partitionRenameRequested.emit(partition_id)
            )
            menu.addAction(rename_action)

            delete_action = QAction("删除分区", menu)
            delete_action.setProperty("danger", True)
            delete_action.triggered.connect(
                lambda: self.partitionDeleteRequested.emit(partition_id)
            )
            menu.addAction(delete_action)

        return menu
