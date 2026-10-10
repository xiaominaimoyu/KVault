"""MCP 服务注册测试。

``mcp_server.server`` 之前从未被测试覆盖，导致 SDK 2.x 把 ``FastMCP``
更名为 ``MCPServer`` 后服务直接启动失败却无人察觉。这里确保模块可导入、
工具全部注册。
"""

import pytest


class TestServerModule:
    def test_module_imports(self):
        """server 模块必须能在当前安装的 MCP SDK 下成功导入。"""
        import mcp_server.server as server

        assert server.mcp is not None

    def test_server_name(self):
        import mcp_server.server as server

        assert server.mcp.name == "kvault"

    def test_sdk_compat_import(self):
        """无论 SDK 1.x（FastMCP）还是 2.x（MCPServer）都能导入。"""
        from mcp_server.server import _ServerBase

        assert hasattr(_ServerBase, "tool")
        assert hasattr(_ServerBase, "run")

    def test_all_tools_registered(self):
        import asyncio

        from mcp_server.server import mcp

        tools = asyncio.run(mcp.list_tools())
        names = {tool.name for tool in tools}

        # 既有只读工具
        assert "search_knowledge_base_tool" in names
        assert "list_knowledge_bases_tool" in names
        assert "get_document_preview_tool" in names
        # 新增笔记工具
        assert "list_notes_tool" in names
        assert "get_note_tool" in names
        assert "search_notes_tool" in names
        assert "get_backlinks_tool" in names
        assert "list_tags_tool" in names
        assert "create_note_tool" in names
        assert "append_to_note_tool" in names
        assert "update_note_links_tool" in names

    def test_tool_count(self):
        import asyncio

        from mcp_server.server import mcp

        assert len(asyncio.run(mcp.list_tools())) == 11

    def test_every_tool_has_description(self):
        """工具描述是 AI 代理选择工具的依据，不能为空。"""
        import asyncio

        from mcp_server.server import mcp

        for tool in asyncio.run(mcp.list_tools()):
            assert tool.description, f"{tool.name} 缺少描述"

    def test_write_tools_document_the_gate(self):
        """写入工具必须在描述中说明开关，避免代理误用。"""
        import asyncio

        from mcp_server.server import mcp

        tools = {t.name: t.description for t in asyncio.run(mcp.list_tools())}
        for name in ("create_note_tool", "append_to_note_tool", "update_note_links_tool"):
            assert "KVAULT_ALLOW_WRITE" in tools[name]

    def test_readonly_tools_make_no_write_claim(self):
        import asyncio

        from mcp_server.server import mcp

        tools = {t.name: t.description for t in asyncio.run(mcp.list_tools())}
        assert "KVAULT_ALLOW_WRITE" not in tools["get_note_tool"]


class TestMainEntry:
    def test_main_passes_transport(self, monkeypatch):
        import sys

        import mcp_server.server as server

        captured = {}

        def fake_run(transport="stdio", **kwargs):
            captured.update({"transport": transport, **kwargs})

        monkeypatch.setattr(server.mcp, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["kvault-mcp", "--transport", "stdio"])
        server.main()
        assert captured["transport"] == "stdio"

    def test_sse_transport_forwards_port(self, monkeypatch):
        """SSE 模式必须把端口传下去（SDK 2.x 走 run() 参数）。"""
        import sys

        import mcp_server.server as server

        captured = {}

        def fake_run(transport="stdio", **kwargs):
            captured.update({"transport": transport, **kwargs})

        monkeypatch.setattr(server.mcp, "run", fake_run)
        monkeypatch.setattr(sys, "argv", ["kvault-mcp", "--transport", "sse", "--port", "9090"])
        server.main()

        assert captured["transport"] == "sse"
        assert captured.get("port") == 9090

    def test_set_sse_port_tolerates_missing_field(self):
        """SDK 2.x 的 settings 没有 port 字段时不应抛异常。"""
        import mcp_server.server as server

        # 既不报错，也不静默吞掉调用方的意图
        server._set_sse_port(server.mcp, 8080)