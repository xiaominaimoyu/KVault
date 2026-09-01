"""FormatBadge 格式徽章测试。"""

from gui.widgets.format_badge import FormatBadge


def test_construction_uppercases_ext():
    badge = FormatBadge("pdf")
    assert badge.text() == "PDF"


def test_object_name():
    badge = FormatBadge("docx")
    assert badge.objectName() == "FormatBadge"


def test_already_upper_ext_unchanged():
    badge = FormatBadge("MD")
    assert badge.text() == "MD"


def test_empty_ext():
    badge = FormatBadge("")
    assert badge.text() == ""
