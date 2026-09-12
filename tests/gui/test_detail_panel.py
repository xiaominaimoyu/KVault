"""DetailPanel 详情面板测试。"""

import pytest

from gui.panels.detail_panel import DetailPanel


@pytest.fixture
def panel() -> DetailPanel:
    return DetailPanel(default_top_k=5)


def test_construction_has_three_tabs(panel):
    labels = [panel.tabText(i) for i in range(panel.count())]
    assert labels == ["预览", "检索", "元数据"]


def test_sub_tabs_exposed(panel):
    assert panel.preview_tab is not None
    assert panel.search_tab is not None
    assert panel.metadata_tab is not None


def test_switch_to_search(panel):
    panel.switch_to_search()
    assert panel.currentIndex() == 1


def test_switch_to_preview(panel):
    panel.switch_to_search()
    panel.switch_to_preview()
    assert panel.currentIndex() == 0


def test_switch_to_metadata(panel):
    panel.switch_to_metadata()
    assert panel.currentIndex() == 2


def test_search_requested_forwarded(panel):
    emitted = []
    panel.searchRequested.connect(lambda q, k: emitted.append((q, k)))
    panel.search_tab._input.setText("查询")
    panel.search_tab._search_btn.click()
    assert emitted == [("查询", 5)]


def test_result_clicked_forwarded(panel):
    emitted = []
    panel.resultClicked.connect(emitted.append)
    sentinel = object()
    panel.search_tab.resultClicked.emit(sentinel)
    assert emitted == [sentinel]
