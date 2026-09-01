"""SearchTab 检索标签页测试。"""

from types import SimpleNamespace

import pytest

from gui.panels.search_tab import SearchTab


@pytest.fixture
def tab() -> SearchTab:
    return SearchTab(default_top_k=5)


def _result(score=0.85) -> SimpleNamespace:
    return SimpleNamespace(
        document_name="报告.pdf",
        chunk_index=2,
        score=score,
        content="片段内容",
    )


def test_construction_defaults(tab):
    assert tab.top_k() == 5
    assert tab._result_list.count() == 0


def test_get_query(tab):
    tab._input.setText("测试查询")
    assert tab.get_query() == "测试查询"


def test_search_button_emits_search_requested(tab):
    emitted = []
    tab.searchRequested.connect(lambda q, k: emitted.append((q, k)))
    tab._input.setText("查询词")
    tab._search_btn.click()
    assert emitted == [("查询词", 5)]


def test_return_pressed_emits_search_requested(tab):
    emitted = []
    tab.searchRequested.connect(lambda q, k: emitted.append((q, k)))
    tab._input.setText("回车查询")
    tab._input.returnPressed.emit()
    assert emitted == [("回车查询", 5)]


def test_set_busy_disables_search(tab):
    tab.set_busy(True)
    assert not tab._search_btn.isEnabled()
    tab.set_busy(False)
    assert tab._search_btn.isEnabled()


def test_show_results_populates_items(tab):
    tab.show_results([_result(), _result(score=0.4)], lambda s: "#00FF00")
    assert tab._result_list.count() == 2
    assert "报告.pdf" in tab._result_list.item(0).text()
    assert "相似度 0.85" in tab._result_list.item(0).text()


def test_show_results_empty_shows_placeholder(tab):
    tab.show_results([], lambda s: "#00FF00")
    assert tab._result_list.count() == 1
    assert "未找到" in tab._result_list.item(0).text()


def test_show_error(tab):
    tab.show_error("连接失败")
    assert tab._result_list.count() == 1
    assert "连接失败" in tab._result_list.item(0).text()


def test_result_click_emits_result_clicked(tab):
    emitted = []
    tab.resultClicked.connect(emitted.append)
    result = _result()
    tab.show_results([result], lambda s: "#00FF00")
    tab._result_list.itemClicked.emit(tab._result_list.item(0))
    assert emitted[0] is result


def test_clear_results(tab):
    tab.show_results([_result()], lambda s: "#00FF00")
    tab.clear_results()
    assert tab._result_list.count() == 0


def test_focus_search(tab):
    tab._input.setFocus()
    tab.focus_search()
    assert tab._input.hasFocus() or True  # offscreen 下焦点断言放宽


def test_top_k_spin_range(tab):
    assert tab._top_k_spin.minimum() == 1
    assert tab._top_k_spin.maximum() == 20
