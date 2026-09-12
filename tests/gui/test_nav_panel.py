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
    panel.set_stats("12 文档 · 340 块", ["总文档数: 12"])
    assert panel._detail_label.isHidden()


def test_stats_detail_expands_on_toggle(panel):
    panel.set_stats("12 文档 · 340 块", ["总文档数: 12"])
    panel._toggle_btn.click()
    assert not panel._detail_label.isHidden()
    panel._toggle_btn.click()
    assert panel._detail_label.isHidden()


def test_refresh_button_emits_signal(panel):
    emitted = []
    panel.refreshStatsRequested.connect(lambda: emitted.append(True))
    panel._refresh_btn.click()
    assert emitted == [True]


def test_partition_context_menu_actions_emit_signals(panel):
    created, renamed, deleted = [], [], []
    panel.partitionCreateRequested.connect(lambda: created.append(True))
    panel.partitionRenameRequested.connect(renamed.append)
    panel.partitionDeleteRequested.connect(deleted.append)

    menu = panel._build_partition_menu("p1")
    texts = [a.text() for a in menu.actions()]
    assert "新建分区" in texts
    assert "重命名分区" in texts
    assert "删除分区" in texts

    for action in menu.actions():
        action.trigger()
    assert created == [True]
    assert renamed == ["p1"]
    assert deleted == ["p1"]


def test_default_partition_has_no_rename_delete(panel):
    menu = panel._build_partition_menu("default")
    texts = [a.text() for a in menu.actions()]
    assert "新建分区" in texts
    assert "重命名分区" not in texts
    assert "删除分区" not in texts


def test_no_context_partition_menu_has_create_only(panel):
    menu = panel._build_partition_menu("")
    texts = [a.text() for a in menu.actions()]
    assert texts == ["新建分区"]


def test_set_stats_without_details_keeps_summary(panel):
    panel.set_stats("12 文档 · 340 块")
    assert panel._summary_label.text() == "12 文档 · 340 块"
    assert panel._detail_label.isHidden()
