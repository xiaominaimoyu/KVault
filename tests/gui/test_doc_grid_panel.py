"""DocGridPanel 卡片网格视图测试。"""

from types import SimpleNamespace

import pytest

from gui.panels.doc_grid_panel import DocGridPanel


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


@pytest.fixture
def grid() -> DocGridPanel:
    return DocGridPanel()


def test_set_documents_creates_cards(grid):
    grid.set_documents([_doc(), _doc(id="d2", file_name="笔记.md", file_ext="md")])
    assert grid.row_count() == 2
    assert grid._list.count() == 2


def test_selected_doc_ids_from_cards(grid):
    grid.set_documents([_doc(), _doc(id="d2")])
    grid._list.item(1).setSelected(True)
    assert grid.selected_doc_ids() == ["d2"]


def test_select_doc_by_id(grid):
    grid.set_documents([_doc(), _doc(id="d2")])
    assert grid.select_doc("d2")
    assert grid.selected_doc_ids() == ["d2"]


def test_select_missing_doc_returns_false(grid):
    grid.set_documents([_doc()])
    assert not grid.select_doc("nope")


def test_clear_selection(grid):
    grid.set_documents([_doc()])
    grid.select_doc("d1")
    grid.clear_selection()
    assert grid.selected_doc_ids() == []


def test_selection_changed_emits_document_selected(grid):
    emitted = []
    grid.documentSelected.connect(lambda doc_id: emitted.append(doc_id))
    grid.set_documents([_doc()])
    grid._list.item(0).setSelected(True)
    assert emitted == ["d1"]


def test_selection_cleared_emits_none(grid):
    emitted = []
    grid.documentSelected.connect(lambda doc_id: emitted.append(doc_id))
    grid.set_documents([_doc()])
    grid._list.item(0).setSelected(True)
    grid._list.clearSelection()
    assert emitted[-1] is None
