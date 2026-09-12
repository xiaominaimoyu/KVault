"""动效工具模块。

遵循设计规范 6.x：时长 150-300ms、ease-out 缓动、
reduce_motion 时跳过动画直接显示。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


def _make_opacity_anim(
    effect: QGraphicsOpacityEffect, duration: int
) -> QPropertyAnimation:
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    return anim


def fade_in(widget: QWidget, duration: int = 200, reduce_motion: bool = False):
    """淡入动画（透明度 0 → 1）。

    Args:
        widget: 目标控件（须可见）。
        duration: 时长毫秒。
        reduce_motion: 为 True 时不做动画，返回 None。

    Returns:
        已启动的 QParallelAnimationGroup，reduce_motion 时为 None。
    """
    if reduce_motion:
        return None
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    group = QParallelAnimationGroup(widget)
    group.addAnimation(_make_opacity_anim(effect, duration))
    group.start(QAbstractAnimation.DeleteWhenStopped)
    return group


def fade_slide_in(
    widget: QWidget, duration: int = 300, offset: int = 0, reduce_motion: bool = False
):
    """淡入 + 上移动画（空状态出现：图标 + 文字上移淡入）。

    Args:
        widget: 目标控件。
        duration: 时长毫秒。
        offset: 上移像素数（0 则仅淡入）。
        reduce_motion: 为 True 时不做动画，返回 None。

    Returns:
        已启动的 QParallelAnimationGroup，reduce_motion 时为 None。
    """
    if reduce_motion:
        return None
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    group = QParallelAnimationGroup(widget)
    group.addAnimation(_make_opacity_anim(effect, duration))

    if offset:
        end_pos = widget.pos()
        pos_anim = QPropertyAnimation(widget, b"pos")
        pos_anim.setDuration(duration)
        pos_anim.setStartValue(end_pos + QPoint(0, offset))
        pos_anim.setEndValue(end_pos)
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(pos_anim)

    group.start(QAbstractAnimation.DeleteWhenStopped)
    return group
