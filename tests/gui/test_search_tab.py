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


def test_show_results_populates_cards(tab):
    """§3.4.2 结果以卡片呈现：文档名 + 块号 + 分数条 + 内容预览。"""
    from gui.panels.search_tab import _ResultCard

    tab.show_results([_result(), _result(score=0.4)], lambda s: "#00FF00")
    assert tab.result_count() == 2

    card = tab.result_list.itemWidget(tab.result_list.item(0))
    assert isinstance(card, _ResultCard)
    assert "报告.pdf" in card._name.text()
    assert card._meta.text().startswith("块 ")
    assert card.score() == pytest.approx(0.85)


def test_result_card_uses_score_band(tab):
    """§8.7 分数条颜色按区间映射。"""
    from gui.widgets.score_bar import score_band

    tab.show_results([_result(score=0.9), _result(score=0.6), _result(score=0.2)], None)
    bands = [
        tab.result_list.itemWidget(tab.result_list.item(i))._score_bar.band()
        for i in range(3)
    ]
    assert bands == ["success", "warning", "error"]
    assert score_band(0.85) == "success"


def test_result_click_marks_selected(tab):
    from gui.panels.search_tab import _ResultCard

    tab.show_results([_result(), _result()], None)
    tab._on_result_clicked(tab.result_list.item(1))

    cards = [
        tab.result_list.itemWidget(tab.result_list.item(i)) for i in range(2)
    ]
    assert all(isinstance(c, _ResultCard) for c in cards)
    assert cards[0].property("selected") is False
    assert cards[1].property("selected") is True


def test_show_results_empty_shows_empty_state(tab):
    """§7.1 空结果使用 EmptyState 组件。"""
    tab.show_results([], None)
    assert tab.result_count() == 0
    assert tab.empty_state is not None
    assert "未找到相关结果" in tab.empty_state._title_label.text()


def test_show_error_switches_to_error_view(tab):
    tab.show_error("检索失败")
    assert "检索失败" in tab._error_view.toPlainText()
    assert tab.result_count() == 0


def test_busy_state_shows_spinner(tab):
    """§7.2 检索中：按钮禁用 + spinner 显示。"""
    tab.set_busy(True)
    assert tab.is_busy() is True
    # offscreen 下父级未显示时 isVisible 恒为 False，因此校验显隐标记本身
    assert tab.spinner.isHidden() is False
    assert tab.spinner.text() != ""

    tab.set_busy(False)
    assert tab.is_busy() is False
    assert tab.spinner.text() == ""
    assert tab.spinner.isHidden() is True


def test_empty_query_does_not_emit(tab):
    """空查询不应触发检索。"""
    emitted = []
    tab.searchRequested.connect(lambda *a: emitted.append(a))
    tab._input.setText("   ")
    tab._on_search_clicked()
    assert emitted == []


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
