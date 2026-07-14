# KVault

KVault 是一款面向个人的本地化知识库桌面应用，基于 **PySide6** 构建 GUI，通过 **RAG（检索增强生成）流水线** 实现文档管理与语义检索。所有数据（文件、向量索引、元数据）均保存在本地，无需联网即可使用（嵌入模型需本地 Ollama 服务）。

---

## 功能特性

- **多格式文档导入**：支持 TXT、Markdown、PDF、DOCX、XLSX、PPTX。
- **自动解析与切分**：提取文本内容并按配置切分为语义块。
- **本地向量索引**：使用 ChromaDB 持久化存储文本嵌入向量。
- **语义检索**：输入自然语言即可查找相关文档片段，并按相似度排序。
- **全局文档过滤**：按文件名、扩展名、分区快速筛选已导入文档。
- **元数据管理**：SQLite 记录文档状态、分区、标签、切分块信息。
- **异步处理**：导入与检索均在后台线程运行，避免界面卡顿。
- **分区管理**：创建、重命名、删除分区，支持文档移动。
- **标签管理**：为文档添加自定义标签，支持标签过滤检索。
- **文档操作**：删除、移动、重新索引已导入的文档。
- **设置管理**：调整嵌入模型、检索参数、主题设置。
- **状态监控**：实时显示导入进度、文档统计、系统状态。
- **MCP 外部接口**：提供标准化外部接口，便于其他工具调用。
- **首次启动检查**：自动检测 Ollama 服务、模型可用性、数据目录。

---

## 架构设计

KVault 采用四层架构：

```
┌─────────────────────────────────────┐
│  Desktop Application Layer (PySide6)│  ← GUI 主窗口、后台 Worker、启动检查
├─────────────────────────────────────┤
│      Backend Core Layer (core/)     │  ← 解析、切分、嵌入、检索、元数据
├─────────────────────────────────────┤
│      Storage Layer                  │  ← ChromaDB + SQLite + 本地文件
├─────────────────────────────────────┤
│      External Interface Layer (MCP) │  ← 外部调用接口
└─────────────────────────────────────┘
```

### RAG 流水线

```
文档导入 → 解析文本 → 切分块 → Embedding (Ollama) → ChromaDB 存储 → 语义检索
```

---

## 安装步骤

1. 克隆项目到本地。

2. 创建并激活虚拟环境（项目使用 `.env` 目录）：

   ```powershell
   python -m venv .env
   .\.env\Scripts\Activate.ps1
   ```

3. 安装依赖：

   ```powershell
   pip install -r requirements.txt
   ```

4. 确保已安装并启动 [Ollama](https://ollama.com)，且本地已拉取嵌入模型：

   ```bash
   ollama pull modelscope.cn/Embedding-GGUF/bge-large-zh-v1.5:latest
   ```

---

## 使用指南

1. 启动应用：

   ```powershell
   .\.env\Scripts\Activate.ps1
   python main.py
   ```

2. **首次启动**：应用会自动检查环境，包括 Ollama 服务状态、模型可用性、数据目录权限。

3. **导入文档**：点击 **「导入文档」**，选择本地文件导入。支持批量导入。

4. **管理分区**：在左侧面板创建、重命名分区，将文档移动到不同分区。

5. **标签管理**：右键文档选择 **「编辑标签」**，为文档添加自定义标签。

6. **语义检索**：在右侧面板输入自然语言查询，点击 **「检索」**。检索结果按相似度排序（绿色 ≥0.8、黄色 ≥0.5、红色 <0.5）。

7. **文档预览**：点击检索结果可定位源文档并高亮对应文本块。

### 直接运行打包版

如果已经通过 PyInstaller 打包生成 `dist/KVault/KVault.exe`，可以直接双击运行，无需再激活虚拟环境：

```powershell
dist\KVault\KVault.exe
```

打包版的数据目录固定为 `%APPDATA%\KVault`，与源码模式的 `data/` 相互独立。

---

## MCP 外部接口使用

KVault 通过 **Model Context Protocol（MCP）** 向外部 AI 代理暴露本地知识库检索能力。MCP 服务以只读方式运行，不提供导入、删除或修改知识库的能力。

### 启动 MCP 服务

MCP 服务需要在 Python 环境中运行。激活虚拟环境后执行：

```powershell
.\.env\Scripts\Activate.ps1
python -m mcp_server
```

默认使用 `stdio` 传输；如需使用 `sse`：

```powershell
python -m mcp_server --transport sse --port 8080
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `CHROMA_PATH` | 覆盖 ChromaDB 数据目录 |
| `DB_PATH` | 覆盖 SQLite 数据库路径 |

### 可用工具

- `search_knowledge_base_tool`：语义检索知识库片段。
- `list_knowledge_bases_tool`：列出所有分区及文档数量。
- `get_document_preview_tool`：获取指定文档的预览与元信息。

### 在 Claude Desktop 中配置

在 `%APPDATA%\Claude\settings.json` 中添加：

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

> 请根据实际安装路径调整 `cwd`、`CHROMA_PATH` 和 `DB_PATH`。

### Python 客户端示例

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

更多参数和返回格式详见 [`docs/mcp-api.md`](docs/mcp-api.md)。

---

## 开发计划

| 阶段 | 主题 | 状态 |
|------|------|------|
| Phase 1 | 基础 GUI 与原型验证 | 已完成 |
| Phase 2 | 真实索引与元数据管理 | 已完成 |
| Phase 3 | 检索体验与格式扩展 | 已完成 |
| Phase 4 | GUI 管理功能扩展 | 已完成 |
| Phase 5 | MCP 协议与外部接口 | 已完成 |
| Phase 6 | 打包、首启引导与文档 | 已完成 |

---

## 技术栈

- Python 3.11+
- PySide6
- LangChain / langchain-text-splitters
- ChromaDB
- Ollama
- python-docx / PyPDF2 / openpyxl / python-pptx
- SQLite
- python-multipart (MCP)

---

## 目录说明

```
KVault/
├── core/                # 核心后端逻辑
│   ├── config.py        # 配置管理
│   ├── document_parser.py   # 文档解析器
│   ├── text_splitter.py     # 文本切分
│   ├── embedding_service.py  # 嵌入服务
│   ├── vector_store.py      # 向量数据库
│   ├── metadata_manager.py  # 元数据管理
│   ├── ingest.py            # 导入流水线
│   ├── retriever.py         # 检索服务
│   └── startup_check.py     # 启动检查
├── gui/                 # 桌面界面
│   ├── main_window.py   # 主窗口
│   ├── startup_dialog.py   # 启动检查对话框
│   └── workers/         # 后台线程
├── mcp_server/          # MCP 服务器模块
│   ├── __init__.py
│   ├── server.py        # MCP 服务实现
│   └── tools.py         # 工具定义
├── docs/                # 开发计划与文档
│   ├── mcp-api.md       # MCP API 文档
│   └── backup-and-migration.md  # 备份迁移指南
├── data/                # 运行时数据（自动生成）
├── main.py              # 入口文件
├── KVault.spec          # PyInstaller 打包配置
├── requirements.txt     # 依赖列表
└── README.md            # 本文件
```

---

## 打包部署

使用 PyInstaller 打包为 Windows 可执行文件：

```powershell
.\.env\Scripts\Activate.ps1
pyinstaller KVault.spec
```

打包后的可执行文件位于 `dist/KVault/KVault.exe`。

---

## 注意事项

- 首次导入文档时会根据文件大小生成嵌入，可能需要一定时间。
- 嵌入服务依赖本地 Ollama，请确保 Ollama 服务已启动且模型已下载。
- `data/` 目录为运行时数据目录，建议定期备份。
- 在打包环境中，用户数据存储在 `%APPDATA%\KVault` 目录。
- 关闭窗口时会自动终止所有后台工作线程，确保数据安全。
- 更换 Embedding 模型前，请先阅读 `docs/backup-and-migration.md` 中的「模型变更处理」章节，避免向量不兼容导致检索异常。

---

## 更新日志

### 修复内容

1. **文档不清理向量**：删除文档时同步清理 ChromaDB 中的向量数据。
2. **HTML 注入漏洞**：所有用户输入内容在渲染前经过 `html.escape()` 处理。
3. **SQLite 线程安全**：数据库连接添加 `check_same_thread=False`。
4. **窗口关闭线程泄漏**：添加 `closeEvent` 处理，确保工作线程正确终止。
5. **模型名称解析**：自动匹配短名称与完整模型路径，增强兼容性。
6. **文档同步**：补充 `docs/backup-and-migration.md`「模型变更处理」章节，README 同步添加相关指引。
7. **配置文件路径固定**：`config.json` 的加载与保存均解析为应用根目录的绝对路径，避免从不同目录启动时数据目录漂移导致的数据丢失。
8. **MCP 服务启动修复**：修复 `FastMCP.run()` 不支持 `port` 参数导致的 `TypeError`，SSE 模式通过 `mcp.settings.port` 设置端口。