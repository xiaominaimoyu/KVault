"""MetadataTab 元数据标签页测试。"""

import pytest

from gui.panels.metadata_tab import MetadataTab


@pytest.fixture
def tab() -> MetadataTab:
    return MetadataTab()


def test_construction_empty(tab):
    assert tab._table.rowCount() == 0


def test_set_metadata_populates_rows(tab):
    tab.set_metadata([
        ("文档 ID", "abc-123"),
        ("存储路径", "D:/vault/files/abc-123.pdf"),
        ("状态", "已索引"),
    ])
    assert tab._table.rowCount() == 3
    assert tab._table.item(0, 0).text() == "文档 ID"
    assert tab._table.item(1, 1).text() == "D:/vault/files/abc-123.pdf"


def test_set_metadata_replaces_previous(tab):
    tab.set_metadata([("A", "1")])
    tab.set_metadata([("B", "2"), ("C", "3")])
    assert tab._table.rowCount() == 2
    assert tab._table.item(0, 0).text() == "B"


def test_clear_metadata(tab):
    tab.set_metadata([("A", "1")])
    tab.set_metadata([])
    assert tab._table.rowCount() == 0


def test_path_rows_have_copy_button(tab):
    tab.set_metadata([
        ("文档 ID", "abc"),
        ("存储路径", "D:/vault/files/abc.pdf"),
    ])
    # 只有路径行提供复制按钮
    assert tab._table.cellWidget(0, 2) is None
    assert tab._table.cellWidget(1, 2) is not None


def test_copy_button_copies_to_clipboard(tab):
    from PySide6.QtWidgets import QApplication, QPushButton

    tab.set_metadata([("存储路径", "D:/vault/files/x.pdf")])
    container = tab._table.cellWidget(0, 2)
    btn = container.findChild(QPushButton)
    btn.click()
    QApplication.processEvents()
    assert QApplication.clipboard().text() == "D:/vault/files/x.pdf"
