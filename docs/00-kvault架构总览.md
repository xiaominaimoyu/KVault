# KVault 项目架构总览

> **版本**：v1.0  
> **日期**：2026-07-13  
> **说明**：基于 `docs/` 下 6 份阶段计划书与总体开发方案汇总而成的项目整体架构。  
> 每个模块附**最小核心代码骨架**，用于快速把握结构，不代表最终实现。

---

## 一、项目定位

**KVault** 是一款**完全本地运行**的个人知识库桌面应用：

- **多格式导入**：PDF / DOCX / MD / TXT / XLSX / PPTX
- **RAG 管道**：解析 → 切分 → 向量化 → 入库
- **可视化管理**：PySide6 三栏式 GUI
- **对外接口**：MCP 协议暴露检索能力给外部 Agent（Claude Desktop / Cursor 等）

**核心原则**：本地优先 · 渐进增强 · GUI/后端/MCP 三层解耦 · 标准协议对外。

---

## 二、四层分层架构

​```text
┌───────────────────────────────────────────────────────────────────┐
│  ①  桌面应用层  (PySide6 GUI)                                       │
│   顶部工具栏 · 左侧导航栏 · 中间文档列表 · 右侧预览+检索 · 底部状态栏      │
├───────────────────────────────────────────────────────────────────┤
│  ②  后端核心层  (core/，无 GUI 依赖)                                 │
│   parser · splitter · embedding · vector_store · retriever ·      │
│   metadata_manager · config                                       │
├───────────────────────────────────────────────────────────────────┤
│  ③  存储层                                                         │
│   ChromaDB (向量) · SQLite (元数据) · data/files/ (原文件副本)        │
├───────────────────────────────────────────────────────────────────┤
│  ④  对外接口层  (mcp_server/)                                       │
│   MCP Server (JSON-RPC 2.0, stdio / SSE)                          │
│     ├─ search_knowledge_base                                       │
│     ├─ list_knowledge_bases                                        │
│     └─ get_document_preview                                        │
│                     ↓                                              │
│           外部 Agent (Claude / Cursor / 自建)                        │
└───────────────────────────────────────────────────────────────────┘
​```

---

## 三、目录结构

​```text
KVault/
├── main.py
├── requirements.txt
├── config.json.example
├── KVault.spec
│
├── gui/
│   ├── main_window.py
│   ├── toolbar.py
│   ├── nav_panel.py
│   ├── doc_list_view.py
│   ├── preview_panel.py
│   ├── settings_dialog.py
│   ├── workers/
│   │   ├── ingest_worker.py
│   │   └── search_worker.py
│   └── widgets/
│
├── core/
│   ├── config.py
│   ├── document_parser.py
│   ├── text_splitter.py
│   ├── embedding_service.py
│   ├── vector_store.py
│   ├── retriever.py
│   └── metadata_manager.py
│
├── mcp_server/
│   ├── server.py
│   └── tools.py
│
├── data/            # 运行时生成
│   ├── files/
│   ├── chroma_db/
│   ├── kb.sqlite
│   └── logs/app.log
│
├── assets/
└── docs/
​```

---

## 四、技术选型速览

| 层 | 选型 | 版本 |
|----|------|------|
| GUI | PySide6 (Qt6) | ≥ 6.4 |
| RAG 编排 | LangChain | ≥ 0.3 |
| PDF 解析 | PyMuPDF | latest |
| Office 解析 | python-docx / openpyxl / python-pptx | latest |
| Embedding | Ollama + bge-large-zh-v1.5 (1024 dim) | latest |
| 向量库 | ChromaDB | ≥ 0.4 |
| 元数据 | SQLite | 内置 |
| 对外协议 | MCP (JSON-RPC 2.0) | ≥ 1.0 |
| 打包 | PyInstaller | ≥ 6.0 |

---

## 五、核心模块与最小代码骨架

> 以下代码仅展示每个模块**最核心的接口形态**，省略异常处理、日志、边界校验等细节。

### 5.1 应用入口 `main.py`

​```python
import sys
from PySide6.QtWidgets import QApplication
from core.config import Config
from gui.main_window import MainWindow

def main():
    config = Config.load()
    app = QApplication(sys.argv)
    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
​```

---

### 5.2 配置与路径 `core/config.py`

​```python
import json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Config:
    files_dir: Path = Path("./data/files")
    chroma_dir: Path = Path("./data/chroma_db")
    sqlite_path: Path = Path("./data/kb.sqlite")
    chunk_size: int = 500
    chunk_overlap: int = 100
    embedding_model: str = "bge-large-zh-v1.5"
    ollama_base_url: str = "http://localhost:11434"
    top_k: int = 5
    similarity_threshold: float = 0.5

    @classmethod
    def load(cls, path: str = "config.json") -> "Config":
        data = json.loads(Path(path).read_text("utf-8")) if Path(path).exists() else {}
        cfg = cls(**data)
        for p in (cfg.files_dir, cfg.chroma_dir, cfg.sqlite_path.parent):
            p.mkdir(parents=True, exist_ok=True)
        return cfg
​```

---

### 5.3 文档解析 `core/document_parser.py`

​```python
from pathlib import Path
from dataclasses import dataclass

@dataclass
class ParsedDocument:
    content: str
    metadata: dict

class DocumentParser:
    def parse(self, file_path: str) -> ParsedDocument:
        ext = Path(file_path).suffix.lower()
        parser = self._dispatch(ext)
        if parser is None:
            raise ValueError(f"Unsupported format: {ext}")
        return parser(file_path)

    def _dispatch(self, ext: str):
        return {
            ".txt":  self._parse_txt,
            ".md":   self._parse_txt,
            ".pdf":  self._parse_pdf,
            ".docx": self._parse_docx,
            ".xlsx": self._parse_xlsx,
            ".pptx": self._parse_pptx,
        }.get(ext)

    def _parse_txt(self, path):
        text = Path(path).read_text("utf-8", errors="ignore")
        return ParsedDocument(text, {"source": path})

    def _parse_pdf(self, path):
        import fitz
        doc = fitz.open(path)
        text = "\n".join(page.get_text() for page in doc)
        return ParsedDocument(text, {"source": path, "pages": doc.page_count})

    # _parse_docx / _parse_xlsx / _parse_pptx 结构类似
​```

---

### 5.4 文本切分 `core/text_splitter.py`

​```python
from dataclasses import dataclass
from langchain.text_splitter import RecursiveCharacterTextSplitter

@dataclass
class Chunk:
    content: str
    metadata: dict

class KnowledgeTextSplitter:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""],
        )

    def split(self, content: str, doc_metadata: dict) -> list[Chunk]:
        pieces = self.splitter.split_text(content)
        total = len(pieces)
        return [
            Chunk(
                content=p,
                metadata={**doc_metadata, "chunk_index": i, "total_chunks": total},
            )
            for i, p in enumerate(pieces)
        ]
​```

---

### 5.5 Embedding 服务 `core/embedding_service.py`

​```python
import ollama

class EmbeddingService:
    def __init__(self, model: str = "bge-large-zh-v1.5",
                 base_url: str = "http://localhost:11434"):
        self.model = model
        self.client = ollama.Client(host=base_url)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.client.embeddings(model=self.model, prompt=t)["embedding"]
                for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self.embed_texts([query])[0]

    @property
    def dimension(self) -> int:
        return 1024
​```

---

### 5.6 向量存储 `core/vector_store.py`

​```python
import chromadb
from dataclasses import dataclass

@dataclass
class SearchResult:
    chunk_id: str
    content: str
    score: float
    metadata: dict

class VectorStore:
    def __init__(self, persist_dir: str = "./data/chroma_db"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, ids, texts, embeddings, metadatas):
        self.collection.add(ids=ids, documents=texts,
                            embeddings=embeddings, metadatas=metadatas)

    def search(self, query_embedding, top_k: int = 5, filters: dict | None = None):
        res = self.collection.query(query_embeddings=[query_embedding],
                                    n_results=top_k, where=filters)
        return [
            SearchResult(chunk_id=cid, content=doc, score=1 - dist, metadata=meta)
            for cid, doc, dist, meta in zip(
                res["ids"][0], res["documents"][0],
                res["distances"][0], res["metadatas"][0],
            )
        ]

    def delete_by_document(self, document_id: str):
        self.collection.delete(where={"document_id": document_id})
​```

---

### 5.7 元数据管理 `core/metadata_manager.py`

​```python
import sqlite3, uuid, time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    file_name TEXT, stored_path TEXT, file_ext TEXT, file_size INTEGER,
    partition_id TEXT, status TEXT,        -- pending/indexing/indexed/failed
    chunk_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at REAL, updated_at REAL
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY, document_id TEXT,
    chunk_index INTEGER, content_preview TEXT, chroma_id TEXT
);
CREATE TABLE IF NOT EXISTS partitions (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS tags (id TEXT PRIMARY KEY, name TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS document_tags (document_id TEXT, tag_id TEXT);
"""

class MetadataManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def create_document(self, file_name, stored_path, file_ext, file_size,
                        partition_id="default") -> str:
        doc_id = uuid.uuid4().hex
        now = time.time()
        with self._conn() as c:
            c.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?,?,0,NULL,?,?)",
                (doc_id, file_name, stored_path, file_ext, file_size,
                 partition_id, "pending", now, now),
            )
        return doc_id

    def update_status(self, doc_id, status, error=None, chunk_count=None):
        with self._conn() as c:
            c.execute(
                "UPDATE documents SET status=?, error_message=?, "
                "chunk_count=COALESCE(?,chunk_count), updated_at=? WHERE id=?",
                (status, error, chunk_count, time.time(), doc_id),
            )

    def list_documents(self, partition_id=None):
        sql, args = "SELECT * FROM documents", ()
        if partition_id:
            sql += " WHERE partition_id=?"
            args = (partition_id,)
        with self._conn() as c:
            return c.execute(sql + " ORDER BY created_at DESC", args).fetchall()

    def delete_document(self, doc_id):
        with self._conn() as c:
            c.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
            c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
​```

---

### 5.8 检索服务 `core/retriever.py`

​```python
from dataclasses import dataclass

@dataclass
class SearchHit:
    document_id: str
    document_name: str
    chunk_index: int
    content: str
    score: float

class Retriever:
    def __init__(self, embedding_service, vector_store, metadata_manager,
                 similarity_threshold: float = 0.5):
        self.emb = embedding_service
        self.vs = vector_store
        self.mm = metadata_manager
        self.threshold = similarity_threshold

    def search(self, query: str, top_k: int = 5,
               filters: dict | None = None) -> list[SearchHit]:
        if not query.strip():
            return []
        qv = self.emb.embed_query(query)
        raw = self.vs.search(qv, top_k=top_k, filters=filters)
        return [
            SearchHit(
                document_id=r.metadata.get("document_id", ""),
                document_name=r.metadata.get("file_name", ""),
                chunk_index=r.metadata.get("chunk_index", 0),
                content=r.content,
                score=r.score,
            )
            for r in raw if r.score >= self.threshold
        ]
​```

---

### 5.9 导入编排 `core/ingest.py`

​```python
import shutil
from pathlib import Path

def ingest_document(file_path, cfg, parser, splitter,
                    embedder, vector_store, metadata) -> str:
    src = Path(file_path)
    stored = cfg.files_dir / src.name

    doc_id = metadata.create_document(
        file_name=src.name, stored_path=str(stored),
        file_ext=src.suffix.lower(), file_size=src.stat().st_size,
    )
    try:
        shutil.copy2(src, stored)
        metadata.update_status(doc_id, "indexing")

        parsed = parser.parse(str(stored))
        chunks = splitter.split(parsed.content, {"document_id": doc_id,
                                                 "file_name": src.name})
        embeddings = embedder.embed_texts([c.content for c in chunks])

        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        vector_store.add_chunks(
            ids=ids,
            texts=[c.content for c in chunks],
            embeddings=embeddings,
            metadatas=[c.metadata for c in chunks],
        )
        metadata.update_status(doc_id, "indexed", chunk_count=len(chunks))
        return doc_id
    except Exception as e:
        metadata.update_status(doc_id, "failed", error=str(e))
        raise
​```

---

### 5.10 GUI 主窗口 `gui/main_window.py`

​```python
from PySide6.QtWidgets import QMainWindow, QSplitter, QWidget, QHBoxLayout
from PySide6.QtCore import Qt
from gui.toolbar import TopToolBar
from gui.nav_panel import NavPanel
from gui.doc_list_view import DocListView
from gui.preview_panel import PreviewPanel

class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.setWindowTitle("KVault · 个人知识库")
        self.resize(1280, 800)
        self.config = config

        self.addToolBar(TopToolBar(self))

        splitter = QSplitter(Qt.Horizontal)
        self.nav = NavPanel()
        self.doc_list = DocListView()
        self.preview = PreviewPanel()
        splitter.addWidget(self.nav)
        splitter.addWidget(self.doc_list)
        splitter.addWidget(self.preview)
        splitter.setSizes([180, 460, 640])

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

        self.statusBar().showMessage("本地运行 · 就绪")

        self.nav.partition_selected.connect(self.doc_list.filter_by_partition)
        self.doc_list.document_selected.connect(self.preview.load_document)
​```

---

### 5.11 后台导入线程 `gui/workers/ingest_worker.py`

​```python
from PySide6.QtCore import QThread, Signal
import os

class IngestWorker(QThread):
    progress = Signal(int, str)          # (percent, file_name)
    file_done = Signal(str, bool)        # (path, success)
    finished_all = Signal(int, int)      # (success, fail)

    def __init__(self, file_paths, ingest_fn):
        super().__init__()
        self.file_paths = file_paths
        self.ingest_fn = ingest_fn

    def run(self):
        total, ok, fail = len(self.file_paths), 0, 0
        for i, path in enumerate(self.file_paths, 1):
            self.progress.emit(int(i / total * 100), os.path.basename(path))
            try:
                self.ingest_fn(path)
                self.file_done.emit(path, True); ok += 1
            except Exception:
                self.file_done.emit(path, False); fail += 1
        self.finished_all.emit(ok, fail)
​```

---

### 5.12 MCP 工具定义 `mcp_server/tools.py`

​```python
TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": "在个人知识库中进行语义检索",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "default": 5},
                "partition_filter": {"type": "string"},
                "tag_filters": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_knowledge_bases",
        "description": "列出所有分区及文档数量",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_document_preview",
        "description": "获取指定文档的预览内容和元信息",
        "inputSchema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
        },
    },
]
​```

---

### 5.13 MCP Server `mcp_server/server.py`

​```python
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from core.config import Config
from core.embedding_service import EmbeddingService
from core.vector_store import VectorStore
from core.metadata_manager import MetadataManager
from core.retriever import Retriever
from mcp_server.tools import TOOLS

cfg = Config.load()
retriever = Retriever(
    EmbeddingService(cfg.embedding_model, cfg.ollama_base_url),
    VectorStore(str(cfg.chroma_dir)),
    MetadataManager(str(cfg.sqlite_path)),
)
mm = retriever.mm
app = Server("kvault")

@app.list_tools()
async def list_tools():
    return TOOLS

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "search_knowledge_base":
        hits = retriever.search(
            query=arguments["query"],
            top_k=arguments.get("top_k", 5),
            filters=_build_filters(arguments),
        )
        return {"results": [h.__dict__ for h in hits]}
    if name == "list_knowledge_bases":
        return {"partitions": mm.list_partitions_with_counts()}
    if name == "get_document_preview":
        return {"document": mm.get_document_preview(arguments["document_id"])}
    raise ValueError(f"Unknown tool: {name}")

def _build_filters(args):
    f = {}
    if args.get("partition_filter"): f["partition"] = args["partition_filter"]
    if args.get("tag_filters"):      f["tags"] = {"$in": args["tag_filters"]}
    return f or None

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
​```

---

## 六、关键数据流

### 6.1 写入流（文档导入）

​```text
用户拖拽/选择文件
  → IngestWorker (QThread)
      ① MetadataManager.create_document(pending)
      ② 复制到 data/files/  → status = indexing
      ③ DocumentParser.parse()          → 纯文本
      ④ KnowledgeTextSplitter.split()   → chunks
      ⑤ EmbeddingService.embed_texts()  → vectors
      ⑥ VectorStore.add_chunks()        → Chroma
      ⑦ MetadataManager.update_status(indexed, chunk_count)
      异常 → update_status(failed, error)
  → Signal 回主线程刷新列表与状态栏
​```

### 6.2 读取流（语义检索）

​```text
GUI 输入 / MCP 请求
  → Retriever.search(query, top_k, filters)
      ① EmbeddingService.embed_query()
      ② VectorStore.search()   (cosine, top_k)
      ③ 合并 SQLite 元数据（文档名/分区/标签）
      ④ 按 similarity_threshold 过滤
  → SearchHit[]
  → GUI 相似度着色 (≥0.8 绿 / ≥0.5 黄 / <0.5 红) / MCP JSON 返回
  → 点击结果 → 预览面板定位对应 chunk
​```

---

## 七、核心数据模型（SQLite）

| 表 | 关键字段 | 作用 |
|----|----------|------|
| `documents` | id, file_name, stored_path, file_ext, file_size, partition_id, **status** (pending/indexing/indexed/failed), chunk_count, error_message, created_at | 文档主表，重启可恢复 |
| `chunks` | id, document_id, chunk_index, content_preview, **chroma_id** | 桥接 SQLite 与 ChromaDB |
| `partitions` | id, name | 默认：全部/技术笔记/项目资料/阅读笔记/灵感收藏 |
| `tags` / `document_tags` | — | 多对多标签关系 |

---

## 八、开发路线（六阶段）

| 阶段 | 周期 | 里程碑 | 完成定义 |
|------|------|--------|----------|
| **1. 最小闭环** | 第 1 周 | 项目骨架 + 三栏窗口 + TXT/MD/PDF 解析 + 切分 + 写 Chroma | 能选文件走通整条管道 |
| **2. 真实索引与元数据** | 第 2 周 | Ollama Embedding + SQLite 元数据 + 后台线程 | 重启能恢复文档列表与状态 |
| **3. 检索与格式扩展** | 第 3 周 | Retriever + 检索面板 + DOCX/XLSX/PPTX + 全局过滤 | 自然语言检索并追溯来源 |
| **4. GUI 管理完善** | 第 4 周上 | 分区/标签 CRUD + 右键菜单 + 删除/重索引 + 设置 + 日志 | 全 GUI 完成管理动作 |
| **5. MCP 对外接口** | 第 4 周下 | mcp_server + 3 个工具 + stdio (SSE 可选) | Claude/Cursor 联调通过 |
| **6. 打包与首启引导** | 第 5 周 | PyInstaller + 首启检查 + README/MCP API 文档 | 新环境按文档跑通打包版 |

---

## 九、关键设计决策

1. **GUI 与 core 完全解耦** — core 不引入 Qt 依赖，可被 GUI 与 MCP Server 共享。
2. **所有耗时操作走 QThread** — 通过 Signal 回主线程，UI 永不假死。
3. **文档状态机** — `pending → indexing → indexed | failed`，任何环节失败可恢复。
4. **Chroma 与 SQLite 双写一致性** — chunks 保存 `chroma_id`，删除/重索引按 `document_id` 统一操作。
5. **MCP 第一版只读** — 只暴露 search/list/preview，禁止外部 Agent 修改数据。
6. **配置变更语义清晰** — Embedding 与切分参数变更仅影响新导入；旧数据需手动"重新索引"。
7. **路径策略分离** — 打包环境不写只读程序目录，用户数据可配置目录。

---

*本文档随项目进展持续更新，是 `docs/` 目录下 6 份阶段计划书的架构级汇总。*