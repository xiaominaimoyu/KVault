"""Markdown YAML frontmatter 解析与序列化。

Obsidian 的笔记属性（properties）存储在文件头部的 `---` 围栏中。本模块实现一个
**只覆盖 frontmatter 常用子集**的 YAML 解析器，不引入额外依赖：

- 标量：字符串（含单双引号）、整数、浮点、布尔、null
- 列表：行内 `[a, b]` 与块状 `- item`
- 嵌套映射：缩进一级，用于 `cssclasses` 等键

设计原则：**解析失败绝不抛异常**。遇到无法识别的 YAML 结构时降级为"无 frontmatter"
并保留原文，绝不破坏用户数据。

常用键约定：

- ``tags``    —— 笔记标签，支持 ``#`` 前缀，解析时统一去除前缀
- ``aliases`` —— 别名，用于 `[[别名]]` 链接解析
- ``title``   —— 显示标题，缺省时回退为文件名
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DELIMITER = "---"

# Obsidian 允许 frontmatter 围栏与正文之间有空行，统一剥离
_BLANK_LINES_BEFORE_BODY = 1


class FrontmatterError(ValueError):
    """frontmatter 结构非法（解析器已降级处理，此异常仅供严格校验场景使用）。"""


@dataclass
class Frontmatter:
    """一次 frontmatter 解析的结果。

    :param data: 解析出的键值映射，未解析到时为空字典
    :param body: 去除 frontmatter 之后的正文
    :param present: 原文是否包含 frontmatter 围栏
    :param body_offset: 正文第一行在**原文**中的行号（0 基），用于编辑器定位
    """

    data: dict = field(default_factory=dict)
    body: str = ""
    present: bool = False
    body_offset: int = 0

    def get(self, key: str, default=None):
        """读取单个属性，键名大小写不敏感。"""
        if key in self.data:
            return self.data[key]
        lowered = key.lower()
        for k, v in self.data.items():
            if isinstance(k, str) and k.lower() == lowered:
                return v
        return default

    def set(self, key: str, value) -> None:
        """写入属性；若已存在同名键（忽略大小写）则原地覆盖，避免产生重复键。"""
        lowered = key.lower()
        for k in list(self.data):
            if isinstance(k, str) and k.lower() == lowered:
                if k != key:
                    del self.data[k]
                self.data[key] = value
                return
        self.data[key] = value

    @property
    def title(self) -> str:
        """笔记标题：取 ``title`` 属性，缺省为空字符串。"""
        value = self.get("title")
        return value.strip() if isinstance(value, str) else ""

    @property
    def aliases(self) -> list[str]:
        """别名列表，统一为去空白、去空的字符串列表。"""
        return _as_str_list(self.get("aliases"))

    @property
    def tags(self) -> list[str]:
        """标签列表，统一去除 `#` 前缀并保持书写顺序去重。"""
        raw = self.get("tags") or self.get("tag")
        tags: list[str] = []
        for item in _as_str_list(raw):
            cleaned = item.lstrip("#").strip()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
        return tags


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------


def parse(text: str) -> Frontmatter:
    """解析 ``text`` 的 frontmatter。

    无 frontmatter、或围栏未闭合时，返回 ``present=False`` 且 ``body`` 为原文。
    该函数不会抛出异常。
    """
    if not text:
        return Frontmatter(data={}, body="", present=False, body_offset=0)

    lines = text.split("\n")

    # 允许文件以 UTF-8 BOM 开头
    first = lines[0].lstrip("\ufeff").rstrip()
    if first != DELIMITER:
        return Frontmatter(data={}, body=text, present=False, body_offset=0)

    # 找到闭合围栏
    end = -1
    for i in range(1, len(lines)):
        if lines[i].rstrip() == DELIMITER:
            end = i
            break
    if end == -1:
        # 围栏未闭合：视为无 frontmatter，保留原文
        return Frontmatter(data={}, body=text, present=False, body_offset=0)

    raw_lines = lines[1:end]
    body_lines = lines[end + 1 :]

    # 剥离围栏与正文之间的一个空行（Obsidian 保存时的常见形态）
    offset = end + 1
    while (
        offset < len(lines)
        and body_lines
        and body_lines[0].strip() == ""
        and len([ln for ln in body_lines[:_BLANK_LINES_BEFORE_BODY]]) > 0
    ):
        body_lines = body_lines[1:]
        offset += 1
        break

    body = "\n".join(body_lines)

    try:
        data = _parse_block(raw_lines)
    except Exception:  # noqa: BLE001 —— 任何解析异常都降级，不破坏用户数据
        return Frontmatter(data={}, body=text, present=False, body_offset=0)

    return Frontmatter(data=data, body=body, present=True, body_offset=offset)


def _parse_block(lines: list[str]) -> dict:
    """解析缩进块，返回映射。非映射内容会被忽略。"""
    value, _ = _parse_node(lines, 0, _indent_of(lines[0]) if lines else 0)
    return value if isinstance(value, dict) else {}


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _parse_node(lines: list[str], index: int, indent: int):
    """解析从 ``index`` 开始、缩进为 ``indent`` 的节点，返回 ``(值, 下一行索引)``。"""
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return None, index

    if lines[index].lstrip().startswith("- ") or lines[index].strip() == "-":
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_list(lines: list[str], index: int, indent: int):
    """解析块状列表，支持嵌套标量与嵌套映射。"""
    items: list = []
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        current_indent = _indent_of(line)
        if current_indent < indent:
            break
        stripped = line.strip()
        if not stripped.startswith("-"):
            break

        content = stripped[1:].strip()
        index += 1

        if not content:
            # `-` 单独一行：值来自下一层缩进
            value, index = _parse_node(lines, index, current_indent + 1)
            items.append(value)
        elif _looks_like_mapping(content):
            # `- key: value` 形式：收集该条目下的所有同行/缩进行
            sub_lines = [" " * (current_indent + 2) + content]
            while index < len(lines):
                nxt = lines[index]
                if not nxt.strip():
                    index += 1
                    continue
                if _indent_of(nxt) <= current_indent:
                    break
                sub_lines.append(nxt)
                index += 1
            value, _ = _parse_node(sub_lines, 0, current_indent + 2)
            items.append(value)
        else:
            items.append(_parse_scalar(content))
    return items, index


def _parse_mapping(lines: list[str], index: int, indent: int):
    """解析缩进映射。"""
    result: dict = {}
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        current_indent = _indent_of(line)
        if current_indent < indent:
            break
        if current_indent > indent:
            # 缩进异常，跳过以避免死循环
            index += 1
            continue

        stripped = line.strip()
        if stripped.startswith("- "):
            break

        key, raw_value = _split_key_value(stripped)
        if key is None:
            index += 1
            continue

        index += 1
        raw_value = raw_value.strip()

        if raw_value:
            result[key] = _parse_scalar(raw_value)
        else:
            # 值位于下一层缩进
            child_indent = None
            probe = index
            while probe < len(lines):
                if lines[probe].strip():
                    child_indent = _indent_of(lines[probe])
                    break
                probe += 1
            if child_indent is not None and child_indent > current_indent:
                value, index = _parse_node(lines, index, child_indent)
                result[key] = value
            else:
                result[key] = None
    return result, index


def _looks_like_mapping(text: str) -> bool:
    key, _ = _split_key_value(text)
    return key is not None


def _split_key_value(text: str) -> tuple[str | None, str]:
    """按第一个顶层的 ``:`` 切分键值对，忽略引号与行内链接中的冒号。"""
    in_single = False
    in_double = False
    depth = 0

    for i, ch in enumerate(text):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == ":" and depth == 0:
                after = text[i + 1 : i + 2]
                # 结尾冒号或冒号后跟空格才算分隔符，避免命中 `http://`
                if after in ("", " "):
                    key = text[:i].strip()
                    if not key or key.startswith(("'", '"')) and key.count("'") != 2 and key.count('"') != 2:
                        return None, ""
                    return key, text[i + 1 :]
    return None, ""


_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}
_NULL = {"null", "~", "none", ""}


def _parse_scalar(text: str):
    """解析 YAML 标量或行内列表。"""
    text = text.strip()

    if text.startswith("[") and text.endswith("]"):
        return [_parse_scalar(part) for part in _split_inline_list(text[1:-1])]

    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        inner = text[1:-1]
        if text[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
        return inner.replace("''", "'")

    lowered = text.lower()
    if lowered in _NULL:
        return None
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False

    if re.fullmatch(r"[+-]?\d+", text):
        try:
            return int(text)
        except ValueError:
            return text
    if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?", text):
        try:
            return float(text)
        except ValueError:
            return text

    return text


def _split_inline_list(text: str) -> list[str]:
    """切分行内列表，忽略引号内的逗号。"""
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    depth = 0

    for ch in text:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(buf))
                buf = []
                continue
        buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)

    return [p.strip() for p in parts if p.strip()]


def _as_str_list(value) -> list[str]:
    """把属性值规整为字符串列表，兼容标量写法。"""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = [v for v in value]
    else:
        return []

    out: list[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, bool):
            out.append("true" if item else "false")
        elif isinstance(item, (int, float)):
            out.append(str(item))
        elif isinstance(item, str):
            out.append(item.strip())
    return [s for s in out if s]


# --------------------------------------------------------------------------
# 序列化
# --------------------------------------------------------------------------


def dump(data: dict | None, body: str = "") -> str:
    """把属性映射与正文序列化为完整 Markdown 文本。

    ``data`` 为空且正文不含 frontmatter 时直接返回正文。
    """
    body = body or ""
    if not data:
        return body
    lines = [DELIMITER]
    lines.extend(_dump_mapping(data, 0))
    lines.append(DELIMITER)
    front = "\n".join(lines)
    if not body:
        return front + "\n"
    return front + "\n\n" + body.lstrip("\n")


def _dump_mapping(data: dict, indent: int) -> list[str]:
    pad = " " * indent
    lines: list[str] = []

    for key, value in data.items():
        if value is None:
            lines.append(f"{pad}{key}:")
        elif isinstance(value, bool):
            lines.append(f"{pad}{key}: {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{pad}{key}: {value}")
        elif isinstance(value, str):
            lines.append(f"{pad}{key}: {_quote(value)}")
        elif isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.extend(_dump_mapping(value, indent + 2))
        elif isinstance(value, (list, tuple, set)):
            items = [v for v in value if v is not None]
            if not items:
                lines.append(f"{pad}{key}: []")
            elif all(isinstance(v, (str, int, float, bool)) for v in items):
                rendered = ", ".join(
                    _quote(v) if isinstance(v, str) else ("true" if v is True else "false" if v is False else str(v))
                    for v in items
                )
                lines.append(f"{pad}{key}: [{rendered}]")
            else:
                lines.append(f"{pad}{key}:")
                for v in items:
                    if isinstance(v, dict):
                        nested = _dump_mapping(v, indent + 4)
                        if nested:
                            lines.append(" " * (indent + 2) + "- " + nested[0].strip())
                            lines.extend(nested[1:])
                    else:
                        lines.append(f"{' ' * (indent + 2)}- {_quote(str(v))}")
        else:
            lines.append(f"{pad}{key}: {_quote(str(value))}")

    return lines


_NUMERIC = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")


def _quote(text: str) -> str:
    """含特殊字符的字符串加引号，避免序列化后无法回读。

    数字、布尔、null 形态的字符串必须加引号，否则回读时类型会漂移
    （例如 ``"1"`` 会被读成整数 ``1``）。
    """
    if text == "":
        return '""'
    needs = (
        text.strip() != text
        or text[0] in "#&*!|>%@`{}[],\"'"
        or ": " in text
        or text.endswith(":")
        or "\n" in text
        or text.lower() in _TRUE | _FALSE | _NULL
        or _NUMERIC.fullmatch(text) is not None
    )
    if not needs:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


# --------------------------------------------------------------------------
# 便捷操作
# --------------------------------------------------------------------------


def update(text: str, updates: dict) -> str:
    """在保留其它属性与正文的前提下更新部分属性。"""
    fm = parse(text)
    data = dict(fm.data)
    for key, value in updates.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return dump(data, fm.body)


def ensure_tags(text: str, tags: list[str]) -> str:
    """合并标签到 frontmatter 的 ``tags``，去重且保持顺序。"""
    fm = parse(text)
    existing = fm.tags
    for tag in tags:
        cleaned = str(tag).lstrip("#").strip()
        if cleaned and cleaned not in existing:
            existing.append(cleaned)
    return update(text, {"tags": existing})