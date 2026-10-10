"""笔记内链接与标签的抽取。

支持 Obsidian 风格的语法：

- ``[[目标笔记]]``            —— 普通链接
- ``[[目标|显示文本]]``      —— 带别名的链接
- ``[[目标#小节]]``          —— 链接到小节
- ``![[目标]]``              —— 嵌入（transclusion）
- ``#标签`` / ``#父级/子级``  —— 行内标签

关键约束：**代码块、行内代码、链接目标内的内容不参与抽取**。抽取实现采用
「掩码 + 正则」两段式——先把不该匹配的区域替换成等长占位符（保留偏移量与换行），
再在掩码文本上跑正则，最后回到原文按偏移量取真实内容。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 掩码占位符：不会出现在正常文本中，且不参与 \w 匹配
_MASK = "\x00"

# 代码围栏（行首 0-3 空格 + 3 个以上反引号/波浪线）
_FENCE_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})([^\n]*)$")

# 行内代码：成对的 1 个以上反引号
_INLINE_CODE = re.compile(r"(`+)(.+?)\1", re.DOTALL)

# wiki 链接：可选的前置 ! 表示嵌入
_WIKILINK = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")

# 行内标签：# 后接词字符、连字符、斜杠
_INLINE_TAG = re.compile(r"(?<![\w#/\\])#([\w\-/]+)", re.UNICODE)

# Markdown 行内链接的 URL 部分，例如 [文本](https://a.com/b#c)
_MD_LINK_TARGET = re.compile(r"\]\([^)\n]*\)")

# 由 3 个以上 # 组成的标题行，例如 ### 标题
_ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,}(?=\s|$)", re.MULTILINE)


@dataclass(frozen=True)
class NoteLink:
    """一条指向其它笔记的链接。"""

    target: str
    """链接目标的原始文本（已去除别名与小节锚点）。"""

    alias: str | None = None
    """``|`` 之后的显示文本，未设置时为 ``None``。"""

    heading: str | None = None
    """``#`` 之后的小节标题，未设置时为 ``None``。"""

    embed: bool = False
    """是否以 ``!`` 前缀书写，即嵌入而非引用。"""

    start: int = 0
    """在原文中的起始字符偏移。"""

    end: int = 0
    """在原文中的结束字符偏移（不含）。"""

    @property
    def display(self) -> str:
        """链接在正文中应显示的文本。"""
        return self.alias or self.target

    @property
    def anchor(self) -> str:
        """``#小节`` 部分，不存在时为空字符串。"""
        return f"#{self.heading}" if self.heading else ""


@dataclass(frozen=True)
class TagRef:
    """一处行内标签。"""

    name: str
    """标签名，不含 ``#`` 前缀。"""

    start: int = 0
    end: int = 0

    @property
    def text(self) -> str:
        return f"#{self.name}"

    @property
    def depth(self) -> int:
        """嵌套层级，``#a/b/c`` 为 3。"""
        return self.name.count("/") + 1

    @property
    def parent(self) -> str | None:
        """父标签，``#a/b/c`` 返回 ``a/b``；顶层标签返回 ``None``。"""
        return self.name.rsplit("/", 1)[0] if "/" in self.name else None


# --------------------------------------------------------------------------
# 掩码
# --------------------------------------------------------------------------


def _mask_ranges(text: str, masked: list[str], start: int, end: int) -> None:
    """把 ``[start, end)`` 区间替换为占位符，但保留换行符。"""
    for i in range(max(start, 0), min(end, len(masked))):
        if masked[i] != "\n":
            masked[i] = _MASK


def _mask_fenced_code(text: str, masked: list[str]) -> None:
    """掩码 ``` / ~~~ 围栏代码块。

    按 CommonMark 规则闭合：闭合围栏的字符须与开围栏一致、长度不短于开围栏，
    且围栏行之后不得携带 info string。
    """
    lines = text.split("\n")
    pos = 0
    fence_char: str | None = None
    fence_len = 0

    for line in lines:
        start = pos
        pos += len(line) + 1
        match = _FENCE_OPEN.match(line)

        if fence_char is None:
            if match:
                fence_char = match.group(1)[0]
                fence_len = len(match.group(1))
                _mask_ranges(text, masked, start, start + len(line))
            continue

        # 已在围栏内：整行掩码，遇到合法闭合围栏则退出围栏状态
        _mask_ranges(text, masked, start, start + len(line))
        if (
            match
            and match.group(1)[0] == fence_char
            and len(match.group(1)) >= fence_len
            and match.group(2).strip() == ""
        ):
            fence_char = None
            fence_len = 0


def _mask_inline_code(text: str, masked: list[str]) -> None:
    """掩码行内代码片段。"""
    for match in _INLINE_CODE.finditer(text):
        if masked[match.start()] == _MASK:
            continue
        _mask_ranges(text, masked, match.start(), match.end())


def _mask_links(text: str, masked: list[str]) -> None:
    """掩码 wiki 链接与 Markdown 行内链接的目标部分。"""
    for match in _WIKILINK.finditer(text):
        _mask_ranges(text, masked, match.start(), match.end())
    for match in _MD_LINK_TARGET.finditer(text):
        _mask_ranges(text, masked, match.start(), match.end())
    for match in _ATX_HEADING.finditer(text):
        _mask_ranges(text, masked, match.start(), match.start() + 1)


def mask_code(text: str) -> str:
    """返回仅掩码代码区域（围栏 + 行内）的等长文本。

    用于抽取链接——链接本身不能被掩码。
    """
    masked = list(text)
    _mask_fenced_code(text, masked)
    _mask_inline_code(text, masked)
    return "".join(masked)


def mask_noncontent(text: str) -> str:
    """返回与原文等长的掩码文本，被排除的区域以占位符填充。

    在 :func:`mask_code` 的基础上额外掩码链接与标题标记，用于抽取标签——
    ``[[笔记#小节]]`` 中的井号不是标签。

    偏移量与换行位置保持不变，可直接用于在原文上做切片。
    """
    masked = list(text)
    _mask_fenced_code(text, masked)
    _mask_inline_code(text, masked)
    _mask_links(text, masked)
    return "".join(masked)


# --------------------------------------------------------------------------
# 抽取
# --------------------------------------------------------------------------


def _parse_link_body(body: str) -> tuple[str, str | None, str | None]:
    """拆分 wiki 链接正文，返回 ``(目标, 别名, 小节)``。"""
    alias: str | None = None
    if "|" in body:
        body, _, raw_alias = body.partition("|")
        alias = raw_alias.strip() or None

    heading: str | None = None
    if "#" in body:
        body, _, raw_heading = body.partition("#")
        heading = raw_heading.strip() or None

    return body.strip(), alias, heading


def extract_links(text: str) -> list[NoteLink]:
    """抽取文本中的全部 wiki 链接（含嵌入）。

    代码块与行内代码内的内容会被忽略。
    """
    if not text or "[" not in text:
        return []

    masked = mask_code(text)
    links: list[NoteLink] = []

    for match in _WIKILINK.finditer(masked):
        # 二重保险：确认原文该位置确实是 wiki 链接
        raw = text[match.start() : match.end()]
        if not raw.startswith(("[[", "![[")):
            continue

        body = text[match.start(2) : match.end(2)]
        target, alias, heading = _parse_link_body(body)
        if not target:
            continue

        links.append(
            NoteLink(
                target=target,
                alias=alias,
                heading=heading,
                embed=match.group(1) == "!",
                start=match.start(),
                end=match.end(),
            )
        )

    return links


def extract_tags(text: str) -> list[TagRef]:
    """抽取文本中的行内标签。

    排除：代码块、行内代码、wiki 链接内部、Markdown 链接的 URL、ATX 标题的井号，
    以及纯数字（``#123`` 被视为 issue 编号而非标签）。
    """
    if not text or "#" not in text:
        return []

    masked = mask_noncontent(text)
    tags: list[TagRef] = []

    for match in _INLINE_TAG.finditer(masked):
        name = match.group(1).rstrip("/")
        # 纯数字视为 issue 编号；形如 `#123abc` 仍允许
        if not name or name.isdigit():
            continue
        tags.append(TagRef(name=name, start=match.start(), end=match.end()))

    return tags


def tag_hierarchy(names: list[str]) -> dict[str, int]:
    """把标签列表展开为「含自身的完整路径 → 使用次数」。

    ``["a/b", "a"]`` 展开为 ``{"a": 2, "a/b": 1}``，其中 ``a`` 计入自身与子标签。
    """
    counts: dict[str, int] = {}
    for raw in names:
        name = raw.lstrip("#").strip().rstrip("/")
        if not name:
            continue
        parts = name.split("/")
        for i in range(len(parts)):
            path = "/".join(parts[: i + 1])
            counts[path] = counts.get(path, 0) + 1
    return counts


def parse_link_target(target: str) -> tuple[str, str | None]:
    """解析链接目标字符串，返回 ``(笔记路径, 小节)``。

    ``笔记A#小节|别名`` 解析为 ``("笔记A", "小节")``；别名被丢弃——需要别名时
    请使用 :func:`extract_links`。
    """
    path, _alias, heading = _parse_link_body(target)
    return path, heading


def normalize_target(target: str) -> str:
    """归一化链接目标：去除扩展名与首尾斜杠，便于比较。"""
    name = target.strip().replace("\\", "/").strip("/")
    if name.lower().endswith(".md"):
        name = name[:-3]
    return name


def format_link(target: str, alias: str | None = None, heading: str | None = None) -> str:
    """按 Obsidian 语法序列化链接。"""
    body = target
    if heading:
        body += f"#{heading}"
    if alias:
        body += f"|{alias}"
    return f"[[{body}]]"