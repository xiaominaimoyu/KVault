"""FloatingActionBar 批量操作浮动工具条测试。"""

from gui.widgets.floating_action_bar import FloatingActionBar


def test_construction_with_actions():
    bar = FloatingActionBar([("delete", "删除"), ("export", "导出")])
    assert len(bar._action_buttons) == 2
    assert bar._action_buttons["delete"].text() == "删除"
    assert bar._action_buttons["export"].text() == "导出"


def test_button_click_emits_action_triggered():
    bar = FloatingActionBar([("delete", "删除")])
    emitted = []
    bar.actionTriggered.connect(lambda action: emitted.append(action))
    bar._action_buttons["delete"].click()
    assert emitted == ["delete"]


def test_clear_removes_buttons():
    bar = FloatingActionBar([("delete", "删除")])
    bar.clear()
    assert len(bar._action_buttons) == 0


def test_set_actions_replaces_existing():
    bar = FloatingActionBar([("delete", "删除")])
    bar.set_actions([("reindex", "重建索引")])
    assert list(bar._action_buttons.keys()) == ["reindex"]
    assert "delete" not in bar._action_buttons


def test_set_action_enabled_toggles_button():
    bar = FloatingActionBar([("delete", "删除")])
    bar.set_action_enabled("delete", False)
    assert not bar._action_buttons["delete"].isEnabled()
    bar.set_action_enabled("delete", True)
    assert bar._action_buttons["delete"].isEnabled()


def test_object_name_for_qss():
    bar = FloatingActionBar([])
    assert bar.objectName() == "FloatingActionBar"


def test_set_info_text_updates_label():
    bar = FloatingActionBar([("delete", "删除")])
    bar.set_info_text("已选 3 项")
    assert bar._info_label.text() == "已选 3 项"
