"""NavPanel 左侧导航面板测试。

覆盖分区树、标签 pill 网格、可折叠状态摘要与全部对外信号。
"""

import pytest

from gui.panels.nav_panel import NavPanel


@pytest.fixture
def panel() -> NavPanel:
    return NavPanel()


def _click_partition(panel: NavPanel, index: int):
    item = panel._partition_tree.topLevelItem(index)
    panel._partition_tree.itemClicked.emit(item, 0)


def _click_tag(panel: NavPanel, index: int):
    item = panel._tag_list.item(index)
    panel._tag_list.itemClicked.emit(item)


def test_construction(panel):
    assert panel.objectName() == "NavPanel"


def test_set_partitions_populates_tree_with_all_item(panel):
    panel.set_partitions([
        {"id": "p1", "name": "分区一", "doc_count": 3},
        {"id": "p2", "name": "分区二", "doc_count": 5},
    ])
    # "所有文档" + 2 个分区
    assert panel._partition_tree.topLevelItemCount() == 3
    assert panel._partition_tree.topLevelItem(0).text(0).startswith("所有文档")


def test_set_partitions_defaults_to_all(panel):
    panel.set_partitions([{"id": "p1", "name": "A", "doc_count": 1}])
    assert panel.selected_partition_id() is None


def test_set_partitions_restores_current_id(panel):
    panel.set_partitions([{"id": "p1", "name": "A", "doc_count": 1}], current_id="p1")
    assert panel.selected_partition_id() == "p1"


def test_set_partitions_selects_all_when_current_id_missing(panel):
    panel.set_partitions([{"id": "p1", "name": "A", "doc_count": 1}], current_id="pX")
    assert panel.selected_partition_id() is None


def test_set_tags_populates_pill_grid(panel):
    panel.set_tags([
        {"id": "t1", "name": "python", "doc_count": 2},
        {"id": "t2", "name": "qt", "doc_count": 4},
    ])
    # "全部标签" + 2 个标签
    assert panel._tag_list.count() == 3
    assert panel._tag_list.item(0).text() == "全部标签"


def test_set_tags_defaults_to_all(panel):
    panel.set_tags([{"id": "t1", "name": "python", "doc_count": 2}])
    assert panel.selected_tag_id() is None


def test_set_tags_restores_current_id(panel):
    panel.set_tags([{"id": "t1", "name": "python", "doc_count": 2}], current_id="t1")
    assert panel.selected_tag_id() == "t1"


def test_partition_click_emits_partition_selected(panel):
    emitted = []
    panel.partitionSelected.connect(emitted.append)
    panel.set_partitions([{"id": "p1", "name": "A", "doc_count": 1}])
    _click_partition(panel, 1)
    assert emitted == ["p1"]


def test_all_documents_click_emits_none(panel):
    emitted = []
    panel.partitionSelected.connect(emitted.append)
    panel.set_partitions([{"id": "p1", "name": "A", "doc_count": 1}])
    _click_partition(panel, 0)
    assert emitted == [None]


def test_partition_click_clears_tag_selection(panel):
    panel.set_tags([{"id": "t1", "name": "python", "doc_count": 2}], current_id="t1")
    panel.set_partitions([{"id": "p1", "name": "A", "doc_count": 1}])
    _click_partition(panel, 1)
    assert panel.selected_tag_id() is None


def test_tag_click_emits_tag_selected(panel):
    emitted = []
    panel.tagSelected.connect(emitted.append)
    panel.set_tags([{"id": "t1", "name": "python", "doc_count": 2}])
    _click_tag(panel, 1)
    assert emitted == ["t1"]


def test_all_tags_click_emits_none(panel):
    emitted = []
    panel.tagSelected.connect(emitted.append)
    panel.set_tags([{"id": "t1", "name": "python", "doc_count": 2}])
    _click_tag(panel, 0)
    assert emitted == [None]


def test_tag_click_clears_partition_selection(panel):
    panel.set_partitions([{"id": "p1", "name": "A", "doc_count": 1}], current_id="p1")
    panel.set_tags([{"id": "t1", "name": "python", "doc_count": 2}])
    _click_tag(panel, 1)
    assert panel.selected_partition_id() is None


def test_clear_selection(panel):
    panel.set_partitions([{"id": "p1", "name": "A", "doc_count": 1}], current_id="p1")
    panel.set_tags([{"id": "t1", "name": "python", "doc_count": 2}], current_id="t1")
    panel.clear_selection()
    assert panel.selected_partition_id() is None
    assert panel.selected_tag_id() is None


def test_set_stats_updates_summary(panel):
    panel.set_stats("12 文档 · 340 块", ["总文档数: 12", "总块数: 340"])
    assert panel._summary_label.text() == "12 文档 · 340 块"


def test_stats_detail_collapsed_by_default(panel):
    """§3.2 状态详情默认折叠。"""
    panel.set_stats("3 文档 · 12 块", ["已索引: 3", "失败: 0", "向量数: 12"])
    assert panel.is_detail_expanded() is False


def test_stats_detail_expands_on_toggle(panel):
    """§3.2 展开为 4 行详细统计。"""
    panel.set_stats(
        "3 文档 · 12 块",
        ["已索引: 3", "失败: 0", "向量数: 12", "分区: 4 · 标签: 2"],
    )
    panel._toggle_stats_detail()

    assert panel.is_detail_expanded() is True
    assert len(panel._detail_labels) == 4
    assert panel._detail_labels[0].text() == "已索引: 3"
    assert panel._detail_labels[3].text() == "分区: 4 · 标签: 2"


def test_summary_label_click_toggles(panel):
    """§3.2 点击摘要行本身也能展开。"""
    panel.set_stats("3 文档", ["已索引: 3"])
    assert panel.is_detail_expanded() is False
    panel._summary_label.clicked.emit()
    assert panel.is_detail_expanded() is True


def test_set_stats_without_details_keeps_summary(panel):
    panel.set_stats("只有摘要")
    assert panel._summary_label.text() == "只有摘要"


def test_partition_rows_have_folder_icons(panel):
    """§3.2 分区行应带图标。"""
    from PySide6.QtCore import Qt

    panel.set_partitions([{"id": "p1", "name": "技术笔记", "doc_count": 3}])
    tree = panel._partition_tree
    assert tree.topLevelItemCount() == 2  # 所有文档 + 1 个分区
    item = tree.topLevelItem(1)
    assert not item.icon(0).isNull()
    assert item.data(0, Qt.UserRole) == "p1"


def test_empty_states_shown_when_no_data(panel):
    """§7.1 分区树与标签区的空状态引导。"""
    panel.set_partitions([])
    panel.set_tags([])

    assert panel._partition_empty.isHidden() is False
    assert "还没有分区" in panel._partition_empty.text()
    assert panel._tag_empty.isHidden() is False
    assert "还没有标签" in panel._tag_empty.text()


def test_partition_rows_have_folder_icons(panel):
    """§3.2 分区行应带图标。"""
    from PySide6.QtCore import Qt

    panel.set_partitions([{"id": "p1", "name": "技术笔记", "doc_count": 3}])
    tree = panel._partition_tree
    assert tree.topLevelItemCount() == 2  # 所有文档 + 1 个分区
    item = tree.topLevelItem(1)
    assert not item.icon(0).isNull()
    assert item.data(0, Qt.UserRole) == "p1"


def test_empty_states_shown_when_no_data(panel):
    """§7.1 分区树与标签区的空状态引导。"""
    panel.set_partitions([])
    panel.set_tags([])

    assert panel._partition_empty.isHidden() is False
    assert "还没有分区" in panel._partition_empty.text()
    assert panel._tag_empty.isHidden() is False
    assert "还没有标签" in panel._tag_empty.text()


def test_collapse_toggles_width(panel):
    """§3.1 导航可折叠至 48px 图标栏。"""
    from gui.panels.nav_panel import COLLAPSED_WIDTH, EXPANDED_WIDTH

    assert panel.is_collapsed() is False
    panel.toggle_collapsed()
    assert panel.is_collapsed() is True
    assert panel.width() == COLLAPSED_WIDTH

    panel.toggle_collapsed()
    assert panel.is_collapsed() is False
    assert panel.width() == EXPANDED_WIDTH
