import argparse
import logging
import sys

# MCP SDK 2.x 把 FastMCP 更名为 MCPServer，1.x 仍叫 FastMCP。
# 两者的 tool()/run()/settings 接口一致，这里做兼容导入，
# 避免 requirements.txt 的下界写法在装到 2.x 时直接启动失败。
try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _ServerBase
except ModuleNotFoundError:  # pragma: no cover - 取决于已安装的 SDK 版本
    from mcp.server.fastmcp import FastMCP as _ServerBase  # type: ignore[no-redef]

from mcp_server.note_tools import (
    append_to_note,
    create_note,
    get_backlinks,
    get_note,
    list_notes,
    list_tags,
    search_notes,
    update_note_links,
)
from mcp_server.tools import (
    get_document_preview,
    list_knowledge_bases,
    search_knowledge_base,
)


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


mcp = _ServerBase("kvault")

logger = logging.getLogger(__name__)


@mcp.tool()
def search_knowledge_base_tool(
    query: str,
    top_k: int = 5,
    partition_filter: str | None = None,
    tag_filters: list[str] | None = None,
    workspace: str | None = None,
) -> dict:
    """在个人知识库中执行语义检索。"""
    return search_knowledge_base(
        query=query,
        top_k=top_k,
        partition_filter=partition_filter,
        tag_filters=tag_filters,
        workspace=workspace,
    )


@mcp.tool()
def list_knowledge_bases_tool(workspace: str | None = None) -> dict:
    """列出所有分区及文档数量。"""
    return list_knowledge_bases(workspace=workspace)


@mcp.tool()
def get_document_preview_tool(
    document_id: str,
    workspace: str | None = None,
) -> dict:
    """获取指定文档的预览内容和元信息。"""
    return get_document_preview(document_id, workspace=workspace)


# --------------------------------------------------------------------------
# 笔记库工具（只读）
# --------------------------------------------------------------------------


@mcp.tool()
def list_notes_tool(
    workspace: str | None = None,
    folder: str | None = None,
    tag: str | None = None,
    limit: int = 100,
) -> dict:
    """列出 vault 中的笔记，可按目录或标签过滤。"""
    return list_notes(workspace=workspace, folder=folder, tag=tag, limit=limit)


@mcp.tool()
def get_note_tool(path: str, workspace: str | None = None) -> dict:
    """读取一篇笔记的完整内容及其链接关系。

    ``path`` 可以是路径（``目录/笔记.md``）、标题或链接目标。
    """
    return get_note(path, workspace=workspace)


@mcp.tool()
def search_notes_tool(query: str, limit: int = 10, workspace: str | None = None) -> dict:
    """在笔记正文中做关键词检索（字面匹配，与语义检索互补）。"""
    return search_notes(query, limit=limit, workspace=workspace)


@mcp.tool()
def get_backlinks_tool(path: str, workspace: str | None = None) -> dict:
    """查询一篇笔记的反向链接与出链，可用于发现断链。"""
    return get_backlinks(path, workspace=workspace)


@mcp.tool()
def list_tags_tool(workspace: str | None = None) -> dict:
    """列出全部标签及其关联笔记数。"""
    return list_tags(workspace=workspace)


# --------------------------------------------------------------------------
# 笔记库工具（写入，需 KVAULT_ALLOW_WRITE=1）
# --------------------------------------------------------------------------


@mcp.tool()
def create_note_tool(
    title: str,
    content: str = "",
    folder: str = "",
    tags: list[str] | None = None,
    workspace: str | None = None,
) -> dict:
    """新建一篇笔记。需要环境变量 KVAULT_ALLOW_WRITE=1 开启写入。"""
    return create_note(
        title=title, content=content, folder=folder, tags=tags, workspace=workspace
    )


@mcp.tool()
def append_to_note_tool(
    path: str, content: str, workspace: str | None = None
) -> dict:
    """向已有笔记追加内容。需要环境变量 KVAULT_ALLOW_WRITE=1 开启写入。"""
    return append_to_note(path=path, content=content, workspace=workspace)


@mcp.tool()
def update_note_links_tool(
    path: str,
    link_targets: list[str],
    mode: str = "append",
    workspace: str | None = None,
) -> dict:
    """为笔记添加或移除 wiki 链接。需要环境变量 KVAULT_ALLOW_WRITE=1 开启写入。"""
    return update_note_links(
        path=path, link_targets=link_targets, mode=mode, workspace=workspace
    )


def _set_sse_port(server, port: int) -> None:
    """配置 SSE 监听端口。

    SDK 1.x 通过 ``mcp.settings.port`` 设置；2.x 移除了该字段，改由
    ``run()`` 的关键字参数传入。先尝试旧路径，失败则由调用方走 kwargs。
    """
    try:
        server.settings.port = port
    except (AttributeError, ValueError):
        logger.debug("当前 SDK 不支持 settings.port，改用 run() 参数传入")


def main():
    _setup_logging()
    parser = argparse.ArgumentParser(description="KVault MCP Server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse"],
        help="传输协议，默认 stdio",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="SSE 模式监听端口，默认 8080",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        _set_sse_port(mcp, args.port)

    try:
        mcp.run(transport=args.transport, port=args.port)
    except TypeError:
        # SDK 1.x 的 run() 不接受 port 参数
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
