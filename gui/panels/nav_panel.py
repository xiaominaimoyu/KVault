"""左侧导航面板。

对应设计文档 §3.2：

1. 分区树（主体）—— 每行：图标 + 名称 + 文档数
2. 标签区 —— 标签 pill 网格
3. 状态摘要（底部）—— 默认折叠为一行摘要，点击展开为 4 行详细统计

另实现 §3.1 要求的可折叠：折叠后收为 48px 图标栏。
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

from gui.styles.icons import icon

#: §3.1 折叠后的图标栏宽度
COLLAPSED_WIDTH = 48

#: §3.1 展开后的导航宽度
EXPANDED_WIDTH = 260


class _ClickableLabel(QLabel):
    """可点击的 QLabel。

    不能在实例上直接赋值 ``mousePressEvent``——那会用 Python 函数替换绑定方法，
    在 Qt 的事件分发中会导致访问冲突。这里改为正规子类。
    """

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt 接口命名
        self.clicked.emit()
        super().mousePressEvent(event)


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
        self._collapsed = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 折叠按钮（§3.1）
        self._collapse_btn = QPushButton("«")
        self._collapse_btn.setObjectName("NavCollapseButton")
        self._collapse_btn.setFixedSize(24, 24)
        self._collapse_btn.setToolTip("折叠导航面板")
        self._collapse_btn.clicked.connect(self.toggle_collapsed)
        layout.addWidget(self._collapse_btn, 0, Qt.AlignRight)

        # §7.1 分区树空状态占位
        self._partition_empty = QLabel("还没有分区\n右键新建分区来组织文档")
        self._partition_empty.setObjectName("EmptyStateSubtitle")
        self._partition_empty.setAlignment(Qt.AlignCenter)
        self._partition_empty.setWordWrap(True)
        self._partition_empty.setVisible(False)
        layout.addWidget(self._partition_empty)

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

        # §7.1 标签区空状态占位
        self._tag_empty = QLabel("还没有标签\n在文档右键菜单中添加标签")
        self._tag_empty.setObjectName("EmptyStateSubtitle")
        self._tag_empty.setAlignment(Qt.AlignCenter)
        self._tag_empty.setWordWrap(True)
        self._tag_empty.setVisible(False)
        layout.addWidget(self._tag_empty)

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

        # §3.2 点击摘要本身也能展开
        self._summary_label = _ClickableLabel("")
        self._summary_label.setObjectName("StatsSummary")
        self._summary_label.setToolTip("点击展开统计详情")
        self._summary_label.setCursor(Qt.PointingHandCursor)
        self._summary_label.clicked.connect(self._toggle_stats_detail)
        header_row.addWidget(self._summary_label, 1)

        self._refresh_btn = QPushButton("⟳")
        self._refresh_btn.setProperty("btnType", "icon")
        self._refresh_btn.setFixedSize(24, 24)
        self._refresh_btn.setToolTip("刷新状态")
        self._refresh_btn.clicked.connect(self.refreshStatsRequested.emit)
        header_row.addWidget(self._refresh_btn)

        card_layout.addLayout(header_row)

        # §3.2 展开为 4 行详细统计（每行独立标签，而非拼成一段）
        self._detail_container = QWidget()
        detail_layout = QVBoxLayout(self._detail_container)
        detail_layout.setContentsMargins(0, 4, 0, 0)
        detail_layout.setSpacing(2)

        self._detail_labels: list[QLabel] = []
        for _ in range(4):
            row = QLabel("")
            row.setObjectName("StatsDetail")
            row.setVisible(False)
            self._detail_labels.append(row)
            detail_layout.addWidget(row)

        self._detail_container.setVisible(False)
        card_layout.addWidget(self._detail_container)

        layout.addWidget(self._stats_card)

    def _on_summary_clicked(self, event) -> None:
        """点击摘要行触发展开。"""
        self._toggle_stats_detail()
        del event

    # ---- 数据填充 ----

    def set_partitions(self, partitions: list[dict], current_id: str | None = None):
        """填充分区树。

        Args:
            partitions: [{"id", "name", "doc_count"}, ...] 列表。
            current_id: 需选中的分区 ID；不匹配则选中"所有文档"。
        """
        self._partition_tree.clear()
        stats_total = sum(p.get("doc_count", 0) for p in partitions)

        # §7.1 没有分区时显示引导文案
        has_partitions = bool(partitions)
        self._partition_empty.setVisible(not has_partitions)
        self._partition_tree.setVisible(has_partitions)

        all_item = QTreeWidgetItem(self._partition_tree)
        all_item.setText(0, f"所有文档 ({stats_total})")
        all_item.setIcon(0, icon("database", size=14))
        all_item.setData(0, Qt.UserRole, "")

        matched = False
        for p in partitions:
            item = QTreeWidgetItem(self._partition_tree)
            item.setText(0, f"{p['name']} ({p.get('doc_count', 0)})")
            # §3.2 每行：图标 + 名称 + 文档数
            item.setIcon(0, icon("folder", size=14))
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

        # §7.1 没有标签时显示引导文案
        has_tags = bool(tags)
        self._tag_empty.setVisible(not has_tags)
        self._tag_list.setVisible(has_tags)
        if not has_tags:
            self._current_tag_id = None
            return

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
        """更新状态摘要与可选的展开详情（§3.2 展开为 4 行）。"""
        self._summary_label.setText(summary)

        # 归一化为 4 行，多余的合并进最后一行
        rows = list(details or [])[:4]
        while len(rows) < 4:
            rows.append("")
        for label, text in zip(self._detail_labels, rows):
            label.setText(text)
            label.setVisible(bool(text) and not self._detail_container.isHidden())

    def is_detail_expanded(self) -> bool:
        """统计详情是否处于展开态。"""
        return not self._detail_container.isHidden()

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
        """展开/折叠统计详情。"""
        should_show = self._detail_container.isHidden()
        self._detail_container.setVisible(should_show)
        for label in self._detail_labels:
            label.setVisible(should_show and bool(label.text()))
        self._toggle_btn.setText("▾" if should_show else "▸")

    # ---- §3.1 折叠为 48px 图标栏 ----

    def toggle_collapsed(self) -> None:
        """折叠 / 展开导航面板（§3.1 图标栏模式）。"""
        self._collapsed = not self._collapsed
        self.setFixedWidth(COLLAPSED_WIDTH if self._collapsed else EXPANDED_WIDTH)

        self._collapse_btn.setText("»" if self._collapsed else "«")
        self._collapse_btn.setToolTip(
            "展开导航面板" if self._collapsed else "折叠导航面板"
        )

        # 折叠时隐藏文字性内容，仅保留可交互的控件
        self._partition_tree.setVisible(not self._collapsed and bool(self._partition_tree.topLevelItemCount()))
        self._tag_list.setVisible(not self._collapsed and self._tag_list.count() > 0)
        self._stats_card.setVisible(not self._collapsed)
        self._partition_empty.setVisible(not self._collapsed and self._partition_empty.text() != "")
        self._tag_empty.setVisible(not self._collapsed and self._tag_empty.text() != "")

    def is_collapsed(self) -> bool:
        """是否处于折叠态。"""
        return self._collapsed

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
