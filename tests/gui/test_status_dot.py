"""StatusDot 状态指示点测试。"""

from gui.widgets.status_dot import StatusDot


def test_status_dot_construction():
    dot = StatusDot("pending", reduce_motion=True)
    assert dot.width() == 8
    assert dot.height() == 8


def test_status_dot_set_status():
    dot = StatusDot("pending", reduce_motion=True)
    dot.set_status("indexed")
    assert dot._status == "indexed"
    dot.set_status("failed")
    assert dot._status == "failed"


def test_status_dot_no_pulse_with_reduce_motion():
    dot = StatusDot("indexing", reduce_motion=True)
    assert dot._pulse_animation is None


def test_status_dot_color_mapping():
    dot = StatusDot("indexed", reduce_motion=True)
    color = dot.get_color()
    assert color is not None
    assert color.red() > 0 or color.green() > 0

    dot.set_status("failed")
    color = dot.get_color()
    assert color is not None


def test_status_dot_opacity_property():
    dot = StatusDot("pending", reduce_motion=True)
    assert dot.opacity == 1.0
    dot.opacity = 0.5
    assert dot.opacity == 0.5
