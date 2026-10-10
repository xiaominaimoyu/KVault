"""DocListPanel 文档列表面板测试。"""

from types import SimpleNamespace

import pytest

from gui.panels.doc_list_panel import DocListPanel, format_size


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
def panel() -> DocListPanel:
    return DocListPanel()


def test_construction_columns(panel):
    headers = [
        panel._table.horizontalHeaderItem(i).text()
        for i in range(panel._table.columnCount())
    ]
    assert headers == ["文件名", "格式", "大小", "状态", "块数", "导入时间", "doc_id"]
    assert panel._table.isColumnHidden(6)
    assert panel._table.rowCount() == 0


def test_set_documents_populates_rows(panel):
    panel.set_documents([_doc(), _doc(id="d2", file_name="笔记.md", file_ext="md")])
    assert panel._table.rowCount() == 2
    assert panel._table.item(0, 0).text() == "季度报告.pdf"
    assert panel._table.item(1, 0).text() == "笔记.md"


def test_format_column_uses_badge_widget(panel):
    panel.set_documents([_doc()])
    widget = panel._table.cellWidget(0, 1)
    assert widget is not None
    assert widget.text() == "PDF"


def test_status_column_uses_status_cell(panel):
    panel.set_documents([_doc(status="failed")])
    cell = panel._table.cellWidget(0, 3)
    assert cell is not None
    assert cell._dot._status == "failed"
    assert cell._label.text() == "失败"


def test_empty_state_shown_when_no_documents(panel):
    panel.set_documents([])
    assert panel._empty_state is not None
    assert panel._stacked.currentWidget() is panel._empty_state


def test_table_shown_when_documents_exist(panel):
    panel.set_documents([_doc()])
    assert panel._stacked.currentWidget() is panel._table


def test_empty_state_cta_emits_import_requested(panel):
    emitted = []
    panel.importRequested.connect(lambda: emitted.append(True))
    panel._empty_state._cta_btn.click()
    assert emitted == [True]


# ---- P8 视图切换 ----

def test_default_view_mode_is_table(panel):
    assert panel.view_mode() == "table"


def test_set_view_mode_card_shows_grid(panel):
    panel.set_documents([_doc()])
    panel.set_view_mode("grid")
    assert panel.view_mode() == "grid"
    assert panel._stacked.currentWidget() is panel._grid


def test_set_view_mode_table_shows_table(panel):
    panel.set_documents([_doc()])
    panel.set_view_mode("grid")
    panel.set_view_mode("table")
    assert panel._stacked.currentWidget() is panel._table


def test_invalid_view_mode_ignored(panel):
    panel.set_view_mode("grid")
    panel.set_view_mode("bogus")
    assert panel.view_mode() == "grid"


def test_card_view_populates_grid(panel):
    panel.set_documents([_doc(), _doc(id="d2")])
    assert panel._grid.row_count() == 2


def test_card_view_shows_empty_state_when_no_docs(panel):
    panel.set_view_mode("grid")
    panel.set_documents([])
    assert panel._stacked.currentWidget() is panel._empty_state


def test_view_toggle_buttons_switch_mode(panel):
    panel.set_documents([_doc()])
    panel._card_view_btn.click()
    assert panel.view_mode() == "grid"
    panel._table_view_btn.click()
    assert panel.view_mode() == "table"


def test_selected_doc_ids_works_in_card_view(panel):
    panel.set_documents([_doc(), _doc(id="d2")])
    panel.set_view_mode("grid")
    assert panel._grid.select_doc("d2")
    assert panel.selected_doc_ids() == ["d2"]


# ---- P8 批量操作浮动条 ----

def test_action_bar_hidden_by_default(panel):
    assert panel._action_bar.isHidden()


def test_action_bar_hidden_when_single_selection(panel):
    panel.set_documents([_doc()])
    panel.select_doc("d1")
    assert panel._action_bar.isHidden()


def _select_both_rows(panel):
    """以 item 级选择模拟多选（selectRow 不累积）。"""
    panel._table.item(0, 0).setSelected(True)
    panel._table.item(1, 0).setSelected(True)


def test_action_bar_shown_when_multi_selection(panel):
    panel.set_documents([_doc(), _doc(id="d2")])
    _select_both_rows(panel)
    assert not panel._action_bar.isHidden()
    assert "已选 2 项" in panel._action_bar._info_label.text()


def test_action_bar_hidden_after_clear_selection(panel):
    panel.set_documents([_doc(), _doc(id="d2")])
    _select_both_rows(panel)
    panel.clear_selection()
    assert panel._action_bar.isHidden()


def test_batch_action_emits_signal_with_ids(panel):
    panel.set_documents([_doc(), _doc(id="d2")])
    _select_both_rows(panel)
    emitted = []
    panel.batchActionRequested.connect(lambda action, ids: emitted.append((action, ids)))
    panel._action_bar._action_buttons["delete"].click()
    assert emitted == [("delete", ["d1", "d2"])]


# ---- P8 拖拽导入 ----

def _make_drop_events():
    """构造拖拽事件。返回 (enter, drop, mime)，mime 需在事件使用期间保持引用。"""
    from PySide6.QtCore import QMimeData, QPointF, QPoint, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("C:/vault/a.pdf"), QUrl.fromLocalFile("C:/vault/b.md")])
    enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    return enter, drop, mime


def test_drop_overlay_hidden_by_default(panel):
    assert panel._drop_overlay.isHidden()


def test_drag_enter_shows_overlay(panel):
    enter, _, _mime = _make_drop_events()
    panel.dragEnterEvent(enter)
    assert not panel._drop_overlay.isHidden()


def test_drop_emits_files_dropped(panel):
    emitted = []
    panel.filesDropped.connect(lambda paths: emitted.append(paths))
    _, drop, _mime = _make_drop_events()
    panel.dropEvent(drop)
    assert emitted == [["C:/vault/a.pdf", "C:/vault/b.md"]]
    assert panel._drop_overlay.isHidden()


def test_drag_leave_hides_overlay(panel):
    from PySide6.QtGui import QDragLeaveEvent

    enter, _, _mime = _make_drop_events()
    panel.dragEnterEvent(enter)
    panel.dragLeaveEvent(QDragLeaveEvent())
    assert panel._drop_overlay.isHidden()


# ---- P9 动效集成 ----

def test_drag_enter_with_motion_creates_overlay_animation():
    animated = DocListPanel(reduce_motion=False)
    enter, _, _mime = _make_drop_events()
    animated.dragEnterEvent(enter)
    assert animated._overlay_anim is not None
    assert animated._overlay_anim.duration() == 200


def test_drag_enter_without_motion_no_animation():
    still = DocListPanel(reduce_motion=True)
    enter, _, _mime = _make_drop_events()
    still.dragEnterEvent(enter)
    assert still._overlay_anim is None
    assert not still._drop_overlay.isHidden()


def test_empty_state_fades_in_when_documents_cleared():
    animated = DocListPanel(reduce_motion=False)
    animated.set_documents([_doc()])
    animated.set_documents([])
    assert animated._stacked.currentWidget() is animated._empty_state
    assert animated._empty_anim is not None


def test_empty_state_no_animation_when_reduce_motion():
    still = DocListPanel(reduce_motion=True)
    still.set_documents([])
    assert still._empty_anim is None



def test_status_label_fallback_for_unknown_status(panel):
    panel.set_documents([_doc(status="weird")])
    cell = panel._table.cellWidget(0, 3)
    assert cell._label.text() == "weird"


def test_hidden_doc_id_column_stores_id(panel):
    panel.set_documents([_doc()])
    assert panel._table.item(0, 6).text() == "d1"


def test_no_selection_initially(panel):
    panel.set_documents([_doc()])
    assert panel.selected_doc_ids() == []


def test_select_doc_emits_document_selected(panel):
    emitted = []
    panel.documentSelected.connect(emitted.append)
    panel.set_documents([_doc(), _doc(id="d2")])
    panel.select_doc("d2")
    assert emitted[-1] == "d2"
    assert panel.selected_doc_ids() == ["d2"]


def test_select_doc_unknown_id_returns_false(panel):
    panel.set_documents([_doc()])
    assert panel.select_doc("nope") is False
    assert panel.selected_doc_ids() == []


def test_clear_selection_resets(panel):
    panel.set_documents([_doc()])
    panel.select_doc("d1")
    panel.clear_selection()
    assert panel.selected_doc_ids() == []


def test_context_menu_emits_doc_ids(panel):
    emitted = []
    panel.contextMenuRequested.connect(lambda pos, ids: emitted.append(ids))
    panel.set_documents([_doc(), _doc(id="d2")])
    panel.select_doc("d2")
    panel._table.customContextMenuRequested.emit(panel._table.viewport().rect().center())
    assert emitted == [["d2"]]


def test_context_menu_no_selection_no_emit(panel):
    emitted = []
    panel.contextMenuRequested.connect(lambda pos, ids: emitted.append(ids))
    panel.set_documents([_doc()])
    panel._table.customContextMenuRequested.emit(panel._table.viewport().rect().center())
    assert emitted == []


def test_format_size():
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
