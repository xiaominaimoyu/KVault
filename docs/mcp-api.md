# KVault MCP API 文档

## 概述

KVault 通过 Model Context Protocol (MCP) 向外部 AI 代理暴露知识库检索能力。本文件与实际代码实现保持一致。

## 协议支持

- **服务名称**: `kvault`
- **传输方式**: `stdio`（默认）或 `sse`
- **启动命令**:
  ```bash
  python -m mcp_server
  python -m mcp_server --transport stdio
  python -m mcp_server --transport sse --port 8080
  ```

> **工作目录必须是项目根目录**（即含 `core/`、`mcp_server/`、`config.json` 的目录），
> 否则 `python -m mcp_server` 找不到模块，且 `config.json` 会解析到别处。

## 环境变量

| 变量 | 说明 |
|------|------|
| `CHROMA_PATH` | 覆盖 ChromaDB 数据目录 |
| `DB_PATH` | 覆盖 SQLite 数据库路径 |
| `WORKSPACE` | 默认工作区 ID（不传 workspace 参数时使用） |
| `KVAULT_ALLOW_WRITE` | 设为 `1` 时开放笔记写入工具，默认只读 |

> 使用多工作区布局时**不要设置** `CHROMA_PATH` / `DB_PATH`：服务端会用
> `chroma_dir.parent.parent` 反推工作区根目录，覆盖这两个变量会让它指向错误的
> workspace，表现为「笔记列表为空」。如有需要，请改 `config.json` 而不要用环境变量。

## 工具列表

### 1. search_knowledge_base_tool

**功能**: 在个人知识库中执行语义检索。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 自然语言查询文本 |
| top_k | int | 否 | 返回结果数量，默认 5，范围 1-50 |
| partition_filter | string | 否 | 按分区名称过滤 |
| tag_filters | list[string] | 否 | 按标签名称过滤，命中任意标签即返回 |
| workspace | string | 否 | 工作区 ID，不传时使用默认工作区 |

**返回结构**:

```json
{
  "results": [
    {
      "document_id": "uuid-string",
      "document_name": "document.pdf",
      "chunk_id": "chunk-uuid-string",
      "chunk_index": 0,
      "score": 0.8523,
      "content": "检索到的文本片段内容（最多 800 字符）..."
    }
  ]
}
```

**错误返回**:

```json
{ "error": "query 不能为空" }
{ "error": "服务初始化失败: ..." }
{ "error": "检索失败: ..." }
{ "error": "workspace not found" }
```

### 2. list_knowledge_bases_tool

**功能**: 列出所有分区及文档数量。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| workspace | string | 否 | 工作区 ID，不传时使用默认工作区 |

**返回结构**:

```json
{
  "partitions": [
    {
      "id": "uuid-string",
      "name": "默认分区",
      "document_count": 12
    }
  ]
}
```

**错误返回**:

```json
{ "error": "服务初始化失败: ..." }
{ "error": "列出分区失败: ..." }
```

### 3. get_document_preview_tool

**功能**: 获取指定文档的预览内容和元信息。

**参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| document_id | string | 是 | 文档 ID；也支持按文件名模糊匹配 |
| workspace | string | 否 | 工作区 ID，不传时使用默认工作区 |

**返回结构**:

```json
{
  "document": {
    "id": "uuid-string",
    "name": "document.pdf",
    "file_ext": ".pdf",
    "partition": "默认分区",
    "status": "indexed",
    "chunk_count": 22,
    "tags": ["标签1", "标签2"],
    "preview": "文档前 2000 字符预览内容..."
  }
}
```

**错误返回**:

```json
{ "error": "document_id 不能为空" }
{ "error": "文档不存在" }
{
  "error": "找到多个匹配文档，请使用精确的 document_id",
  "matches": [
    { "id": "uuid-1", "name": "report.pdf" },
    { "id": "uuid-2", "name": "report-old.pdf" }
  ]
}
```

### 4. 笔记库工具

笔记工具直接读写 vault（Markdown 文件 + SQLite 索引），与文档检索工具互补。

**只读（默认可用）**

| 工具 | 参数 | 说明 |
|------|------|------|
| `list_notes_tool` | `folder` / `tag` / `limit` / `workspace` | 列出笔记，可按目录或层级标签过滤 |
| `get_note_tool` | `path` / `workspace` | 读取笔记全文，返回标签、反链与出链 |
| `search_notes_tool` | `query` / `limit` / `workspace` | 正文关键词检索（字面匹配，多关键词全命中） |
| `get_backlinks_tool` | `path` / `workspace` | 查询反链 / 出链与断链数量 |
| `list_tags_tool` | `workspace` | 列出全部标签及笔记数 |

**写入（需 `KVAULT_ALLOW_WRITE=1`）**

| 工具 | 参数 | 说明 |
|------|------|------|
| `create_note_tool` | `title` / `content` / `folder` / `tags` | 新建笔记并写入 frontmatter |
| `append_to_note_tool` | `path` / `content` | 向已有笔记追加内容 |
| `update_note_links_tool` | `path` / `link_targets` / `mode` | 追加或移除 `[[wiki 链接]]` |

未开启写入时返回：

```json
{
  "error": "当前处于只读模式，无法创建笔记",
  "write_allowed": false,
  "hint": "写入 vault 需要设置环境变量 KVAULT_ALLOW_WRITE=1 后重启 MCP 服务"
}
```

## 使用示例

### Python MCP 客户端

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["-m", "mcp_server"],
    env=None,
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        result = await session.call_tool(
            "search_knowledge_base_tool",
            {"query": "机器学习", "top_k": 3}
        )
        print(result)
```

### Claude Desktop / Cursor / Trae 配置示例

在客户端 MCP 配置中添加（Claude Desktop 为 `%APPDATA%\Claude\claude_desktop_config.json`，
Trae 为「设置 → MCP → 手动配置」）：

```json
{
  "mcpServers": {
    "kvault": {
      "command": "D:\\project file\\KVault-main\\.build-venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server", "--transport", "stdio"],
      "cwd": "D:\\project file\\KVault-main",
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

要点：

- `command` 必须指向**已安装依赖的 Python 解释器**（项目内 `.build-venv` 或自建虚拟环境），不要用系统 `python`；
- `cwd` 必须是项目根目录；
- **不要**在 `env` 中设置 `CHROMA_PATH` / `DB_PATH`，否则工作区定位会失效，表现为笔记列表为空；
- 需要 AI 写入笔记时，在 `env` 中追加 `"KVAULT_ALLOW_WRITE": "1"`。

## 配置

工作区、数据目录与嵌入后端由项目根目录的 `config.json` 决定，MCP 服务只读不写：

```json
{
  "embedding_backend": "llama_cpp_server",
  "llama_server": {
    "base_url": "http://127.0.0.1:8001",
    "model": "",
    "timeout": 120
  },
  "mcp_enabled": true
}
```

`mcp_enabled` 只影响 GUI 设置页的显示状态，不参与服务端启停——MCP 是否可用，
取决于是否有人以 stdio / SSE 方式启动了 `python -m mcp_server`。

## 安全说明

- MCP 服务仅支持本地连接
- 不提供远程访问接口
- 建议在受信任环境中运行
- 文档检索工具为只读；笔记写入工具默认关闭，需显式设置 `KVAULT_ALLOW_WRITE=1`
- 所有路径经 `core.vault` 越界校验，无法读写 vault 之外的文件