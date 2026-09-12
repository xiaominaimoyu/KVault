"""格式徽章控件。

圆角小徽章，展示文档格式（自动大写 + 等宽字）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class FormatBadge(QLabel):
    """格式徽章，如 PDF / DOCX / MD。

    Args:
        file_ext: 文件扩展名（自动转大写）。
        parent: 父控件。
    """

    def __init__(self, file_ext: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FormatBadge")
        self.setText(file_ext.upper())
        self.setAlignment(Qt.AlignCenter)
