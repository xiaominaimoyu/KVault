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

## 环境变量

| 变量 | 说明 |
|------|------|
| `CHROMA_PATH` | 覆盖 ChromaDB 数据目录 |
| `DB_PATH` | 覆盖 SQLite 数据库路径 |

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
```

### 2. list_knowledge_bases_tool

**功能**: 列出所有分区及文档数量。

**参数**: 无

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

### Claude Desktop 配置示例

在 Claude Desktop 配置文件中添加（路径通常为 `%APPDATA%\Claude\settings.json`）：

```json
{
  "mcpServers": {
    "kvault": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "D:\\project file\\KVault",
      "env": {
        "CHROMA_PATH": "D:\\project file\\KVault\\data\\chroma_db",
        "DB_PATH": "D:\\project file\\KVault\\data\\kb.sqlite"
      }
    }
  }
}
```

> 注意：请根据实际安装路径调整 `cwd`、`CHROMA_PATH` 和 `DB_PATH`。

## 配置

在 `config.json` 中可调整以下相关配置：

```json
{
  "embedding_model": "modelscope.cn/Embedding-GGUF/bge-large-zh-v1.5:latest",
  "ollama_base_url": "http://localhost:11434",
  "top_k": 5,
  "similarity_threshold": 0.5
}
```

## 安全说明

- MCP 服务仅支持本地连接
- 不提供远程访问接口
- 建议在受信任环境中运行
- 工具均为只读操作，不提供导入、删除、修改知识库的能力