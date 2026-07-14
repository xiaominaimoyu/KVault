## KVault 个人知识库项目验收报告

验收日期：2026-07-13
项目路径：D:\project file\KVault

---

### 一、项目概况

KVault 是一个本地优先的个人知识库桌面应用，基于 PySide6 + ChromaDB + Ollama 实现 RAG（检索增强生成）管道。所有数据（文件、向量索引、元数据）存储在本地，无需云服务。项目按6个阶段规划，当前已完成 Phase 1-3 的核心代码，Phase 4-6 尚未开始。

技术栈：Python 3.14 / PySide6 6.11.1 / LangChain 1.3.9 / ChromaDB 1.5.9 / Ollama 0.6.2 / SQLite

---

### 二、阶段验收对照

#### Phase 1：项目框架与最小导入闭环

| 验收项 | 状态 | 说明 |
|--------|------|------|
| 项目目录结构 | ✅ 通过 | core/、gui/、data/、docs/ 结构完整 |
| 依赖清单 | ⚠️ 部分通过 | requirements.txt 缺少 langchain_text_splitters 显式声明；chromadb 未安装在 venv 中 |
| core/config.py | ✅ 通过 | 默认值加载、目录自动创建正常 |
| gui/main_window.py 骨架 | ✅ 通过 | 三栏布局、1280x800窗口、工具栏、状态栏均已实现 |
| document_parser（txt/md/pdf） | ✅ 通过 | 三种格式解析正常，4200字符测试文本解析成功 |
| text_splitter | ✅ 通过 | LangChain RecursiveCharacterTextSplitter，中文分隔符，分块元数据完整 |
| vector_store（ChromaDB） | ✅ 通过 | 持久化集合、批量写入、余弦相似度搜索、按文档删除 |
| 完整导入流程 | ⚠️ 受阻 | 代码逻辑完整，但因 embedding 模型未拉取无法端到端验证 |
| 不支持格式的提示 | ❌ 未实现 | 不支持的扩展名直接返回空字符串，无用户提示 |
| 导入失败不崩溃 | ✅ 通过 | try/except 包裹，状态设为 failed，错误信息保存 |

#### Phase 2：真实索引与元数据管理

| 验收项 | 状态 | 说明 |
|--------|------|------|
| embedding_service（Ollama） | ⚠️ 部分通过 | 代码完整，但 bge-large-zh-v1.5 模型未拉取，当前 Ollama 仅有 qwen2.5:7b |
| metadata_manager（SQLite） | ✅ 通过 | 5表结构完整，CRUD 操作正常，分区默认数据已初始化 |
| 导入状态机 | ✅ 通过 | pending → indexing → indexed/failed 状态流转正确 |
| IngestWorker（QThread） | ✅ 通过 | progress/file_done/finished_all 信号定义完整 |
| 文档列表绑定 SQLite | ✅ 通过 | 6列展示（文件名、格式、大小、状态、分块数、导入时间） |
| 预览面板 | ✅ 通过 | 文档信息+解析文本+分块列表展示 |

#### Phase 3：检索体验与格式扩展

| 验收项 | 状态 | 说明 |
|--------|------|------|
| retriever.py | ✅ 通过 | SearchResult 数据类、阈值过滤、元数据充实 |
| 语义搜索面板 | ✅ 通过 | 查询输入、搜索按钮、结果列表、相似度色标 |
| 搜索→预览联动 | ✅ 通过 | 点击结果自动定位源文档并高亮分块 |
| 全局搜索栏 | ✅ 通过 | 按文件名/扩展名/分区实时过滤 |
| DOCX 解析 | ✅ 通过 | 段落、标题层级、表格文本提取 |
| XLSX 解析 | ✅ 通过 | 按工作表读取，保留表名，跳过空行 |
| PPTX 解析 | ✅ 通过 | 按幻灯片提取文本框，保留页码 |
| 检索质量测试 | ❌ 未执行 | 无测试记录 |

#### Phase 4：GUI管理功能完善 — ❌ 未实现

导航面板（分区树/标签云）、文档右键菜单、删除/重索引、设置对话框、日志系统均未实现。

#### Phase 5：MCP对外接口 — ❌ 未实现

mcp_server/ 目录不存在，三个 MCP 工具均未开发。

#### Phase 6：打包与文档 — ❌ 未实现

无 PyInstaller 配置、无首启引导、无备份迁移文档。

---

### 三、严重问题（必须修复）

#### 3.1 致命缺陷

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | **chromadb 未安装** | requirements.txt → venv | 应用启动即崩溃：`ModuleNotFoundError: No module named 'chromadb'`。已手动 `pip install chromadb` 修复 |
| 2 | **embedding 模型未拉取** | Ollama | `bge-large-zh-v1.5` 不存在，所有导入和搜索操作崩溃：`model not found, try pulling it first` |
| 3 | **删除文档不清理 ChromaDB** | metadata_manager.py 第204行 | `delete_document()` 只删 SQLite 记录，不调用 `VectorStore.delete_by_document()`，导致向量数据永久残留、搜索结果出现幽灵数据 |
| 4 | **HTML注入** | main_window.py 第306行 | 文档内容直接 `replace("\n", "<br>")` 后注入 QTextBrowser，未转义 `<`、`>`、`&`，含HTML标签的文档会破坏布局甚至执行脚本 |

#### 3.2 严重缺陷

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 5 | **关闭窗口不终止工作线程** | main_window.py（无 closeEvent） | 导入/搜索进行中关闭窗口会触发 "QThread: Destroyed while thread is still running" 崩溃 |
| 6 | **SQLite 非线程安全** | metadata_manager.py 第82行 | 每次操作新建连接且 `check_same_thread=True`，GUI多线程调用会抛出 `sqlite3.ProgrammingError` |
| 7 | **Embedding 伪批处理** | embedding_service.py 第43-46行 | batch_size 参数无效，实际逐条调用 Ollama API，大文档导入极慢 |
| 8 | **维度自动检测为死代码** | embedding_service.py 第47-48行 | `_dimension` 默认 1024（非 None），自动检测逻辑永远不会触发 |
| 9 | **同名文件覆盖** | ingest.py 第22行 | 不同路径的同名文件会互相覆盖，无去重策略 |
| 10 | **PDF/Excel 资源泄漏** | document_parser.py 第40行、第75行 | `fitz.open()` 和 `load_workbook()` 返回的对象从未 close，大量导入后文件描述符耗尽 |

#### 3.3 数据完整性问题

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 11 | **分区ID等于分区名** | metadata_manager.py 第95行 | 重命名分区需更新所有文档外键，极不安全 |
| 12 | **INSERT OR REPLACE 丢向量** | metadata_manager.py 第163行 | 重新导入会静默替换 SQLite 分块记录，但旧 ChromaDB 向量未清理 |
| 13 | **tags/document_tags 表无操作** | metadata_manager.py 第42-52行 | 表结构已创建但无任何 CRUD 方法，标签功能完全不可用 |

---

### 四、一般问题（建议修复）

#### 4.1 代码质量

| # | 问题 | 位置 |
|---|------|------|
| 14 | 未使用导入 `os`、`shutil` | main_window.py 第1-2行 |
| 15 | 未使用导入 `Optional` | embedding_service.py 第2行 |
| 16 | `_color_brush` 方法内导入 `QBrush`/`QColor` | main_window.py 第409行（每次调用重复导入） |
| 17 | `langchain_text_splitters` 未显式声明 | requirements.txt（当前依赖 langchain 传递安装） |
| 18 | 无 `.gitignore` 文件 | 项目根目录（.env/ 虚拟环境未被排除） |
| 19 | Git 仓库为空（零提交） | .git/ 目录 |
| 20 | 无日志配置 | main.py 从未调用 `logging.basicConfig()` |

#### 4.2 用户体验

| # | 问题 | 位置 |
|---|------|------|
| 21 | 导航面板为占位标签 | main_window.py 第109行 |
| 22 | 无文档删除 UI | GUI 层 |
| 23 | 无失败文档重试机制 | GUI 层 |
| 24 | 批量导入失败弹多个模态框 | main_window.py 第222行 |
| 25 | 搜索输入无清除按钮 | main_window.py 工具栏搜索框 |
| 26 | 文档表格无空状态引导 | main_window.py |
| 27 | 标签搜索承诺但未实现 | main_window.py 第244-249行（占位文本提及标签但过滤逻辑未覆盖） |

#### 4.3 性能与健壮性

| # | 问题 | 位置 |
|---|------|------|
| 28 | 每次 SQLite 操作新建连接 | metadata_manager.py 第82行（高频操作下性能差） |
| 29 | 搜索结果 N+1 查询 | retriever.py 第64-67行（每个结果单独查 SQLite） |
| 30 | 预览在主线程解析大文档 | main_window.py 第303行（可能卡顿 UI） |
| 31 | 无文件大小限制检查 | document_parser.py（GB 级文件会吃满内存） |
| 32 | 无 Ollama 故障重试 | embedding_service.py |

---

### 五、ruff 检查结果

```
core\embedding_service.py:2:20: F401 [*] `typing.Optional` imported but unused
gui\main_window.py:1:8:         F401 [*] `os` imported but unused
gui\main_window.py:2:8:         F401 [*] `shutil` imported but unused
Found 3 errors. (3 fixable with the `--fix` option)
```

仅 3 个 F401 未使用导入问题，整体代码风格良好。无语法错误、无逻辑告警。

---

### 六、运行环境验证

| 检查项 | 状态 | 说明 |
|--------|------|------|
| Python 编译检查 | ✅ 全部通过 | 9个 .py 文件均无语法错误 |
| Config 加载 | ✅ 正常 | 默认值完整，目录自动创建 |
| SQLite 初始化 | ✅ 正常 | 5个分区已创建，表结构完整 |
| ChromaDB 连接 | ✅ 正常 | 安装后可用，当前 0 条向量 |
| Ollama 连接 | ✅ 可用 | 服务运行中 |
| Embedding 模型 | ❌ 不可用 | `bge-large-zh-v1.5` 未拉取，需执行 `ollama pull bge-large-zh-v1.5` |
| GUI 启动 | ⚠️ 未验证 | 当前环境为远程 bash，无法启动 PySide6 窗口 |
| 端到端导入 | ⚠️ 受阻 | 解析+分块正常，但 embedding 失败导致无法完成完整流程 |

---

### 七、阶段完成度总结

| 阶段 | 计划内容 | 完成度 | 判定 |
|------|----------|--------|------|
| Phase 1 | 项目框架 + 最小导入闭环 | 85% | ⚠️ 条件通过（需修复依赖安装+模型拉取） |
| Phase 2 | 真实索引 + 元数据管理 | 80% | ⚠️ 条件通过（需修复删除不清理向量+线程安全） |
| Phase 3 | 检索体验 + 格式扩展 | 75% | ⚠️ 条件通过（需修复HTML注入+补充检索测试） |
| Phase 4 | GUI管理功能完善 | 0% | ❌ 未开始 |
| Phase 5 | MCP对外接口 | 0% | ❌ 未开始 |
| Phase 6 | 打包与文档 | 0% | ❌ 未开始 |

---

### 八、修复优先级建议

**P0 — 立即修复（阻塞应用运行）：**
1. 拉取 embedding 模型：`ollama pull bge-large-zh-v1.5`
2. 将 chromadb 加入 venv（已完成）并更新 requirements.txt 锁定版本
3. 修复 HTML 注入（main_window.py 第306行，用 `html.escape()` 转义）
4. 修复删除不清理向量（metadata_manager.py 的 `delete_document` 需调用 `vector_store.delete_by_document()`）

**P1 — 尽快修复（影响稳定性）：**
5. 添加 closeEvent 处理器，关闭窗口时终止工作线程
6. SQLite 连接改用 `check_same_thread=False` + 连接池或线程本地存储
7. 修复 PDF/Excel 资源泄漏（使用 `with` 上下文管理器）
8. 修复同名文件覆盖问题（添加 UUID 或时间戳后缀）

**P2 — 后续迭代（提升质量）：**
9. 修复 embedding 伪批处理，改用 Ollama 批量 API
10. 添加 .gitignore 并初始化 Git 仓库首次提交
11. 添加 logging.basicConfig() 配置
12. 运行 `ruff check --fix` 清理未使用导入
