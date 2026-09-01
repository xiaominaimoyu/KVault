# 阶段 5：MCP 对外接口计划书

> 对应目标：将本地知识库检索能力通过 MCP 暴露给外部 Agent。
> 建议周期：第 4 周后半
> 阶段性质：外部集成阶段

---

## 1. 阶段目标

本阶段实现 MCP Server，让 Claude Desktop、Cursor 或自建 Agent 可以调用本地知识库。MCP 层不重新实现检索逻辑，只复用前面阶段已经稳定的 `core` 模块。

第一版优先支持 stdio 传输，SSE 可作为增强项。

---

## 2. 本阶段范围

### 2.1 必须完成

- 搭建 `mcp_server` 模块。
- 实现 `search_knowledge_base` 工具。
- 实现 `list_knowledge_bases` 工具。
- 实现 `get_document_preview` 工具。
- 支持 stdio 启动模式。
- 编写 MCP 配置示例。
- 完成外部 Client 联调。

### 2.2 可选完成

- SSE HTTP 模式。
- MCP 服务在 GUI 中一键启动/停止。
- MCP 状态显示在底部状态栏。

### 2.3 暂不完成

- 不做远程认证。
- 不做公网访问。
- 不做多租户权限控制。
- 不让 MCP 直接修改知识库内容。

---

## 3. 模块规划

```text
mcp_server/
├── __init__.py
├── server.py
└── tools.py
```

职责：

- `server.py`：启动 MCP Server，处理协议通信。
- `tools.py`：定义工具 schema，并将工具调用转发到 core 层。

---

## 4. 工具设计

### 4.1 search_knowledge_base

用途：在个人知识库中执行语义检索。

输入：

```json
{
  "query": "自然语言查询",
  "top_k": 5,
  "partition_filter": "技术笔记",
  "tag_filters": ["RAG", "Python"]
}
```

输出建议：

```json
{
  "results": [
    {
      "document_id": "doc_xxx",
      "document_name": "example.md",
      "chunk_id": "chunk_xxx",
      "chunk_index": 3,
      "score": 0.86,
      "content": "命中的文本片段..."
    }
  ]
}
```

验收标准：

- 必填参数只有 `query`。
- `top_k` 有默认值。
- 空结果时返回空数组。
- 异常时返回清晰错误，而不是输出 Python traceback。

### 4.2 list_knowledge_bases

用途：列出所有分区及文档数量。

输出建议：

```json
{
  "partitions": [
    {
      "id": "default",
      "name": "全部文档",
      "document_count": 128
    }
  ]
}
```

验收标准：

- 无参数可调用。
- 返回结果与 GUI 左侧分区树一致。

### 4.3 get_document_preview

用途：获取指定文档的预览内容和元信息。

输入：

```json
{
  "document_id": "doc_xxx"
}
```

输出建议：

```json
{
  "document": {
    "id": "doc_xxx",
    "name": "example.md",
    "file_ext": ".md",
    "chunk_count": 12,
    "preview": "文档预览文本..."
  }
}
```

验收标准：

- 支持按 document_id 查询。
- 可选支持按文件名模糊查询，但第一版不强制。
- 预览长度应有限制，避免一次返回过长内容。

---

## 5. 启动方式

### 5.1 stdio 模式

推荐第一版实现：

```bash
python -m mcp_server.server --transport stdio
```

验收标准：

- 命令可启动。
- 外部 MCP Client 能发现工具。
- 工具调用能返回 JSON 结构结果。

### 5.2 SSE 模式

可选实现：

```bash
python -m mcp_server.server --transport sse --port 8080
```

验收标准：

- 本地端口可访问。
- GUI 状态栏可显示 MCP Server 运行状态。

---

## 6. 外部 Client 配置示例

建议新增文档：

```text
docs/mcp-api.md
```

配置示例：

```json
{
  "mcpServers": {
    "knowledge-base": {
      "command": "python",
      "args": ["-m", "mcp_server.server", "--transport", "stdio"],
      "env": {
        "CHROMA_PATH": "./data/chroma_db",
        "DB_PATH": "./data/kb.sqlite"
      }
    }
  }
}
```

---

## 7. 测试计划

### 7.1 单元测试

覆盖：

- 工具参数校验。
- 空 query。
- top_k 默认值。
- 分区过滤。
- 文档不存在。

### 7.2 集成测试

覆盖：

- 启动 MCP Server。
- 调用 `list_knowledge_bases`。
- 调用 `search_knowledge_base`。
- 调用 `get_document_preview`。

### 7.3 外部联调

至少完成一个外部 Client 联调：

- Claude Desktop。
- Cursor。
- 自建 MCP Client。

---

## 8. 阶段验收清单

- [ ] MCP Server 可启动。
- [ ] MCP Client 能发现工具。
- [ ] `search_knowledge_base` 可返回检索结果。
- [ ] `list_knowledge_bases` 可返回分区。
- [ ] `get_document_preview` 可返回文档预览。
- [ ] MCP 调用结果与 GUI 检索结果基本一致。
- [ ] `docs/mcp-api.md` 包含配置和参数说明。

---

## 9. 风险与控制

| 风险 | 处理方式 |
|------|----------|
| MCP 协议版本变化 | 锁定依赖版本，并在文档中记录 |
| MCP 输出过长 | 限制 preview 和 content 长度 |
| MCP 与 GUI 同时访问数据库 | SQLite 使用短连接，写操作集中在 core 层 |
| 外部 Agent 误用工具 | 第一版 MCP 只读，不提供删除、导入、修改能力 |

---

## 10. 完成定义

当外部 Agent 可以通过 MCP 搜索知识库、列出分区、获取文档预览，并且结果与 GUI 检索保持一致时，本阶段完成。

