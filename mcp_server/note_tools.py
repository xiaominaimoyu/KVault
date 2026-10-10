"""MCP 笔记工具。

原有的 ``mcp_server.tools`` 是**严格只读**的（设计上刻意不提供任何写入能力）。
本模块提供对 vault 的读写工具，让 AI 代理能够真正参与知识库的沉淀：

只读（默认可用）

- :func:`list_notes` —— 列出笔记
- :func:`get_note` —— 读取笔记全文
- :func:`search_notes` —— 关键词检索笔记
- :func:`get_backlinks` —— 查询反向链接

写入（需显式开启）

- :func:`create_note` —— 新建笔记
- :func:`append_to_note` —— 追加内容
- :func:`update_note_links` —— 插入 wiki 链接

安全约束

1. 写入能力默认关闭，必须通过环境变量 ``KVAULT_ALLOW_WRITE=1`` 显式开启。
2. 所有路径都经过 :mod:`core.vault` 的越界校验，无法写到 vault 之外。
3. 写入内容在保存时会被 ``core.markdown`` 的转义逻辑保护，笔记中的 HTML
   不可能在 KVault 内被当作可执行内容。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from core.note_store import NoteStore
from core.title import excerpt
from core.vault import VaultError

logger = logging.getLogger(__name__)

_MAX_CONTENT_LEN = 8000
_MAX_LIST = 200

_store_cache: dict[str, NoteStore] = {}


def write_allowed() -> bool:
    """是否允许写入 vault。

    默认关闭；设置环境变量 ``KVAULT_ALLOW_WRITE=1`` 后开启。
    """
    return os.getenv("KVAULT_ALLOW_WRITE", "").strip().lower() in ("1", "true", "yes", "on")


def _get_store(workspace: Optional[str] = None) -> NoteStore | None:
    """获取指定工作区的笔记库实例。"""
    ws_key = workspace or "default"
    if ws_key in _store_cache:
        return _store_cache[ws_key]

    from mcp_server.tools import _get_services, _load_config

    config = _load_config()
    data_root = config.chroma_dir.parent.parent

    from core.workspace import WorkspaceManager

    ws_manager = WorkspaceManager(config, data_root)
    ws_manager.ensure_default()

    ws = ws_manager.get_workspace(workspace) if workspace else ws_manager.get_current()
    if ws is None:
        return None

    services = _get_services(workspace)
    metadata = services[2] if services else None

    store = NoteStore(str(ws.sqlite_path), ws.base_dir / "vault", metadata)
    _store_cache[ws_key] = store
    return store


def reset_store_cache() -> None:
    """清空缓存，供测试使用。"""
    _store_cache.clear()


def _error(message: str) -> dict:
    return {"error": message}


def _write_error(message: str) -> dict:
    return {
        "error": message,
        "write_allowed": write_allowed(),
        "hint": "写入 vault 需要设置环境变量 KVAULT_ALLOW_WRITE=1 后重启 MCP 服务",
    }


def _resolve(store: NoteStore, reference: str) -> str | None:
    """把用户给的路径/标题/链接目标解析成实际笔记路径。

    越界路径（``../`` 等）由 :mod:`core.vault` 拒绝，这里转成 ``None``，
    让调用方返回结构化错误而不是抛出异常。
    """
    if not reference:
        return None
    reference = reference.strip().lstrip("/")

    try:
        if reference.endswith(".md"):
            return reference if store.get(reference) else None
    except VaultError:
        return None

    resolved = store.vault.resolve_link(reference, "")
    if resolved:
        return resolved

    for record in store.list_notes():
        if record.title == reference or record.name == reference:
            return record.path
    return None


# --------------------------------------------------------------------------
# 只读工具
# --------------------------------------------------------------------------


def list_notes(
    workspace: Optional[str] = None,
    folder: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """列出 vault 中的笔记。

    Args:
        workspace: 工作区 id，缺省为当前工作区。
        folder: 只列出该目录下的笔记（相对 vault 根）。
        tag: 只列出带该标签的笔记，子标签（如 ``项目`` 匹配 ``项目/子项``）同样命中。
        limit: 最多返回条数。
    """
    store = _get_store(workspace)
    if store is None:
        return _error("工作区不存在")

    limit = max(1, min(int(limit), _MAX_LIST))

    if tag:
        paths = store.notes_with_tag(tag)
        notes = [store.get(p) for p in paths]
        notes = [n for n in notes if n is not None]
    else:
        notes = store.list_notes(folder=folder)

    results = []
    for record in notes[:limit]:
        try:
            content = store.read(record.path)
        except (VaultError, OSError):
            content = ""
        results.append(
            {
                "path": record.path,
                "title": record.title,
                "tags": store.tags_for(record.path),
                "word_count": record.word_count,
                "modified": record.updated_at,
                "excerpt": excerpt(content, 160),
            }
        )

    return {"notes": results, "count": len(results), "total": len(notes)}


def get_note(path: str, workspace: Optional[str] = None) -> dict:
    """读取单篇笔记的完整内容。

    Args:
        path: 笔记路径（``目录/笔记.md``）、标题或链接目标。
        workspace: 工作区 id，缺省为当前工作区。
    """
    store = _get_store(workspace)
    if store is None:
        return _error("工作区不存在")

    resolved = _resolve(store, path)
    if resolved is None:
        matches = [
            {"path": r.path, "title": r.title}
            for r in store.list_notes()
            if path.lower() in r.title.lower()
        ]
        if not matches:
            return _error(f"未找到笔记: {path}")
        return {
            "error": f"「{path}」匹配到多篇笔记，请使用更精确的路径",
            "matches": matches[:20],
        }

    try:
        content = store.read(resolved)
    except (VaultError, OSError) as exc:
        return _error(f"读取失败: {exc}")

    record = store.get(resolved)
    return {
        "path": resolved,
        "title": record.title if record else resolved,
        "tags": store.tags_for(resolved),
        "content": content,
        "backlinks": [link.source_path for link in store.backlinks(resolved)],
        "outgoing_links": [link.target_path for link in store.outgoing_links(resolved)],
    }


def search_notes(
    query: str,
    limit: int = 10,
    workspace: Optional[str] = None,
) -> dict:
    """在笔记正文中做关键词检索。

    这是**字面匹配**，与向量语义检索互补——语义检索走
    ``search_knowledge_base``，关键词精确查找走本工具。

    Args:
        query: 关键词，支持空格分隔的多关键词（全部匹配才算命中）。
        limit: 最多返回条数。
        workspace: 工作区 id，缺省为当前工作区。
    """
    store = _get_store(workspace)
    if store is None:
        return _error("工作区不存在")
    if not query or not query.strip():
        return {"error": "查询关键词不能为空"}

    terms = [t.lower() for t in query.split() if t.strip()]
    limit = max(1, min(int(limit), _MAX_LIST))

    matches = []
    for record in store.list_notes():
        try:
            content = store.read(record.path)
        except (VaultError, OSError):
            continue
        lowered = content.lower()
        if not all(term in lowered for term in terms):
            continue

        matches.append(
            {
                "path": record.path,
                "title": record.title,
                "excerpt": excerpt(content, 200),
                # 命中次数作为粗略的相关度信号
                "score": sum(lowered.count(term) for term in terms),
            }
        )

    matches.sort(key=lambda item: (-item["score"], item["path"]))
    return {"results": matches[:limit], "count": min(len(matches), limit)}


def get_backlinks(path: str, workspace: Optional[str] = None) -> dict:
    """查询一篇笔记的反向链接与出链。

    Args:
        path: 笔记路径、标题或链接目标。
        workspace: 工作区 id，缺省为当前工作区。
    """
    store = _get_store(workspace)
    if store is None:
        return _error("工作区不存在")

    resolved = _resolve(store, path)
    if resolved is None:
        return _error(f"未找到笔记: {path}")

    backlinks = [
        {
            "source_path": link.source_path,
            "context": link.context,
            "heading": link.heading,
        }
        for link in store.backlinks(resolved)
    ]
    outgoing = [
        {
            "target": link.target_path,
            "resolved_path": link.target_resolved,
            "broken": link.is_broken,
            "embed": link.is_embed,
        }
        for link in store.outgoing_links(resolved)
    ]

    return {
        "path": resolved,
        "backlinks": backlinks,
        "outgoing_links": outgoing,
        "broken_count": sum(1 for item in outgoing if item["broken"]),
    }


def list_tags(workspace: Optional[str] = None) -> dict:
    """列出全部标签及其笔记数。"""
    store = _get_store(workspace)
    if store is None:
        return _error("工作区不存在")
    counts = store.list_tags()
    return {
        "tags": [{"tag": tag, "count": count} for tag, count in counts.items()],
        "total": len(counts),
    }


# --------------------------------------------------------------------------
# 写入工具
# --------------------------------------------------------------------------


def create_note(
    title: str,
    content: str = "",
    folder: str = "",
    tags: Optional[list[str]] = None,
    workspace: Optional[str] = None,
) -> dict:
    """新建一篇笔记。

    Args:
        title: 笔记标题（同名会自动追加数字后缀）。
        content: 正文；留空则生成一个标题骨架。
        folder: 存放目录，缺省为 vault 根目录。
        tags: 标签列表，写入 frontmatter。
        workspace: 工作区 id，缺省为当前工作区。
    """
    if not write_allowed():
        return _write_error("当前处于只读模式，无法创建笔记")

    store = _get_store(workspace)
    if store is None:
        return _error("工作区不存在")
    if not title or not title.strip():
        return _error("标题不能为空")

    if len(content) > _MAX_CONTENT_LEN:
        return _error(f"内容过长（{len(content)} 字符），上限 {_MAX_CONTENT_LEN}")

    try:
        path = store.create_note(
            title.strip(),
            folder=folder or "",
            content=content,
            tags=tags,
        )
    except VaultError as exc:
        return _error(f"创建失败: {exc}")

    return {"path": path, "title": title.strip(), "created": True}


def append_to_note(
    path: str,
    content: str,
    workspace: Optional[str] = None,
) -> dict:
    """向已有笔记追加内容。

    Args:
        path: 目标笔记路径、标题或链接目标。
        content: 要追加的 Markdown 文本。
        workspace: 工作区 id，缺省为当前工作区。
    """
    if not write_allowed():
        return _write_error("当前处于只读模式，无法写入笔记")

    store = _get_store(workspace)
    if store is None:
        return _error("工作区不存在")

    resolved = _resolve(store, path)
    if resolved is None:
        # ``_resolve`` 对越界路径会返回 None；这里再兜一层，
        # 确保调用方拿到结构化错误而不是异常
        return _error(f"未找到笔记: {path}")
    if not content or not content.strip():
        return _error("追加内容不能为空")

    try:
        existing = store.read(resolved)
    except (VaultError, OSError) as exc:
        return _error(f"读取失败: {exc}")

    if len(existing) + len(content) > _MAX_CONTENT_LEN * 5:
        return _error("追加后篇幅过大，请先拆分笔记")

    separator = "\n\n" if existing.strip() else ""
    updated = existing.rstrip("\n") + separator + content.strip() + "\n"

    try:
        store.save_note(resolved, updated)
    except VaultError as exc:
        return _error(f"写入失败: {exc}")

    return {"path": resolved, "appended": True, "size": len(updated)}


def update_note_links(
    path: str,
    link_targets: list[str],
    mode: str = "append",
    workspace: Optional[str] = None,
) -> dict:
    """给笔记添加或移除 wiki 链接。

    用于把新写的笔记接入知识网络——这是知识库区别于单纯笔记堆的关键动作。

    Args:
        path: 目标笔记路径、标题或链接目标。
        link_targets: 链接目标列表（不含 ``[[ ]]``）。
        mode: ``append`` 追加链接，``remove`` 移除链接。
        workspace: 工作区 id，缺省为当前工作区。
    """
    if not write_allowed():
        return _write_error("当前处于只读模式，无法修改链接")
    if mode not in ("append", "remove"):
        return _error("mode 只能是 append 或 remove")

    store = _get_store(workspace)
    if store is None:
        return _error("工作区不存在")

    resolved = _resolve(store, path)
    if resolved is None:
        return _error(f"未找到笔记: {path}")
    if not link_targets:
        return _error("link_targets 不能为空")

    try:
        existing = store.read(resolved)
    except (VaultError, OSError) as exc:
        return _error(f"读取失败: {exc}")

    changed: list[str] = []
    updated = existing

    for target in link_targets:
        target = target.strip().strip("[]")
        if not target:
            continue
        snippet = f"[[{target}]]"
        if mode == "append":
            if snippet in updated:
                continue
            updated = updated.rstrip("\n") + f"\n\n{snippet}\n"
            changed.append(target)
        else:
            if snippet in updated:
                updated = updated.replace(snippet, target)
                changed.append(target)

    if not changed:
        return {"path": resolved, "changed": [], "message": "无需修改"}

    try:
        store.save_note(resolved, updated)
    except VaultError as exc:
        return _error(f"写入失败: {exc}")

    return {"path": resolved, "changed": changed, "mode": mode}