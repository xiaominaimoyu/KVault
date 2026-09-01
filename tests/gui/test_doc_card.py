"""DocCard 文档卡片控件测试。"""

from types import SimpleNamespace

from gui.widgets.doc_card import DocCard


def _doc(**overrides) -> SimpleNamespace:
    defaults = dict(
        id="d1",
        file_name="季度报告.pdf",
        file_ext="pdf",
        file_size=2048,
        status="indexed",
        chunk_count=5,
        created_at=1700000000.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_construction_shows_core_fields():
    card = DocCard(_doc())
    assert card._badge.text() == "PDF"
    assert card._name_label.text() == "季度报告.pdf"
    assert card._dot._status == "indexed"
    # 元信息行包含大小与块数
    assert "2.0 KB" in card._meta_label.text()
    assert "5 块" in card._meta_label.text()


def test_card_width_is_220():
    card = DocCard(_doc())
    assert card.minimumWidth() >= 200


def test_name_label_wraps_two_lines():
    card = DocCard(_doc())
    assert card._name_label.wordWrap()


def test_set_selected_property():
    card = DocCard(_doc())
    assert not card.property("selected")
    card.set_selected(True)
    assert card.property("selected")


def test_object_name_for_qss():
    card = DocCard(_doc())
    assert card.objectName() == "DocCard"


def test_doc_id_attribute():
    card = DocCard(_doc())
    assert card.doc_id == "d1"
