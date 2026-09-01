"""文档卡片控件。

卡片网格视图中的单个文档卡片：
顶部格式徽章 + 文件名（2 行换行）+ 底部状态点 + 元信息行。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from gui.widgets.format_badge import FormatBadge
from gui.widgets.status_dot import StatusDot

CARD_WIDTH = 220


def _fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ["KB", "MB", "GB"]:
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value / 1024:.1f} TB"


class DocCard(QFrame):
    """文档卡片。

    Args:
        doc: 文档对象，需含 id/file_name/file_ext/file_size/status/chunk_count。
        reduce_motion: 是否减弱动效（传给状态点）。
        parent: 父控件。
    """

    def __init__(self, doc, reduce_motion: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("DocCard")
        self.doc_id = doc.id
        self.setMinimumWidth(CARD_WIDTH)
        self.setFixedWidth(CARD_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        self._badge = FormatBadge(doc.file_ext)
        badge_row.addWidget(self._badge)
        badge_row.addStretch(1)
        layout.addLayout(badge_row)

        self._name_label = QLabel(doc.file_name)
        self._name_label.setObjectName("DocCardName")
        self._name_label.setWordWrap(True)
        self._name_label.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(self._name_label)
        layout.addStretch(1)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        self._dot = StatusDot(doc.status, reduce_motion)
        meta_row.addWidget(self._dot)
        self._meta_label = QLabel(f"{_fmt_size(doc.file_size)} · {doc.chunk_count} 块")
        self._meta_label.setObjectName("DocCardMeta")
        meta_row.addWidget(self._meta_label)
        meta_row.addStretch(1)
        layout.addLayout(meta_row)

        self.setProperty("selected", False)

    def set_selected(self, selected: bool) -> None:
        """设置卡片选中态（供 QSS 属性选择器使用）。"""
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
