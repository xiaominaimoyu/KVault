"""motion 动效模块测试。"""

from PySide6.QtCore import QParallelAnimationGroup
from PySide6.QtWidgets import QLabel

from gui.widgets.motion import fade_in, fade_slide_in


def test_fade_in_returns_none_when_reduce_motion():
    label = QLabel()
    assert fade_in(label, reduce_motion=True) is None


def test_fade_in_returns_animation_group():
    label = QLabel()
    group = fade_in(label, duration=200)
    assert isinstance(group, QParallelAnimationGroup)
    assert group.duration() == 200


def test_fade_in_sets_opacity_effect():
    label = QLabel()
    fade_in(label)
    assert label.graphicsEffect() is not None


def test_fade_slide_in_returns_none_when_reduce_motion():
    label = QLabel()
    assert fade_slide_in(label, reduce_motion=True) is None


def test_fade_slide_in_animation_duration():
    label = QLabel()
    group = fade_slide_in(label, duration=300, offset=12)
    assert isinstance(group, QParallelAnimationGroup)
    assert group.duration() == 300
    # 位移 + 透明度两条动画
    assert group.animationCount() == 2


def test_fade_slide_in_without_offset_single_animation():
    label = QLabel()
    group = fade_slide_in(label, duration=300, offset=0)
    assert group.animationCount() == 1
