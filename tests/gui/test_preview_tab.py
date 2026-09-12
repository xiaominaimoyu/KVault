"""PreviewTab 预览标签页测试。"""

import pytest

from gui.panels.preview_tab import PreviewTab


@pytest.fixture
def tab() -> PreviewTab:
    return PreviewTab()


def test_construction_empty(tab):
    assert tab._browser.toPlainText() == ""


def test_set_html(tab):
    tab.set_html("<h2>文档</h2><p>内容</p>")
    assert "文档" in tab._browser.toPlainText()


def test_clear(tab):
    tab.set_html("<p>内容</p>")
    tab.clear_preview()
    assert tab._browser.toPlainText() == ""


def test_append_hit_chunk(tab):
    tab.set_html("<p>正文</p>")
    tab.append_hit_chunk("<p>命中块</p>")
    text = tab._browser.toPlainText()
    assert "正文" in text
    assert "命中块" in text
