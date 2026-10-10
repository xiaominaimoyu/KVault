"""Markdown 语法高亮。

基于 :class:`QSyntaxHighlighter`，对 QPlainTextEdit 逐块着色（Qt 自带的
``QSyntaxHighlighter`` 不支持正则语法高亮，因此逐块匹配）。

覆盖：frontmatter 围栏与键、标题、列表符号、引用、分隔线、粗斜体、行内代码、
代码围栏、Markdown 链接、wiki 链接（区分已解析/未解析）、标签、块引用 ID。

配色统一取自 :mod:`gui.styles.variables` 的设计令牌，跟随主题切换。
"""

from __future__ import annotations

import re

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(700)
    fmt.setFontItalic(italic)
    return fmt


class MarkdownHighlighter(QSyntaxHighlighter):
    """Markdown 语法高亮器。"""

    def __init__(self, document, theme: str = "dark"):
        super().__init__(document)
        self._theme = theme
        self._build_formats()

    def set_theme(self, theme: str) -> None:
        """切换主题并重新着色。"""
        self._theme = theme
        self._build_formats()
        self.rehighlight()

    # ---------------------------------------------------------------- 内部

    def _tokens(self) -> dict:
        return TOKENS_DARK if self._theme == "dark" else TOKENS_LIGHT

    def _build_formats(self) -> None:
        t = self._tokens()
        self.f_heading = _fmt(t["accent-primary"], bold=True)
        self.f_heading_mark = _fmt(t["accent-primary-dim"], bold=True)
        self.f_bold = _fmt(t["fg-primary"], bold=True)
        self.f_italic = _fmt(t["fg-secondary"], italic=True)
        self.f_strike = _fmt(t["fg-muted"])
        self.f_code = _fmt(t["status-warning"])
        self.f_code_block = _fmt(t["status-info"])
        self.f_fence = _fmt(t["fg-muted"])
        self.f_link = _fmt(t["status-info"])
        self.f_wikilink = _fmt(t["accent-primary"])
        self.f_wikilink_unresolved = _fmt(t["accent-warm"])
        self.f_embed = _fmt(t["accent-warm"])
        self.f_tag = _fmt(t["status-success"])
        self.f_quote = _fmt(t["fg-secondary"], italic=True)
        self.f_list = _fmt(t["accent-warm"], bold=True)
        self.f_hr = _fmt(t["fg-faint"])
        self.f_frontmatter = _fmt(t["fg-muted"])
        self.f_frontmatter_key = _fmt(t["accent-warm"])
        self.f_block_id = _fmt(t["accent-primary-dim"])

    def highlightBlock(self, text: str) -> None:  # noqa: N802 — Qt 接口命名
        state = self.previousBlockState()

        # state 1 = frontmatter 区域，0 = 正文，-1 = 围栏代码块内
        if state == 1:
            if text.strip() == "---":
                self.setFormat(0, len(text), self.f_frontmatter)
                self.setCurrentBlockState(0)
            else:
                self._highlight_frontmatter(text)
                self.setCurrentBlockState(1)
            return

        if state == -1:
            self.setFormat(0, len(text), self.f_code_block)
            if _FENCE.match(text):
                self.setCurrentBlockState(0)
            return

        # 首块判断 frontmatter 起始
        if self.currentBlock().blockNumber() == 0 and text.strip() == "---":
            self.setFormat(0, len(text), self.f_frontmatter)
            self.setCurrentBlockState(1)
            return

        self._highlight_frontmatter_end(text)
        self._highlight_inline(text)

        fence = _FENCE.match(text)
        if fence:
            self.setFormat(0, len(text), self.f_fence)
            self.setCurrentBlockState(-1)
            return

        heading = re.match(r"^(#{1,6})[ \t]+", text)
        if heading:
            self.setFormat(0, len(heading.group(1)), self.f_heading_mark)
            self.setFormat(heading.end(), len(text), self.f_heading)
            self.setCurrentBlockState(0)
            return

        if re.match(r"^[ \t]{0,3}(?:\*[ \t]*){3,}$|^[ \t]{0,3}(?:-[ \t]*){3,}$|^[ \t]{0,3}(?:_[ \t]*){3,}$", text):
            self.setFormat(0, len(text), self.f_hr)
            self.setCurrentBlockState(0)
            return

        quote = re.match(r"^[ \t]{0,3}>", text)
        if quote:
            self.setFormat(0, quote.end(), self.f_quote)
            self.setCurrentBlockState(0)
            return

        bullet = re.match(r"^([ \t]*)([-*+]|\d+[.)])([ \t]+)", text)
        if bullet:
            self.setFormat(bullet.start(2), bullet.end(2), self.f_list)
            self.setCurrentBlockState(0)
            return

        block_id = re.search(r"\s\^([A-Za-z0-9-]+)\s*$", text)
        if block_id:
            self.setFormat(block_id.start(), len(text), self.f_block_id)

        self.setCurrentBlockState(0)

    # ---------------------------------------------------------------- 分项

    def _highlight_frontmatter(self, text: str) -> None:
        self.setFormat(0, len(text), self.f_frontmatter)
        key = re.match(r"^([A-Za-z_\u4e00-\u9fff][\w\-\u4e00-\u9fff]*)(:)", text)
        if key:
            self.setFormat(key.start(1), key.end(1), self.f_frontmatter_key)

    def _highlight_frontmatter_end(self, text: str) -> None:
        """正文中的 ``---`` 分隔线。"""
        if text.strip() == "---":
            self.setFormat(0, len(text), self.f_hr)

    def _highlight_inline(self, text: str) -> None:
        """行内标记。后应用的规则覆盖先应用的，因此顺序按优先级从低到高。"""
        # 块引用 ID（优先级最高，会被其它规则覆盖，先留着）
        # 行内代码
        for match in re.finditer(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", text):
            self.setFormat(match.start(), len(match.group(1)), self.f_code)
            self.setFormat(match.start(2), len(match.group(2)), self.f_code)

        # 粗斜体
        for pattern, fmt in (
            (r"\*\*(?=\S)(.+?)(?<=\S)\*\*", self.f_bold),
            (r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", self.f_italic),
            (r"~~(?=\S)(.+?)(?<=\S)~~", self.f_strike),
        ):
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(1), len(match.group(1)), fmt)

        # wiki 链接与嵌入
        for match in re.finditer(r"(!?)\[\[([^\[\]\n]+?)\]\]", text):
            embed = match.group(1) == "!"
            body = match.group(2)
            target = body.split("|")[0].split("#")[0].strip()

            fmt = self.f_embed if embed else self.f_wikilink
            if not embed and target and not self._is_resolvable(target):
                fmt = self.f_wikilink_unresolved

            start = match.start()
            if embed:
                self.setFormat(start, 1, fmt)
                start += 1
            self.setFormat(start, len(match.group(0)) - (start - match.start()), fmt)

        # Markdown 链接
        for match in re.finditer(r"\[([^\]\n]*)\]\(([^)\s]+)\)", text):
            self.setFormat(match.start(), len(match.group(0)), self.f_link)

        # 行内标签
        for match in re.finditer(r"(?<![\w#/\\])#([\w\-/]+)", text):
            self.setFormat(match.start(), len(match.group(0)), self.f_tag)

        # 块引用 ID 放最后，确保不被覆盖
        block_id = re.search(r"\s(\^[A-Za-z0-9-]+)\s*$", text)
        if block_id:
            self.setFormat(block_id.start(1), len(block_id.group(1)), self.f_block_id)

    def _is_resolvable(self, target: str) -> bool:
        """由外部注入的解析回调判断链接是否存在。"""
        resolver = getattr(self, "_resolver", None)
        if resolver is None:
            # 未配置解析器时按「可解析」着色，避免全部显示为警告色
            return True
        try:
            return bool(resolver(target))
        except Exception:  # noqa: BLE001 —— 高亮失败不应影响编辑
            return True

    def set_resolver(self, resolver) -> None:
        """设置链接解析回调 ``(target) -> 相对路径 | None``，用于区分断链配色。"""
        self._resolver = resolver
        self.rehighlight()