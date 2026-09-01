"""TopNavBar 顶部导航栏测试。"""

from unittest.mock import MagicMock

from gui.panels.top_nav_bar import TopNavBar


def _make_config():
    config = MagicMock()
    config.theme = "dark"
    return config


def test_top_nav_bar_construction():
    config = _make_config()
    nav = TopNavBar(config)
    assert nav.height() == 56
    assert nav.objectName() == "TopNavBar"


def test_set_workspaces():
    config = _make_config()
    nav = TopNavBar(config)
    nav.set_workspaces([("ws1", "工作区1"), ("ws2", "工作区2")], "ws2")
    assert nav._workspace_combo.count() == 2
    assert nav._workspace_combo.currentData() == "ws2"


def test_set_doc_count_badge():
    config = _make_config()
    nav = TopNavBar(config)
    nav.set_doc_count_badge(12)
    assert "12" in nav._doc_count_badge.text()
    nav.set_doc_count_badge(0)
    assert nav._doc_count_badge.text() == ""


def test_focus_global_search():
    from PySide6.QtWidgets import QApplication

    config = _make_config()
    nav = TopNavBar(config)
    nav.show()
    nav.activateWindow()
    QApplication.processEvents()
    nav.focus_global_search()
    QApplication.processEvents()
    assert nav._search_box.hasFocus()


def test_get_search_text():
    config = _make_config()
    nav = TopNavBar(config)
    nav._search_box.setText("test query")
    assert nav.get_search_text() == "test query"


def test_search_box_min_width():
    config = _make_config()
    nav = TopNavBar(config)
    assert nav._search_box.minimumWidth() >= 320


# ---- P10 图标系统 ----

def test_import_button_has_lucide_icon():
    config = _make_config()
    nav = TopNavBar(config)
    assert not nav._import_btn.icon().isNull()


def test_settings_button_uses_icon_not_emoji():
    config = _make_config()
    nav = TopNavBar(config)
    assert not nav._settings_btn.icon().isNull()
    assert nav._settings_btn.text() == ""


def test_logs_button_uses_icon_not_emoji():
    config = _make_config()
    nav = TopNavBar(config)
    assert not nav._logs_btn.icon().isNull()
    assert nav._logs_btn.text() == ""