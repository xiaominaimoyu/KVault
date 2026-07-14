import argparse
import logging
import sys

from mcp.server.fastmcp import FastMCP

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


mcp = FastMCP("kvault")


@mcp.tool()
def search_knowledge_base_tool(
    query: str,
    top_k: int = 5,
    partition_filter: str | None = None,
    tag_filters: list[str] | None = None,
) -> dict:
    """在个人知识库中执行语义检索。"""
    return search_knowledge_base(
        query=query,
        top_k=top_k,
        partition_filter=partition_filter,
        tag_filters=tag_filters,
    )


@mcp.tool()
def list_knowledge_bases_tool() -> dict:
    """列出所有分区及文档数量。"""
    return list_knowledge_bases()


@mcp.tool()
def get_document_preview_tool(document_id: str) -> dict:
    """获取指定文档的预览内容和元信息。"""
    return get_document_preview(document_id)


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

    mcp.run(transport=args.transport, port=args.port)


if __name__ == "__main__":
    main()
