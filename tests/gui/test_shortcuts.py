"""ShortcutManager 键盘快捷键测试。"""

from unittest.mock import MagicMock

from PySide6.QtWidgets import QWidget

from gui.shortcuts import DEFAULT_SHORTCUTS, ShortcutManager


def _all_handlers():
    return {key: MagicMock() for key in DEFAULT_SHORTCUTS}


def test_default_shortcuts_cover_design_doc():
    expected = {
        "import_docs": "Ctrl+I",
        "focus_global_search": "Ctrl+F",
        "focus_semantic_search": "Ctrl+K",
        "open_settings": "Ctrl+S",
        "refresh_status": "Ctrl+R",
        "delete_selected": "Delete",
        "clear_selection": "Esc",
        "tab_preview": "Ctrl+1",
        "tab_search": "Ctrl+2",
        "tab_metadata": "Ctrl+3",
    }
    for action_id, key in expected.items():
        assert DEFAULT_SHORTCUTS[action_id] == key, f"{action_id} 应为 {key}"


def test_manager_registers_all_shortcuts():
    parent = QWidget()
    handlers = _all_handlers()
    manager = ShortcutManager(parent, handlers)
    assert set(manager.shortcuts.keys()) == set(handlers.keys())


def test_activated_calls_handler():
    parent = QWidget()
    handlers = _all_handlers()
    manager = ShortcutManager(parent, handlers)
    manager.shortcuts["import_docs"].activated.emit()
    handlers["import_docs"].assert_called_once()


def test_missing_handlers_are_skipped():
    parent = QWidget()
    handlers = {"import_docs": MagicMock()}
    manager = ShortcutManager(parent, handlers)
    assert set(manager.shortcuts.keys()) == {"import_docs"}


def test_shortcut_key_sequences():
    parent = QWidget()
    handlers = _all_handlers()
    manager = ShortcutManager(parent, handlers)
    from PySide6.QtGui import QKeySequence

    assert (
        manager.shortcuts["delete_selected"].key().toString()
        == QKeySequence("Delete").toString()
    )
    assert (
        manager.shortcuts["tab_metadata"].key().toString()
        == QKeySequence("Ctrl+3").toString()
    )
