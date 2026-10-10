# KVault

KVault 是一款面向个人的本地化知识库桌面应用，基于 **PySide6** 构建 GUI。它把两件原本分开的事情合到了一起：

- **Obsidian 式笔记库** —— 知识库就是你自己的一个 Markdown 文件夹，可编辑、可链接、有图谱
- **RAG 语义检索** —— 向量 + BM25 混合检索，这是 Obsidian 本身不具备的能力

所有数据（笔记文件、向量索引、元数据）均保存在本地，无需联网即可使用（嵌入模型需本地 Ollama 服务）。

---

## 功能特性

### 笔记库

- **Markdown 编辑器**：语法高亮、行号、自动保存、`Ctrl+S` 保存
- **Wiki 链接**：输入 `[[` 即弹出候选补全，`Ctrl+点击` 直接跳转
- **双向链接**：反链面板列出「谁引用了我」，出链面板列出「我引用了谁」，断链单独标色并可一键创建
- **属性（frontmatter）**：标题、别名、标签等以 YAML 写入文件头，与 Obsidian 兼容
- **层级标签**：支持 `#项目/子项`，父标签自动聚合计数
- **知识图谱**：力导向布局的链接网络，节点大小反映链接度，孤儿笔记一目了然
- **快速切换 / 命令面板**：`Ctrl+O` 按名称跳转，`Ctrl+P` 执行命令
- **文件归你所有**：笔记就是磁盘上的 `.md` 文件，可被任意编辑器、Git、同步盘处理

### 文档检索

- **多格式导入**：TXT、Markdown、PDF、DOCX、XLSX、PPTX、PNG/JPG/JPEG（图片需可选依赖 RapidOCR）
- **本地向量索引**：ChromaDB 持久化存储文本嵌入向量
- **混合检索**：向量语义召回 + BM25 关键词召回，RRF / 加权归一化两种融合策略
- **增量更新**：基于内容哈希 + mtime 的差异扫描，只重建变更文档
- **MCP 外部接口**：向 AI 代理暴露知识库读写能力

### 通用

- **多知识库工作区**：创建、切换、归档、恢复，数据完全隔离
- **插件化 Connector**：本地目录、GitHub 仓库等外部数据源
- **深色 / 浅色主题**：全量令牌化 QSS，跟随系统

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

### 两种视图

KVault 的主界面有两个并列的视图，分工明确：

| 视图 | 面向 | 数据来源 |
|------|------|---------|
| **文档** | 导入的外部资料（PDF、网页存档、Office 文件） | `data/…/files/` + ChromaDB 向量索引 |
| **笔记** | 你自己写的知识沉淀 | `data/…/vault/` 下的 Markdown 文件 |

两者共用同一套检索与索引基础设施——**笔记也能被语义检索到**，因为每篇笔记在
`documents` 表中都有对应记录，自动接入既有的向量 / BM25 管道。

### 笔记库架构

```
        磁盘上的 .md 文件（真相）          SQLite 索引（可随时重建）
        ┌──────────────────────┐        ┌──────────────────────┐
        │  项目/方案.md         │◀──────▶│  notes              │
        │  想法/随手记.md       │        │  note_links（链接边）│
        └──────────┬───────────┘        │  note_tags （标签）  │
                   │                    └──────────┬───────────┘
        ┌──────────▼───────────┐                   │
        │  core/vault.py        │  文件读写          │  索引读写
        │  core/frontmatter.py  │  属性解析          │
        │  core/links.py        │  链接与标签抽取      │
        │  core/markdown.py     │  渲染与转义         │
        └──────────┬───────────┘                   │
                   │                               │
        ┌──────────▼───────────────────────────────▼──┐
        │  core/note_store.py —— 桥接层               │
        │  笔记 ⇄ documents ⇄ 向量索引                │
        └─────────────────────────────────────────────┘
```

关键设计：**Markdown 文件是唯一真相**，SQLite 只是可重建的索引。
删掉 `kb.sqlite` 后执行一次全量同步（`Ctrl+R`），笔记库会完整恢复。

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

### 可选依赖

以下依赖不在 `requirements.txt` 的强制项中，按需安装以启用增强能力。未安装时应用正常运行，仅对应能力降级。

| 依赖 | 安装命令 | 启用能力 | 缺失时降级行为 |
|------|---------|---------|---------------|
| `pdfplumber` | `pip install pdfplumber` | PDF 表格结构化提取（保留表格行列结构） | 降级为 PyMuPDF 纯文本提取，表格以普通文本呈现 |
| `rapidocr-onnxruntime` | `pip install rapidocr-onnxruntime` | PNG/JPG/JPEG 图片 OCR 文字识别 | 跳过图片文字识别，图片内容为空并记录 `ocr: skipped` |
| `jieba` | `pip install jieba` | 中文分词，驱动 BM25 混合检索 | 混合检索降级为纯字串匹配，中文关键词召回显著下降 |

> **建议安装 jieba**：没有中文分词时，BM25 臂退化为按空格切分，
> 中文查询几乎无法召回关键词命中的结果。

---

## 使用指南

### 启动应用

```powershell
.\.env\Scripts\Activate.ps1
python main.py
```

### 笔记库

1. 启动后点击顶部 **「笔记」** 切换到笔记视图。

2. **新建笔记**：点击左侧「新建」，或直接输入 `[[` 链接到还不存在的笔记——
   KVault 会提示并帮你创建它。这是构建知识网络最快的方式。

3. **写笔记**：中间区域就是编辑器，自动保存（2 秒），`Ctrl+S` 立即保存。
   顶部可切换 **编辑 / 阅读 / 分栏** 三种模式。

4. **建立链接**：输入 `[[` 触发候选补全，输入 `#标签` 打标签。
   重命名笔记时，指向它的入链会被自动改写，不会产生断链。

5. **查看关系**：右侧「反链 / 出链」面板展示链接关系，
   断链会以警示色标出，双击即可创建缺失的笔记。

6. **查看全局结构**：点击顶部 **「图谱」**，用节点和连线看清知识网络的疏密。

7. **快速跳转**：`Ctrl+O` 按名称打开任意笔记，`Ctrl+P` 打开命令面板。

### 文档检索

1. **首次启动**：应用会自动检查环境，包括 Ollama 服务状态、模型可用性、数据目录权限。

2. **导入文档**：点击 **「导入文档」**，选择本地文件导入。支持批量导入。

3. **管理分区**：在左侧面板创建、重命名分区，将文档移动到不同分区。

4. **标签管理**：右键文档选择 **「编辑标签」**，为文档添加自定义标签。

5. **语义检索**：在右侧面板输入自然语言查询，点击 **「检索」**。检索结果按相似度排序（绿色 ≥0.8、黄色 ≥0.5、红色 <0.5）。

6. **文档预览**：点击检索结果可定位源文档并高亮对应文本块。

> **笔记同样能被语义检索**：切回「文档」视图检索时，笔记内容也会参与召回。

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Shift+N` | 切换到笔记视图 |
| `Ctrl+G` | 切换到图谱视图 |
| `Ctrl+O` | 快速打开笔记 |
| `Ctrl+P` | 命令面板 |
| `Ctrl+S` | 焦点在笔记编辑器内时保存笔记；否则打开设置 |
| `Ctrl+I` | 导入文档 |
| `Ctrl+K` | 语义检索 |
| `Ctrl+R` | 刷新 / 同步笔记索引 |
| `Ctrl+1/2/3` | 切换详情标签页 |

### 直接运行打包版

如果已经通过 PyInstaller 打包生成 `dist/KVault/KVault.exe`，可以直接双击运行，无需再激活虚拟环境：

```powershell
dist\KVault\KVault.exe
```

打包版的数据目录固定为 `%APPDATA%\KVault`，与源码模式的 `data/` 相互独立。

---

## MCP 外部接口使用

KVault 通过 **Model Context Protocol（MCP）** 向外部 AI 代理暴露知识库能力。

工具分两类：

- **只读**（默认可用）：语义检索、笔记列表、读取笔记、关键词检索、反链查询、标签列表
- **写入**（需显式开启）：新建笔记、追加内容、增删链接

> 写入能力**默认关闭**，必须设置环境变量 `KVAULT_ALLOW_WRITE=1` 后重启 MCP 服务。
> 这是刻意的安全设计——避免 AI 代理在未授权的情况下改动你的知识库。
> 笔记中的所有路径访问都经过 `core/vault` 的越界校验，无法写到 vault 之外。

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
| `KVAULT_ALLOW_WRITE` | 设为 `1` 开启笔记写入工具（默认关闭） |

### 可用工具

**文档检索（只读）**

| 工具 | 说明 |
|------|------|
| `search_knowledge_base_tool` | 语义检索知识库片段 |
| `list_knowledge_bases_tool` | 列出所有分区及文档数量 |
| `get_document_preview_tool` | 获取指定文档的预览与元信息 |

**笔记库（只读）**

| 工具 | 说明 |
|------|------|
| `list_notes_tool` | 列出笔记，可按目录 / 标签过滤 |
| `get_note_tool` | 读取笔记全文及其链接关系 |
| `search_notes_tool` | 笔记正文关键词检索（与语义检索互补） |
| `get_backlinks_tool` | 查询反向链接、出链与断链 |
| `list_tags_tool` | 列出全部标签及笔记数 |

**笔记库（写入，需 `KVAULT_ALLOW_WRITE=1`）**

| 工具 | 说明 |
|------|------|
| `create_note_tool` | 新建笔记 |
| `append_to_note_tool` | 向笔记追加内容 |
| `update_note_links_tool` | 增删 wiki 链接（接入知识网络） |

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

## 插件化 Connector

KVault 支持通过 connector 从外部数据源同步文档到知识库。connector 遵循 `list → fetch → parse` 三步契约。

### 内置 Connector

| 类型 | 说明 | 联网 | 依赖 |
|------|------|------|------|
| `local_dir` | 本地目录扫描 | 否 | 无 |
| `github` | GitHub 仓库拉取 | 是 | `requests`（可选） |
| `notion` | Notion 数据库 | — | 未实现（接口占位） |
| `feishu` | 飞书文档 | — | 未实现（接口占位） |

### 配置方式

在 `config.json` 的 `connectors` 段添加 connector 配置：

```json
{
  "connectors": [
    {
      "type": "local_dir",
      "name": "本地文档",
      "dir_path": "/path/to/docs",
      "extensions": [".txt", ".md"]
    },
    {
      "type": "github",
      "name": "项目文档",
      "repo": "owner/repo",
      "branch": "main",
      "path_filter": "docs/"
    }
  ]
}
```

### 使用示例

```python
from core.connectors import ConnectorRegistry, ConnectorSync

connector = ConnectorRegistry.create("local_dir", dir_path="/path/to/docs")
sync = ConnectorSync(connector, "local_dir")
report = sync.sync()
print(f"同步: {report.synced} 新增, {report.skipped} 跳过, {report.failed} 失败")
```

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
| Phase 7 | 笔记库：vault 模型、双链、图谱、快速切换 | 已完成 |
| Phase 8 | 笔记 MCP 工具、核心缺陷修复、主题补齐 | 已完成 |

### 尚未覆盖的 Obsidian 能力

诚实列出来，便于评估后续方向：

- 富文本实时渲染（当前为「源码模式编辑 + 独立阅读视图」，不是所见即所得）
- Canvas 白板、Properties 表格编辑器
- 每日笔记 / 模板系统
- 插件生态
- 全文检索（当前只有关键词子串匹配与向量检索，没有专门的倒排索引引擎）

---

## 技术栈

- Python 3.11+
- PySide6
- LangChain / langchain-text-splitters
- ChromaDB
- Ollama
- python-docx / PyMuPDF / openpyxl / python-pptx
- pdfplumber / rapidocr-onnxruntime / jieba（可选，见「可选依赖」）
- SQLite
- python-multipart (MCP)

---

## 目录说明

```
KVault/
├── core/                     # 核心后端逻辑
│   ├── vault.py              # 笔记库文件模型（路径安全 + CRUD）
│   ├── frontmatter.py        # YAML 属性解析与序列化
│   ├── links.py              # wiki 链接与行内标签抽取
│   ├── title.py              # 标题推导 / 字数统计 / 大纲
│   ├── markdown.py           # Markdown → HTML 渲染（内建 XSS 防护）
│   ├── note_store.py         # 笔记 ⇄ 文档 ⇄ 向量索引 的桥接层
│   ├── config.py             # 配置管理
│   ├── document_parser.py    # 文档解析器
│   ├── text_splitter.py      # 文本切分
│   ├── embedding_service.py  # 嵌入服务
│   ├── vector_store.py       # 向量数据库
│   ├── metadata_manager.py   # 元数据管理
│   ├── ingest.py             # 导入流水线
│   ├── retriever.py          # 检索服务
│   └── startup_check.py      # 启动检查
├── gui/
│   ├── main_window.py        # 主窗口（文档 / 笔记 / 图谱三视图）
│   ├── editor/               # 笔记编辑组件
│   │   ├── markdown_editor.py     # 编辑器（行号、自动保存、快捷键）
│   │   ├── markdown_highlighter.py# 语法高亮
│   │   ├── wiki_completer.py      # [[ 链接补全
│   │   ├── note_viewer.py         # 阅读视图
│   │   ├── link_panels.py         # 反链 / 出链面板
│   │   ├── graph_view.py          # 知识图谱（力导向布局）
│   │   └── quick_switcher.py      # 快速切换 / 命令面板
│   ├── panels/               # 主界面面板
│   │   └── note_workspace.py # 笔记工作台
│   ├── styles/               # 主题令牌与 QSS
│   └── workers/              # 后台线程
├── mcp_server/
│   ├── server.py             # MCP 服务（兼容 SDK 1.x / 2.x）
│   ├── tools.py              # 文档检索工具（只读）
│   └── note_tools.py         # 笔记工具（只读 + 受控写入）
├── tests/                    # 测试
├── docs/                     # 开发计划与文档
├── data/                     # 运行时数据（自动生成）
│   └── workspaces/<id>/
│       ├── files/            # 导入的文档（保留来源目录层级）
│       ├── vault/            # 笔记库——你的 Markdown 文件
│       ├── chroma_db/        # 向量索引
│       └── kb.sqlite         # 元数据索引
├── main.py                   # 入口文件
├── KVault.spec               # PyInstaller 打包配置
├── requirements.txt          # 依赖列表
└── README.md                 # 本文件
```

> **数据目录里的 `vault/` 就是你的知识库**，可以直接用 Obsidian、VS Code
> 或任何编辑器打开，也可以整个目录交给 Git 管理。

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

### 笔记库（Phase 7–8）

9. **笔记库地基**：新增 `core/vault.py`（文件模型 + 路径越界防护）、
   `frontmatter.py`、`links.py`、`title.py`、`markdown.py`，
   SQLite schema 升级至 v4（`notes` / `note_links` / `note_tags`）。

10. **编辑器与阅读**：Markdown 编辑器（语法高亮、行号、自动保存）、
    `[[` 链接补全、阅读视图、反链 / 出链面板。

11. **知识图谱**：自实现力导向布局，不依赖 networkx；节点数超限时自动降采样。

12. **快速切换与命令面板**：模糊匹配打分，子序列匹配 + 连续命中加成。

13. **MCP 笔记工具**：新增 8 个笔记工具；写入能力由 `KVAULT_ALLOW_WRITE`
    显式开启，默认只读。

### 缺陷修复

14. **同名文件静默覆盖**：`ingest.py` 曾把文件平铺存入 `files_dir`，
    不同目录的同名文件会互相覆盖并删除对方的向量。改为保留来源目录层级，
    残余冲突追加数字后缀。

15. **BM25 只能命中块首 200 字**：入库的 `content_preview` 被截断到 200 字，
    而 BM25 正是基于它建索引，长块后半部分永远无法被关键词命中。
    放宽至 4000 字（仍设上限控制体积）。

16. **混合检索阈值量纲错配**：`similarity_threshold` 衡量的是余弦相似度，
    却被套用到 BM25 分数与 RRF 融合分上。改为仅对向量臂结果生效。

17. **增量更新漏扫子目录**：存储路径引入层级后，`scan_diffs` 的非递归
    `iterdir()` 会把已有文档误判为「已删除 + 新增」。改为递归遍历。

18. **MCP SDK 2.x 崩溃**：`FastMCP` 在 2.x 中更名为 `MCPServer`，
    `requirements.txt` 的 `mcp>=1.0.0` 会装到 2.x 并导致服务无法启动。
    增加兼容导入层，并适配端口参数差异。

19. **渲染器 XSS 防护**：Markdown 渲染器禁止透传原始 HTML，
    并拦截 `javascript:` / `data:` 等危险协议的链接。