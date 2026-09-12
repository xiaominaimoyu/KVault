"""空状态占位控件。

图标 + 标题 + 副标题 + 可选 CTA 按钮，
用于列表/详情为空时的占位展示。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QPushButton, QLabel, QWidget


class EmptyState(QWidget):
    """空状态组件。

    Args:
        icon: 图标（emoji 或字符）。
        title: 主标题。
        subtitle: 副标题说明文案。
        cta_text: 可选的行动按钮文案；为 None 时不显示按钮。
        parent: 父控件。
    """

    ctaClicked = Signal()

    def __init__(self, icon: str, title: str, subtitle: str = "", cta_text: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("EmptyState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addStretch(1)

        self._icon_label = QLabel(icon)
        self._icon_label.setObjectName("EmptyStateIcon")
        self._icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._icon_label)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("EmptyStateTitle")
        self._title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_label)

        self._subtitle_label = QLabel(subtitle)
        self._subtitle_label.setObjectName("EmptyStateSubtitle")
        self._subtitle_label.setAlignment(Qt.AlignCenter)
        self._subtitle_label.setWordWrap(True)
        layout.addWidget(self._subtitle_label)

        self._cta_btn: QPushButton | None = None
        if cta_text:
            self._cta_btn = QPushButton(cta_text)
            self._cta_btn.setObjectName("EmptyStateCta")
            self._cta_btn.clicked.connect(self.ctaClicked)
            layout.addWidget(self._cta_btn, 0, Qt.AlignCenter)

        layout.addStretch(2)

    def set_texts(self, icon: str, title: str, subtitle: str) -> None:
        """动态更新图标与文案。"""
        self._icon_label.setText(icon)
        self._title_label.setText(title)
        self._subtitle_label.setText(subtitle)
