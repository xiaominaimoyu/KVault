"""预览标签页。

文档信息卡 + 正文预览 + 检索命中块高亮。
内容 HTML 由上层组装后传入。
"""

from __future__ import annotations

from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget


class PreviewTab(QWidget):
    """预览标签页，包一层 QTextBrowser。

    Methods:
        set_html(html): 整体替换预览内容。
        clear_preview(): 清空预览。
        append_hit_chunk(html): 追加检索命中块（带高亮容器样式）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PreviewTab")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._browser = QTextBrowser()
        self._browser.setPlaceholderText("选择文档查看预览")
        self._browser.setOpenExternalLinks(False)
        layout.addWidget(self._browser)

    def set_html(self, html: str):
        self._browser.setHtml(html)

    def clear_preview(self):
        self._browser.clear()

    def append_hit_chunk(self, html: str):
        self._browser.append(f"<div class='hit-chunk'>{html}</div>")
