"""笔记标题推导。

优先级（与 Obsidian 一致）：

1. frontmatter 的 ``title`` 属性
2. 正文中的首个一级标题 ``# 标题``
3. 文件名

同时提供正文清洗（剥离 frontmatter 与标记语法）与字数统计，供索引使用。
"""

from __future__ import annotations

import re

from core.frontmatter import parse
from core.links import mask_code

# ATX 一级标题：`# 标题`，且后面不能紧跟更多 `#`
_H1 = re.compile(r"^[ \t]{0,3}#(?!#)[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)

# 列表、引用、代码围栏中的井号不参与标题识别
_NOISE_PREFIX = re.compile(r"^[ \t]*(?:[-*+][ \t]|\d+\.[ \t]|>)[ \t]*#")

# 用于统计"有效文本"的 Markdown 标记
# 行内标记替换为空串（否则会把词切开），块级标记替换为空格（否则会粘连相邻词）
_INLINE_NOISE = re.compile(r"(\*\*|~~|\*|`{1,3})")
_BLOCK_NOISE = re.compile(
    r"(^[ \t]*#{1,6}[ \t]+|^[ \t]*[-*+][ \t]+|^[ \t]*>\s?|^[ \t]*(?:={3,}|-{3,}|\*{3,})[ \t]*$)",
    re.MULTILINE,
)

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_WORD = re.compile(r"[A-Za-z0-9_]+")


def strip_markdown(text: str) -> str:
    """剥离 Markdown 标记，返回便于计数的纯文本。"""
    cleaned = _BLOCK_NOISE.sub(" ", text)
    # 行内标记删除但保留分词边界：``**粗**体`` 应读作"粗体"而不是"粗 体"
    cleaned = _INLINE_NOISE.sub("", cleaned)
    return cleaned


def title_from_content(content: str, fallback: str = "") -> str:
    """从笔记正文中提取标题，找不到时返回 ``fallback``。"""
    if not content:
        return fallback

    body = parse(content).body
    # 代码块内的 `#` 不是标题，先把代码区域掩码掉再匹配
    masked = mask_code(body)

    for match in _H1.finditer(masked):
        line_start = body.rfind("\n", 0, match.start()) + 1
        prefix = body[line_start : match.start()]
        if _NOISE_PREFIX.match(prefix + "#"):
            continue
        start, end = match.span(1)
        title = body[start:end].strip().rstrip("#").strip()
        if title:
            return title

    return fallback


def word_count(content: str) -> int:
    """统计有效字数：中日韩字符逐字计，拉丁文字按词计。

    Markdown 标记符号不计入。
    """
    if not content:
        return 0

    body = parse(content).body
    # 剥离围栏代码块，避免代码量污染字数统计
    body = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    body = strip_markdown(body)

    cjk = len(_CJK.findall(body))
    words = len(_WORD.findall(body))
    return cjk + words


def reading_time_minutes(content: str) -> int:
    """估算阅读时长（分钟），按中文 400 字/分钟、英文 200 词/分钟。"""
    if not content:
        return 0
    body = parse(content).body
    cjk = len(_CJK.findall(body))
    words = len(_WORD.findall(body))
    minutes = cjk / 400 + words / 200
    return max(1, round(minutes)) if minutes > 0 else 0


def excerpt(content: str, length: int = 200, strip_markup: bool = True) -> str:
    """生成用于列表展示的摘要文本。"""
    if not content:
        return ""

    body = parse(content).body
    body = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    if strip_markup:
        body = strip_markdown(body)
    body = re.sub(r"\[\[([^\[\]|]+)(?:\|([^\]]*))?\]\]", lambda m: m.group(2) or m.group(1), body)
    body = re.sub(r"!\[\[([^\[\]|]+)(?:\|([^\]]*))?\]\]", lambda m: m.group(2) or m.group(1), body)

    text = re.sub(r"\s+", " ", body).strip()
    return text if len(text) <= length else text[: length - 1].rstrip() + "…"


def headings(content: str) -> list[tuple[int, str]]:
    """提取全部标题，返回 ``(级别, 文本)`` 列表，用于大纲面板。"""
    if not content:
        return []

    body = parse(content).body
    results: list[tuple[int, str]] = []
    in_fence = False
    fence_char = ""

    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence_char = True, marker
            elif marker == fence_char:
                in_fence = False
            continue
        if in_fence:
            continue

        match = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", line)
        if match:
            results.append((len(match.group(1)), match.group(2).strip()))

    return results


def slugify(text: str) -> str:
    """把标题转换为适合文件名的 slug，保留中文。"""
    from core.vault import sanitize_title

    return sanitize_title(text)