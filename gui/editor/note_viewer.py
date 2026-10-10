"""笔记阅读视图。

用 :class:`QTextBrowser` 承载 :func:`core.markdown.render_document` 的输出。
点击 wiki 链接时通过 :attr:`linkClicked` 上抛，由外部决定如何跳转。

HTML 安全性由渲染器保证（见 :mod:`core.markdown` 的安全章节）：正文中的
原始 HTML 一律被转义，危险协议的链接不会被渲染成可点击元素。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtWidgets import QTextBrowser

from core.markdown import RenderOptions, render_document


class NoteViewer(QTextBrowser):
    """Markdown 阅读视图。"""

    #: 用户点击了 wiki 链接，参数为目标文本
    linkClicked = Signal(str)
    #: 用户点击了未解析的链接，参数为目标文本
    brokenLinkClicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NoteViewer")
        self.setOpenLinks(False)
        self.setOpenExternalLinks(True)
        self.setReadOnly(True)

        self._resolve = lambda target, from_path=None: None
        self._from_path = ""
        self._source = ""
        self._loading = False

        self.anchorClicked.connect(self._on_anchor_clicked)

    # ---------------------------------------------------------------- 配置

    def set_link_resolver(self, resolver) -> None:
        """设置链接解析回调 ``(target, from_path) -> 相对路径 | None``。"""
        self._resolve = resolver
        self.refresh()

    def set_note_path(self, path: str) -> None:
        """设置当前笔记路径，用于相对链接解析。"""
        self._from_path = path or ""
        self.refresh()

    def set_theme(self, theme: str) -> None:
        """切换主题后重新渲染。"""
        del theme
        self.refresh()

    # ---------------------------------------------------------------- 渲染

    def render_markdown(self, markdown: str, title: str = "") -> None:
        """渲染 Markdown 为阅读视图。"""
        self._source = markdown or ""
        options = RenderOptions(
            resolve=self._resolve,
            from_path=self._from_path,
            resolve_links=True,
        )
        html = render_document(self._source, title=title, options=options)
        self._loading = True
        try:
            super().setHtml(html)
        finally:
            self._loading = False

    def refresh(self) -> None:
        """用当前文档内容重新渲染。"""
        if self._source:
            self.render_markdown(self._source)

    def clear_view(self) -> None:
        """清空视图。"""
        self._source = ""
        super().clear()

    def scroll_to_heading(self, anchor: str) -> bool:
        """滚动到指定小节，成功返回 ``True``。"""
        if not anchor:
            return False
        return self.scrollToAnchor(anchor)

    # ---------------------------------------------------------------- 事件

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """拦截链接点击。"""
        if self._loading:
            return

        fragment = url.fragment()
        # 外部链接交给浏览器
        if fragment.startswith("http://") or fragment.startswith("https://"):
            return

        target = fragment.split("#")[0]
        if not target:
            # 纯锚点跳转
            self.scrollToAnchor(fragment)
            return

        if self._resolve(target, self._from_path):
            self.linkClicked.emit(target)
        else:
            self.brokenLinkClicked.emit(target)

    def focusOutEvent(self, event) -> None:  # noqa: N802 — Qt 接口命名
        super().focusOutEvent(event)
        self.setFocusPolicy(Qt.NoFocus)