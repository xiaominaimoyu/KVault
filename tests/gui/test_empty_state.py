"""EmptyState 空状态占位控件测试。"""

import pytest

from gui.widgets.empty_state import EmptyState


def test_construction_texts():
    es = EmptyState("📭", "暂无文档", "点击导入按钮添加你的第一份文档")
    assert es._icon_label.text() == "📭"
    assert es._title_label.text() == "暂无文档"
    assert es._subtitle_label.text() == "点击导入按钮添加你的第一份文档"


def test_no_cta_button_by_default():
    es = EmptyState("📭", "暂无文档", "副文案")
    assert es._cta_btn is None


def test_cta_button_shown_when_text_given():
    es = EmptyState("📭", "暂无文档", "副文案", cta_text="导入文档")
    assert es._cta_btn is not None
    assert es._cta_btn.text() == "导入文档"


def test_cta_clicked_emits_signal():
    es = EmptyState("📭", "暂无文档", "副文案", cta_text="导入文档")
    emitted = []
    es.ctaClicked.connect(lambda: emitted.append(True))
    es._cta_btn.click()
    assert emitted == [True]


def test_set_texts_updates_labels():
    es = EmptyState("a", "b", "c")
    es.set_texts("x", "y", "z")
    assert es._icon_label.text() == "x"
    assert es._title_label.text() == "y"
    assert es._subtitle_label.text() == "z"
