"""Markdown → HTML 渲染器。

为预览视图与导出提供 HTML 生成，**不引入第三方依赖**。覆盖知识库日常所需：

- 标题、段落、有序/无序列表、引用、分隔线
- 表格（GFM 风格）
- 行内样式：粗体、斜体、删除线、行内代码、链接
- 代码块围栏（带语言标注）
- 图片
- 脚注式引用

在此之上实现 Obsidian 扩展：

- ``[[笔记]]`` / ``[[笔记|别名]]`` / ``[[笔记#小节]]`` —— 渲染为可点击链接
- ``[[笔记#^块ID]]`` —— 块引用
- ``![[笔记]]`` —— 嵌入（渲染为内联区块）
- ``#标签`` —— 渲染为标签徽章

**安全**：所有文本在进入 HTML 前一律经过 :func:`html.escape`，wiki 链接目标同样如此。
笔记内容完全由用户控制（也可能来自 MCP 等外部写入），因此渲染器绝不允许原始 HTML
注入——它只会转义而不会透传内联 HTML。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

#: 渲染器只转义、不透传任何内联 HTML，笔记内容全部按纯文本处理


@dataclass
class RenderOptions:
    """渲染行为开关。"""

    resolve_links: bool = True
    """链接目标能否解析到真实笔记。``False`` 时未解析链接渲染为纯文本。"""

    resolve: object = None
    """链接解析回调 ``(target, from_path) -> str | None``。"""

    from_path: str = ""
    """当前笔记的相对路径，用于相对链接解析。"""

    embed_missing: str = "text"
    """嵌入目标不存在时的降级方式：``text`` 显示为引用块，``none`` 忽略。"""

    max_heading_level: int = 6
    """标题渲染的最大级别。"""

    heading_anchors: bool = True
    """是否为标题生成锚点 id。"""

    highlight_tags: bool = True
    """是否把 ``#标签`` 渲染为徽章。``False`` 时保留为普通文本。"""

    heading_offset: int = 0
    """标题层级偏移，笔记内 H1 可整体降级为 H2 以适配面板。"""

    code_wrap: bool = False
    """代码块是否按需换行。"""

    extra_css: str = ""
    """追加到 ``<style>`` 的自定义 CSS。"""

    _rendered_links: list = field(default_factory=list, repr=False)
    """渲染过程中产生的链接，用于构建大纲与悬浮预览缓存。"""


# --------------------------------------------------------------------------
# 行内解析
# --------------------------------------------------------------------------

_WIKILINK_INLINE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
_IMAGE_INLINE = re.compile(r"!\[([^\]\n]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LINK_INLINE = re.compile(r"\[([^\]\n]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_AUTOLINK = re.compile(r"<((?:https?|ftp)://[^>\s]+)>")
_TAG_INLINE = re.compile(r"(?<![\w#/\\])#([\w\-/]+)", re.UNICODE)
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_BOLD_ALT = re.compile(r"__(?=\S)(.+?)(?<=\S)__", re.DOTALL)
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_ITALIC_UNDER = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.DOTALL)
_CODE_INLINE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)
_BLOCK_ID = re.compile(r"\s\^([A-Za-z0-9-]+)\s*$")


def escape(text: str, quote: bool = True) -> str:
    """转义 HTML 特殊字符。"""
    return html.escape(text, quote=quote)


#: 允许出现在链接目标中的协议。其余（javascript:、data:、vbscript: 等）一律拒绝，
#: 否则渲染出的 ``<a href>`` 点击后会执行脚本。
_SAFE_SCHEMES = frozenset({"http", "https", "mailto", "ftp", "ftps"})

_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")


def safe_url(url: str) -> str | None:
    """校验链接目标是否可安全渲染。

    返回原 URL，或在协议危险时返回 ``None``。

    - ``javascript:alert(1)`` / ``data:...`` / ``vbscript:...`` 被拒绝
    - 相对路径、锚点、查询串等无协议地址放行
    """
    candidate = (url or "").strip()
    if not candidate:
        return None
    match = _SCHEME_RE.match(candidate)
    if not match:
        # 无协议前缀即视为相对路径
        return candidate
    if match.group(1).lower() in _SAFE_SCHEMES:
        return candidate
    return None


def _render_inline(text: str, opts: RenderOptions) -> str:
    """渲染一段行内文本。

    顺序很关键：先提取出需要跳过的片段（代码、链接、标签）占位，再做样式替换，
    最后把占位还原为 HTML，避免生成的结构被后续正则破坏。
    """
    slots: list[str] = []

    def stash(markup: str) -> str:
        slots.append(markup)
        return f"\x00{len(slots) - 1}\x00"

    # 1) 行内代码优先，内部不再解析任何标记
    def on_code(match: re.Match) -> str:
        return stash(f"<code>{escape(match.group(2).strip())}</code>")

    text = _CODE_INLINE.sub(on_code, text)

    # 2) 图片
    def on_image(match: re.Match) -> str:
        alt, raw_url = match.group(1), match.group(2)
        url = safe_url(raw_url)
        if url is None:
            return stash(f'<span class="kv-broken-image">{escape(alt)}</span>')
        return stash(f'<img src="{escape(url, quote=True)}" alt="{escape(alt)}" />')

    text = _IMAGE_INLINE.sub(on_image, text)

    # 3) wiki 链接 / 嵌入
    def on_wikilink(match: re.Match) -> str:
        return stash(_render_wikilink(match, opts))

    text = _WIKILINK_INLINE.sub(on_wikilink, text)

    # 4) Markdown 链接
    def on_link(match: re.Match) -> str:
        label, raw_url = match.group(1), match.group(2)
        url = safe_url(raw_url)
        if url is None:
            # 危险协议：只保留可见文本，不生成可点击链接
            return stash(f"<span>{escape(label)}</span>")
        return stash(f'<a href="{escape(url, quote=True)}">{escape(label)}</a>')

    text = _LINK_INLINE.sub(on_link, text)

    def on_autolink(match: re.Match) -> str:
        url = safe_url(match.group(1))
        if url is None:
            return stash(f"<span>{escape(match.group(1))}</span>")
        return stash(
            f'<a href="{escape(url, quote=True)}">{escape(match.group(1))}</a>'
        )

    text = _AUTOLINK.sub(on_autolink, text)

    # 5) 标签
    if opts.highlight_tags:
        def on_tag(match: re.Match) -> str:
            name = match.group(1)
            return stash(
                f'<span class="kv-tag" data-tag="{escape(name, quote=True)}">'
                f'<span class="kv-tag-hash">#</span>{escape(name)}</span>'
            )

        text = _TAG_INLINE.sub(on_tag, text)

    # 6) 文本转义——此后只剩纯文本，任何残留的尖括号都不会变成标签
    text = escape(text)

    # 7) 行内样式
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _BOLD_ALT.sub(r"<strong>\1</strong>", text)
    text = _STRIKE.sub(r"<del>\1</del>", text)
    text = _ITALIC_STAR.sub(r"<em>\1</em>", text)
    text = _ITALIC_UNDER.sub(r"<em>\1</em>", text)
    # 转义后的换行符在行内无效，还原成真正的换行
    text = text.replace("&#x27;", "'")

    # 8) 还原占位
    def restore(match: re.Match) -> str:
        return slots[int(match.group(1))]

    return re.sub(r"\x00(\d+)\x00", restore, text)


def _resolve_target(target: str, opts: RenderOptions) -> str | None:
    resolve = opts.resolve
    if resolve is None or not opts.resolve_links:
        return None
    try:
        return resolve(target, opts.from_path)
    except TypeError:
        try:
            return resolve(target)
        except Exception:  # noqa: BLE001 —— 解析失败按未解析处理
            return None
    except Exception:  # noqa: BLE001
        return None


def _render_wikilink(match: re.Match, opts: RenderOptions) -> str:
    """渲染一条 wiki 链接或嵌入。"""
    embed = match.group(1) == "!"
    body = match.group(2)
    target, alias, heading, block_id = _split_wikilink(body)

    if not target:
        return escape(match.group(0))

    display = alias or target
    resolved = _resolve_target(target, opts)
    # 块引用 ``[[笔记#^块ID]]`` 的锚点就是 ``#^块ID``
    anchor_part = heading or (f"^{block_id}" if block_id else "")
    anchor = f"#{escape(anchor_part, quote=True)}" if anchor_part else ""

    if embed:
        css_class = "kv-embed kv-embed-resolved" if resolved else "kv-embed kv-embed-missing"
        if not resolved and opts.embed_missing == "none":
            return ""
        title = escape(f"{target}{anchor}")
        return (
            f'<span class="{css_class}" data-target="{escape(target, quote=True)}" '
            f'data-resolved="{escape(resolved, quote=True) if resolved else ""}" title="{title}">'
            f'<span class="kv-embed-icon">{"↳" if resolved else "⚠"}</span>'
            f"{escape(display)}</span>"
        )

    css_class = "kv-link kv-link-resolved" if resolved else "kv-link kv-link-unresolved"
    opts._rendered_links.append(target)
    title = escape(f"{target}{anchor}")
    href = escape(f"{resolved or target}{anchor}", quote=True)
    return (
        f'<a class="{css_class}" href="{href}" data-target="{escape(target, quote=True)}" '
        f'data-resolved="{escape(resolved, quote=True) if resolved else ""}" '
        f'title="{title}">{escape(display)}</a>'
    )


def _split_wikilink(body: str) -> tuple[str, str | None, str | None, str | None]:
    """拆分 wiki 链接正文，返回 ``(目标, 别名, 小节, 块ID)``。"""
    from core.links import parse_link_target

    alias: str | None = None
    if "|" in body:
        body, _, raw_alias = body.partition("|")
        alias = raw_alias.strip() or None

    block_id: str | None = None
    target, heading = parse_link_target(body)
    if heading:
        found = _BLOCK_ID.search(heading)
        if found:
            block_id = found.group(1)
            heading = heading[: found.start()].strip() or None
    return target, alias, heading, block_id


# --------------------------------------------------------------------------
# 块级解析
# --------------------------------------------------------------------------

_ATX = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
_SETEXT = re.compile(r"^(=+|-+)[ \t]*$")
_FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)[ \t]*$")
_HR = re.compile(r"^[ \t]{0,3}((?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_UL_ITEM = re.compile(r"^([ \t]*)([-*+])[ \t]+(.*)$")
_OL_ITEM = re.compile(r"^([ \t]*)(\d{1,9})[.)][ \t]+(.*)$")
_QUOTE = re.compile(r"^[ \t]{0,3}>[ \t]?(.*)$")
_TABLE_DELIM = re.compile(r"^[ \t]*\|?[ \t]*:?-{1,}:?[ \t]*(\|[ \t]*:?-{1,}:?[ \t]*)*\|?[ \t]*$")

_BLOCK_ID_LINE = re.compile(r"\s*\^([A-Za-z0-9-]+)\s*$")


def slugify_heading(text: str) -> str:
    """把标题文本转为锚点 id。"""
    plain = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", text).strip()
    return re.sub(r"\s+", "-", plain).lower() or "section"


def render(markdown: str, options: RenderOptions | None = None) -> str:
    """把 Markdown 渲染为 HTML 片段。"""
    opts = options or RenderOptions()
    body = _strip_frontmatter(markdown)
    return "\n".join(_parse_blocks(body.split("\n"), opts))


def _strip_frontmatter(markdown: str) -> str:
    """移除 frontmatter，避免属性被当成正文渲染。"""
    from core.frontmatter import parse

    fm = parse(markdown)
    return fm.body if fm.present else markdown


def _parse_blocks(lines: list[str], opts: RenderOptions) -> list[str]:
    """把行序列解析为块级 HTML 片段。"""
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # 空行
        if not line.strip():
            i += 1
            continue

        # 代码围栏
        fence = _FENCE.match(line)
        if fence:
            marker, lang = fence.group(1), fence.group(2)
            i += 1
            code_lines: list[str] = []
            while i < n:
                closing = _FENCE.match(lines[i])
                if (
                    closing
                    and closing.group(1)[0] == marker[0]
                    and len(closing.group(1)) >= len(marker)
                    and not closing.group(2)
                ):
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            cls = f' class="language-{escape(lang, quote=True)}"' if lang else ""
            out.append(
                f"<pre><code{cls}>{escape(chr(10).join(code_lines))}</code></pre>"
            )
            continue

        # ATX 标题
        atx = _ATX.match(line)
        if atx:
            out.append(_render_heading(len(atx.group(1)), atx.group(2), opts))
            i += 1
            continue

        # 分隔线（必须在列表之前判断，`---` 也可能是 setext 下划线）
        if _HR.match(line):
            out.append("<hr />")
            i += 1
            continue

        # 引用块
        if _QUOTE.match(line):
            quote_lines: list[str] = []
            while i < n:
                if not lines[i].strip():
                    # 空行后若仍是引用则保留，否则终止引用块
                    if i + 1 < n and _QUOTE.match(lines[i + 1]):
                        quote_lines.append("")
                        i += 1
                        continue
                    break
                match = _QUOTE.match(lines[i])
                quote_lines.append(match.group(1) if match else lines[i])
                i += 1
            inner = "\n".join(quote_lines)
            out.append(f"<blockquote>{render(inner, opts)}</blockquote>")
            continue

        # 表格
        if "|" in line and i + 1 < n and _TABLE_DELIM.match(lines[i + 1]) and "|" in lines[i + 1]:
            table, i = _parse_table(lines, i, opts)
            out.append(table)
            continue

        # 列表
        if _UL_ITEM.match(line) or _OL_ITEM.match(line):
            block, i = _parse_list(lines, i, opts)
            out.append(block)
            continue

        # 段落
        para_lines = [line]
        i += 1
        while i < n and lines[i].strip() and not _starts_block(lines[i]):
            para_lines.append(lines[i])
            i += 1

        # 收集块 ID 标记
        text = "\n".join(para_lines)
        block_id_match = _BLOCK_ID_LINE.search(text)
        block_id = ""
        if block_id_match:
            text = text[: block_id_match.start()].rstrip()
            block_id = f' id="^{escape(block_id_match.group(1), quote=True)}"'

        out.append(f"<p{block_id}>{_render_inline(text, opts)}</p>")

    return out


def _is_lazy_continuation(line: str) -> bool:
    """引用块内的懒延续行（非引用、非空）。"""
    return bool(line.strip()) and not _starts_block(line)


def _starts_block(line: str) -> bool:
    """判断一行是否开启新的块级结构。"""
    return bool(
        _ATX.match(line)
        or _FENCE.match(line)
        or _HR.match(line)
        or _QUOTE.match(line)
        or _UL_ITEM.match(line)
        or _OL_ITEM.match(line)
    )


def _render_heading(level: int, text: str, opts: RenderOptions) -> str:
    """渲染标题，带锚点。"""
    level = min(max(level + opts.heading_offset, 1), opts.max_heading_level)
    anchor = f' id="{slugify_heading(text)}"' if opts.heading_anchors else ""
    rendered = _render_inline(text, opts)
    return f"<h{level}{anchor}>{rendered}</h{level}>"


def _split_row(line: str) -> list[str]:
    """切分表格行。"""
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells: list[str] = []
    buf: list[str] = []
    escaped = False
    for ch in stripped:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\":
            buf.append(ch)
            escaped = True
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    cells.append("".join(buf).strip())
    return cells


def _parse_table(lines: list[str], start: int, opts: RenderOptions) -> tuple[str, int]:
    """解析 GFM 表格。"""
    header = _split_row(lines[start])
    align_spec = _split_row(lines[start + 1])

    aligns: list[str] = []
    for spec in align_spec:
        left = spec.startswith(":")
        right = spec.endswith(":")
        aligns.append("center" if left and right else "right" if right else "left" if left else "")

    i = start + 2
    rows: list[list[str]] = []
    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
        rows.append(_split_row(lines[i]))
        i += 1

    def cell_html(text: str, col: int) -> str:
        align = f' style="text-align:{aligns[col]}"' if col < len(aligns) and aligns[col] else ""
        return f"<td{align}>{_render_inline(text, opts)}</td>"

    parts = ["<table>", "<thead><tr>"]
    for col, text in enumerate(header):
        align = f' style="text-align:{aligns[col]}"' if col < len(aligns) and aligns[col] else ""
        parts.append(f"<th{align}>{_render_inline(text, opts)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>")
        for col, text in enumerate(row):
            parts.append(cell_html(text, col))
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts), i


def _parse_list(lines: list[str], start: int, opts: RenderOptions) -> tuple[str, int]:
    """解析有序 / 无序列表，支持缩进的嵌套。"""
    i = start
    ordered = bool(_OL_ITEM.match(lines[i]))
    base_indent = len(_UL_ITEM.match(lines[i]).group(1)) if not ordered else len(_OL_ITEM.match(lines[i]).group(1))

    items: list[str] = []
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            # 空行后若仍属同一列表则保留为松散间隔
            if i + 1 < len(lines) and (_UL_ITEM.match(lines[i + 1]) or _OL_ITEM.match(lines[i + 1])):
                i += 1
                continue
            break

        match_ul = _UL_ITEM.match(line)
        match_ol = _OL_ITEM.match(line)
        match = match_ul or match_ol
        if not match:
            indent = len(line) - len(line.lstrip(" "))
            if indent > base_indent and items:
                # 列表项内的懒延续行
                items[-1] += "\n" + line.strip()
                i += 1
                continue
            break

        indent = len(match.group(1))
        if indent > base_indent:
            nested, i = _parse_list(lines, i)
            if items:
                items[-1] = items[-1].rstrip() + nested
            continue
        if indent < base_indent:
            break

        is_ordered_here = match_ol is not None
        if is_ordered_here != ordered:
            break

        content = match.group(3)
        i += 1

        # 收集该列表项的后续行（缩进的段落、嵌套内容）
        continuation: list[str] = []
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip():
                break
            nxt_indent = len(nxt) - len(nxt.lstrip(" "))
            if _UL_ITEM.match(nxt) or _OL_ITEM.match(nxt):
                if nxt_indent <= base_indent:
                    break
                continuation.append(nxt[base_indent + 2 :] if len(nxt) > base_indent else nxt.strip())
                i += 1
                continue
            if nxt_indent > base_indent:
                continuation.append(nxt.strip())
                i += 1
                continue
            if _starts_block(nxt):
                break
            continuation.append(nxt.strip())
            i += 1

        item_body = content
        if continuation:
            item_body += "\n" + "\n".join(continuation)
        items.append(item_body)

    tag = "ol" if ordered else "ul"
    rendered_items = []
    for body_text in items:
        parts = []
        for chunk in re.split(r"\n{2,}", body_text.strip()):
            chunk = chunk.strip()
            if not chunk:
                continue
            if re.search(r"(^|\n)[ \t]*(?:[-*+]|\d+[.)])[ \t]+", chunk):
                parts.append(_render_nested_list(chunk, opts))
            else:
                parts.append(_render_inline(chunk, opts))
        rendered_items.append("<li>" + "".join(parts) + "</li>")

    return f"<{tag}>" + "".join(rendered_items) + f"</{tag}>", i


def _render_nested_list(chunk: str, opts: RenderOptions) -> str:
    """渲染列表项内部的嵌套列表。"""
    blocks = _parse_blocks(chunk.split("\n"), opts)
    return "".join(b for b in blocks if b.strip())


# --------------------------------------------------------------------------
# 完整文档
# --------------------------------------------------------------------------

_BASE_CSS = """
body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
       line-height: 1.7; color: #e6e8ee; background: transparent; padding: 4px 8px; }
h1, h2, h3, h4, h5, h6 { line-height: 1.35; margin: 1.4em 0 .6em; font-weight: 600; }
h1 { font-size: 1.75em; } h2 { font-size: 1.45em; } h3 { font-size: 1.2em; }
p { margin: .7em 0; }
a { color: #2DD4BF; text-decoration: none; }
code { font-family: "JetBrains Mono", Consolas, monospace; font-size: .9em;
       background: rgba(127,127,127,.16); padding: .12em .36em; border-radius: 4px; }
pre { background: rgba(127,127,127,.12); padding: .9em 1.1em; border-radius: 8px;
      overflow-x: auto; margin: .9em 0; }
pre code { background: none; padding: 0; font-size: .86em; line-height: 1.55; }
blockquote { margin: .8em 0; padding: .3em 1em; border-left: 3px solid rgba(127,127,127,.45);
            color: #a8adbd; }
table { border-collapse: collapse; margin: 1em 0; width: 100%; }
th, td { border: 1px solid rgba(127,127,127,.3); padding: .45em .7em; text-align: left; }
th { background: rgba(127,127,127,.12); font-weight: 600; }
hr { border: none; border-top: 1px solid rgba(127,127,127,.28); margin: 1.6em 0; }
ul, ol { padding-left: 1.5em; margin: .6em 0; }
li { margin: .25em 0; }
img { max-width: 100%; border-radius: 6px; }
.kv-link-unresolved { color: #FBBF24; border-bottom: 1px dashed rgba(251,191,36,.5); }
.kv-embed { display: inline-block; padding: .1em .45em; border-radius: 5px;
            background: rgba(127,127,127,.14); font-size: .92em; }
.kv-embed-missing { color: #F87171; }
.kv-tag { color: #60A5FA; background: rgba(96,165,250,.14);
          padding: .06em .42em; border-radius: 10px; font-size: .9em; }
.kv-tag-hash { opacity: .6; margin-right: .1em; }
img.kv-embed-image { max-height: 420px; }
"""


def render_document(markdown: str, title: str = "", options: RenderOptions | None = None) -> str:
    """渲染为可直接放入 ``QTextBrowser`` 的完整 HTML 文档。"""
    opts = options or RenderOptions()
    body_html = render(markdown, opts)

    heading = f"<title>{escape(title)}</title>" if title else ""
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"{heading}<style>{_BASE_CSS}{opts.extra_css}</style></head>"
        f"<body>{body_html}</body></html>"
    )