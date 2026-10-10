"""预览标签页。

对应设计文档 §3.4.1：

- 顶部文档信息卡：文件名 ``--text-lg`` ``--font-semibold`` + 元信息行
- 内容区：衬线体 ``--text-base``、最大宽度 720px 居中、``--fg-primary``
- 文本块概览：折叠卡片，标题"块 N"，内容截断，点击展开
- 检索命中块：``--accent-warm-dim`` 背景 + 左 3px ``--accent-warm`` 边框
- 空状态：``file-text`` 图标 + "选择文档查看预览" + 副标题

本控件负责 HTML 组装（原由 MainWindow 承担），并保证所有文本经
:func:`html.escape` 转义——文档内容可能来自用户导入的外部文件。
"""

from __future__ import annotations

import html

from PySide6.QtWidgets import QStackedWidget, QTextBrowser, QVBoxLayout, QWidget

#: §3.4.1 正文最大阅读宽度
MAX_CONTENT_WIDTH = 720

#: 块卡片默认截断长度（字符），点击可展开
CHUNK_PREVIEW_LEN = 160


def _esc(text) -> str:
    """转义 HTML 特殊字符。"""
    return html.escape(str(text if text is not None else ""), quote=True)


class PreviewTab(QWidget):
    """预览标签页。

    由 :class:`QStackedWidget` 承载空状态与正文两种形态，
    无文档时显示引导，有文档时显示信息卡 + 正文。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PreviewTab")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)

        # --- 空状态（§7.1 预览面板）---
        from gui.widgets.empty_state import EmptyState

        self._empty = EmptyState("📄", "选择文档查看预览", "从左侧列表选择一个文档")
        self._stack.addWidget(self._empty)

        # --- 正文 ---
        self._browser = QTextBrowser()
        self._browser.setObjectName("PreviewBody")
        self._browser.setOpenExternalLinks(False)
        self._browser.setReadOnly(True)
        # §3.4.1 阅读宽度上限 + 衬线体（§2.3）
        self._browser.document().setTextWidth(0)
        self._stack.addWidget(self._browser)

        layout.addWidget(self._stack)
        self._show_empty()

    # ---------------------------------------------------------------- 形态

    def _show_empty(self) -> None:
        self._stack.setCurrentWidget(self._empty)

    def _show_content(self) -> None:
        self._stack.setCurrentWidget(self._browser)

    def is_empty(self) -> bool:
        """当前是否处于空状态。"""
        return self._stack.currentWidget() is self._empty

    @property
    def browser(self) -> QTextBrowser:
        """暴露内部浏览器，便于滚动定位与测试。"""
        return self._browser

    # ---------------------------------------------------------------- 内容

    def set_html(self, html_text: str) -> None:
        """整体替换预览内容。"""
        if not html_text.strip():
            self.clear_preview()
            return
        self._show_content()
        self._browser.setHtml(html_text)

    def clear_preview(self) -> None:
        """清空并回到空状态。"""
        self._browser.clear()
        self._show_empty()

    def set_not_found(self, message: str = "文档不存在") -> None:
        """文档已不存在时的提示。"""
        self._show_content()
        self._browser.setHtml(
            f'<div style="padding:16px;color:#F87171;">{_esc(message)}</div>'
        )

    def append_hit_chunk(self, html_text: str) -> None:
        """追加检索命中块（带 §3.4.1 高亮容器）。"""
        self._browser.append(f'<div class="hit-chunk">{html_text}</div>')

    def scroll_to_top(self) -> None:
        """滚动回顶部。"""
        bar = self._browser.verticalScrollBar()
        bar.setValue(bar.minimum())

    # ---------------------------------------------------------------- 组装

    def build_document_html(
        self,
        doc,
        content: str = "",
        chunks: list[dict] | None = None,
        tags: list[dict] | None = None,
        partitions: str = "",
        error_message: str = "",
        size_label: str = "",
        status_label: str = "",
    ) -> str:
        """组装完整的文档预览 HTML。

        :param doc: :class:`~core.metadata_manager.Document`
        :param content: 已解析的正文
        :param chunks: 文本块列表，用于块概览
        :param tags: 标签字典列表
        :param error_message: 索引失败时的错误信息
        """
        parts: list[str] = [self._info_card(doc, tags, partitions, size_label, status_label)]

        if error_message:
            parts.append(self._error_card(error_message))
        elif content:
            parts.append(self._content_block(content))
        else:
            parts.append(
                '<p style="color:#9BA1AC;">文档尚未完成索引，暂无内容预览。</p>'
            )

        if chunks:
            parts.append(self._chunk_overview(chunks))

        return self._wrap("".join(parts))

    # ------------------------------------------------------------ 片段构造

    def _wrap(self, inner: str) -> str:
        """用最大阅读宽度包裹正文。"""
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<style>"
            "body { margin:0; padding:0; }"
            f".kv-wrap {{ max-width:{MAX_CONTENT_WIDTH}px; margin:0 auto; "
            "font-family:'Inter','Source Han Serif SC','Noto Serif CJK SC',serif;"
            "font-size:14px; line-height:1.8; color:#E8EAED; }"
            ".hit-chunk { background-color:rgba(184,119,20,0.35); "
            "border-left:3px solid #F5A623; padding:6px 10px; margin:4px 0; "
            "border-radius:0 4px 4px 0; }"
            ".chunk-card { background-color:#161922; border:1px solid #3A4049; "
            "border-radius:6px; padding:8px 10px; margin:4px 0; }"
            ".chunk-summary { color:#9BA1AC; font-size:13px; }"
            "</style></head>"
            f'<body><div class="kv-wrap">{inner}</div></body></html>'
        )

    def _info_card(
        self,
        doc,
        tags: list[dict] | None,
        partitions: str,
        size_label: str,
        status_label: str,
    ) -> str:
        """§3.4.1 顶部文档信息卡。"""
        meta_parts = [
            f"<b>格式</b> {_esc((doc.file_ext or '').upper())}",
            f"<b>大小</b> {_esc(size_label)}",
            f"<b>状态</b> {_esc(status_label or doc.status)}",
            f"<b>块数</b> {int(doc.chunk_count)}",
            f"<b>分区</b> {_esc(partitions or '未分类')}",
        ]
        if tags:
            names = ", ".join(_esc(t.get("name", "")) for t in tags)
            meta_parts.append(f"<b>标签</b> {names}")

        return (
            '<div class="kv-info-card" '
            'style="background-color:#161922; border:1px solid #3A4049; '
            'border-radius:8px; padding:16px; margin:16px 0;">'
            f'<div style="font-size:18px; font-weight:600; color:#E8EAED;">'
            f"{_esc(doc.file_name)}</div>"
            '<div style="font-size:13px; color:#9BA1AC; margin-top:8px;">'
            f"{' &nbsp;·&nbsp; '.join(meta_parts)}</div>"
            f'<div style="font-size:12px; color:#5C6370; margin-top:6px; '
            f'font-family:\'JetBrains Mono\',Consolas,monospace;">'
            f"{_esc(doc.stored_path)}</div>"
            "</div>"
        )

    def _error_card(self, message: str) -> str:
        """§3.4.3 失败文档的错误信息用状态色背景卡片突出。"""
        return (
            '<div style="background-color:rgba(248,113,113,0.16); '
            'border:1px solid #F87171; border-radius:8px; padding:12px 16px; '
            'margin:12px 0;">'
            '<span style="color:#F87171; font-weight:600;">索引失败：</span>'
            f'<span style="color:#9BA1AC;">{_esc(message)}</span>'
            "</div>"
        )

    def _content_block(self, content: str, limit: int = 4000) -> str:
        """正文内容区。"""
        text = _esc(content[:limit])
        paragraphs = "".join(
            f"<p>{line}</p>" for line in text.split("\n") if line.strip()
        )
        return f'<div style="padding:0 16px;">{paragraphs}</div>'

    def _chunk_overview(self, chunks: list[dict]) -> str:
        """§3.4.1 文本块折叠卡片概览。"""
        cards = ['<div style="padding:0 16px 16px;">']
        cards.append(
            '<div style="font-size:15px; font-weight:600; margin:12px 0 8px;">'
            "文本块概览</div>"
        )

        for chunk in chunks:
            index = int(chunk.get("chunk_index", 0)) + 1
            preview = _esc(chunk.get("content_preview", ""))
            collapsed = preview[:CHUNK_PREVIEW_LEN]
            suffix = "…" if len(preview) > CHUNK_PREVIEW_LEN else ""

            cards.append(
                '<details class="chunk-card" style="background-color:#161922; '
                'border:1px solid #3A4049; border-radius:6px; padding:8px 10px; '
                'margin:4px 0;">'
                f'<summary style="cursor:pointer; font-size:13px; font-weight:500; '
                f'color:#9BA1AC;">块 {index}</summary>'
                f'<div class="chunk-summary" style="margin-top:6px;">'
                f"{collapsed}{suffix}</div>"
                "</details>"
            )

        cards.append("</div>")
        return "".join(cards)