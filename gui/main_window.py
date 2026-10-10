import html
import logging
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.document_parser import DocumentParser
from core.embedding_service import EmbeddingService
from core.ingest import ingest_document
from core.metadata_manager import DEFAULT_PARTITION_ID, MetadataManager
from core.note_store import NoteStore
from core.retriever import Retriever
from core.text_splitter import KnowledgeTextSplitter
from core.vector_store import VectorStore
from core.workspace import WorkspaceManager
# 对话框由设计文档 9.3 拆分为独立模块；这里重新导出以保持既有导入路径可用
from gui.dialogs.incremental_dialog import IncrementalUpdateDialog  # noqa: F401
from gui.dialogs.settings_dialog import SettingsDialog
from gui.dialogs.startup_dialog import StartupDialog  # noqa: F401
from gui.editor.graph_view import GraphView
from gui.panels.note_workspace import NoteWorkspace
from gui.panels.detail_panel import DetailPanel
from gui.panels.doc_list_panel import (
    STATUS_LABELS,
    DocListPanel,
    format_size,
    format_time,
)
from gui.panels.nav_panel import NavPanel
from gui.panels.status_bar import StatusBar
from gui.panels.top_nav_bar import TopNavBar
from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT, score_to_color
from gui.workers.ingest_worker import IngestWorker
from gui.workers.search_worker import SearchWorker

logger = logging.getLogger(__name__)


def _esc(s: str) -> str:
    return html.escape(str(s))


class ReindexWorker(QThread):
    progress = Signal(int, str)
    file_done = Signal(str, bool, str, str)
    finished_all = Signal(int, int)

    def __init__(self, doc_ids: list[str], reindex_fn):
        super().__init__()
        self.doc_ids = doc_ids
        self.reindex_fn = reindex_fn

    def run(self):
        total = len(self.doc_ids)
        success = 0
        fail = 0
        for i, doc_id in enumerate(self.doc_ids, start=1):
            self.progress.emit(int(i / total * 100), doc_id)
            try:
                new_id = self.reindex_fn(doc_id)
                self.file_done.emit(new_id, True, doc_id, "")
                success += 1
            except Exception as e:
                logger.exception("重新索引失败: %s", doc_id)
                self.file_done.emit("", False, doc_id, str(e))
                fail += 1
        self.finished_all.emit(success, fail)


class MainWindow(QMainWindow):
    def __init__(self, config: Config, capabilities=None):
        super().__init__()
        self.config = config

        # 运行时能力：未配置本地模型时进入受限模式，
        # 笔记库等功能照常可用，仅禁用语义检索与文档导入。
        if capabilities is None:
            from core.capabilities import probe

            capabilities = probe(config)
        self.capabilities = capabilities

        self._apply_theme(getattr(config, "theme", "dark"))

        self.parser = DocumentParser()
        self.splitter = KnowledgeTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )

        self._workspace_manager = WorkspaceManager(
            config, Path(config.chroma_dir).parent.parent
        )
        self._workspace_manager.ensure_default()

        current_ws = self._workspace_manager.get_current()
        self.vector_store = VectorStore(str(current_ws.chroma_dir))
        self.metadata = MetadataManager(str(current_ws.sqlite_path), vector_store=self.vector_store)
        self.embedder = self._build_embedder(config)

        self._current_doc_id: str | None = None
        self._current_partition_id: str | None = None
        self._current_tag_id: str | None = None
        self._ingest_worker: IngestWorker | None = None
        self._search_worker: SearchWorker | None = None
        self._reindex_worker: ReindexWorker | None = None
        self._all_documents: list = []
        self._current_filter: str = ""

        self.note_store: NoteStore | None = None
        self._current_view: str = "docs"
        self._resolved_theme: str = "dark"

        self.retriever = Retriever(
            embedder=self.embedder,
            vector_store=self.vector_store,
            metadata=self.metadata,
            config=self.config,
        )

        self.setWindowTitle("KVault · 个人知识库")
        self.resize(1400, 860)

        self._setup_toolbar()
        self._setup_central_layout()
        self._setup_status_bar()
        self._setup_shortcuts()

        # 注册打包字体（gui/styles/fonts/ 存在时）
        from gui.styles.fonts import register_bundled_fonts
        register_bundled_fonts()

        self._reload_all()
        self._check_environment()

    # ---------------------------------------------------------------- 视图切换

    VIEWS = ("docs", "notes", "graph")

    def _switch_view(self, view: str) -> None:
        """在「文档 / 笔记 / 图谱」三种视图之间切换。"""
        if view not in self.VIEWS:
            return

        self._current_view = view
        self.main_stack.setCurrentIndex(self.VIEWS.index(view))

        for name, button in (
            ("docs", self.docs_view_button),
            ("notes", self.notes_view_button),
            ("graph", self.graph_view_button),
        ):
            button.setProperty("btnType", "primary" if name == view else "secondary")
            # 动态属性变化后必须重新 polish 才会应用新样式
            button.style().unpolish(button)
            button.style().polish(button)

        # 「文档」视图专属部件只在需要时可见
        show_docs = view == "docs"
        self.nav_panel.setVisible(show_docs)
        self.view_switch.setVisible(True)

        if view == "notes":
            self.note_workspace.refresh()
            if self.note_workspace.editor.is_dirty():
                self.note_workspace.save_current()
        elif view == "graph":
            self._refresh_graph()

    def _refresh_graph(self) -> None:
        """重建图谱视图。"""
        if self.note_store is None:
            return
        self.note_workspace.show_graph(self.graph_view)
        stats = self.note_store.stats()
        self.graph_status.setText(
            f"{stats['notes']} 篇笔记 · {stats['links']} 条链接 · "
            f"{stats['broken_links']} 条断链 · 图中显示 {self.graph_view.node_count()} 个节点"
        )

    def _open_graph_node(self, path: str) -> None:
        """点击图谱节点时打开对应笔记。"""
        if self.note_workspace.open_note(path):
            self._switch_view("notes")

    def _on_note_saved(self) -> None:
        """笔记保存后刷新状态栏。"""
        self.status_bar.show_message("笔记已保存")

    def _on_note_stats(self, stats: dict) -> None:
        """笔记统计变化时更新状态栏。"""
        self.status_bar.set_stats_summary(
            f"笔记 {stats['notes']} · 链接 {stats['links']} · 标签 {stats['tags']}"
        )

    def _resolve_theme(self) -> str:
        """把配置里的主题名解析为具体主题（system -> dark/light）。"""
        from gui.styles.apply import resolve_system_theme

        theme = getattr(self.config, "theme", "dark")
        return resolve_system_theme() if theme == "system" else theme

    def _apply_theme(self, theme: str) -> str:
        from PySide6.QtWidgets import QApplication

        from gui.styles.apply import apply_theme

        app = QApplication.instance()
        if app is None:
            return "dark"
        resolved = apply_theme(app, theme)
        self._resolved_theme = resolved
        # 笔记视图自带一套高亮配色，需跟随主题一起切换
        if getattr(self, "note_workspace", None) is not None:
            self.note_workspace.set_theme(resolved)
        if getattr(self, "graph_view", None) is not None:
            self.graph_view.set_theme(resolved)
        if getattr(self, "doc_list_panel", None) is not None:
            self.doc_list_panel.set_theme(resolved)
        return resolved

    def _setup_shortcuts(self):
        """注册全局键盘快捷键（设计规范 5.6）。"""
        from gui.shortcuts import ShortcutManager

        handlers = {
            "import_docs": self._on_import,
            "focus_global_search": self.top_nav_bar.focus_global_search,
            "focus_semantic_search": self._focus_semantic_search,
            "open_settings": self._open_settings,
            "refresh_status": self._refresh_status_panel,
            "delete_selected": self._delete_selected_docs,
            "clear_selection": self.doc_list_panel.clear_selection,
            "tab_preview": self.detail_panel.switch_to_preview,
            "tab_search": self.detail_panel.switch_to_search,
            "tab_metadata": self.detail_panel.switch_to_metadata,
            "view_notes": lambda: self._switch_view("notes"),
            "view_graph": lambda: self._switch_view("graph"),
            "quick_switch": self._open_quick_switcher,
            "command_palette": self._open_command_palette,
        }
        self._shortcut_manager = ShortcutManager(self, handlers)

    def _open_quick_switcher(self):
        """Ctrl+O：快速打开笔记。"""
        if self.note_store is None:
            return
        from gui.editor.quick_switcher import NoteCandidate, show_quick_switcher

        candidates = [
            NoteCandidate(record.path, record.title or record.name)
            for record in self.note_store.list_notes()
        ]
        dialog = show_quick_switcher(self, candidates)
        dialog.noteChosen.connect(self._open_note_from_switcher)

    def _open_note_from_switcher(self, path: str):
        """从快速切换器打开笔记，并切到笔记视图。"""
        if self.note_workspace.open_note(path):
            self._switch_view("notes")

    def _open_command_palette(self):
        """命令面板：列出常用操作。"""
        from gui.editor.quick_switcher import Command, show_command_palette

        commands = [
            Command("新建笔记", lambda: self._switch_view("notes"), "Ctrl+Shift+N"),
            Command("打开图谱", lambda: self._switch_view("graph"), "Ctrl+G"),
            Command("切换到文档", lambda: self._switch_view("docs")),
            Command("快速打开笔记", self._open_quick_switcher, "Ctrl+O"),
            Command("语义检索", self._focus_semantic_search, "Ctrl+K"),
            Command("刷新笔记索引", self._sync_notes, "Ctrl+R"),
            Command("保存当前笔记", lambda: self.note_workspace.save_current(), "Ctrl+S"),
            Command("设置", self._open_settings, "Ctrl+S"),
        ]
        dialog = show_command_palette(self, commands)
        dialog.commandChosen.connect(self._run_command)

    def _run_command(self, command):
        """执行命令面板选中的命令。"""
        if callable(command.action):
            command.action()

    def _sync_notes(self):
        """从磁盘全量同步笔记索引（含外部编辑器的改动）。"""
        if self.note_store is None:
            return
        report = self.note_store.sync_all()
        self.note_workspace.refresh()
        summary = report.as_dict()
        self.status_bar.show_message(
            f"笔记同步完成：新增 {summary['added']}、更新 {summary['updated']}、"
            f"移除 {summary['removed']}",
            4000,
        )

    def _focus_semantic_search(self):
        """Ctrl+K：切到检索标签页并聚焦检索输入框。"""
        self.detail_panel.switch_to_search()
        self.detail_panel.search_tab.focus_search()

    def _setup_toolbar(self):
        self.top_nav_bar = TopNavBar(self.config)
        self.top_nav_bar.importRequested.connect(self._on_import)
        self.top_nav_bar.searchChanged.connect(self._on_global_search_changed)
        self.top_nav_bar.settingsRequested.connect(self._open_settings)
        self.top_nav_bar.logsRequested.connect(self._open_logs_dir)
        self.top_nav_bar.workspaceSwitchRequested.connect(self._switch_workspace)
        self.top_nav_bar.workspaceCreateRequested.connect(self._on_workspace_create)
        self.top_nav_bar.workspaceDeleteRequested.connect(self._on_workspace_delete)
        self.top_nav_bar.viewActionRequested.connect(self._switch_view)
        self.top_nav_bar.quickSwitchRequested.connect(self._open_quick_switcher)
        self.top_nav_bar.commandPaletteRequested.connect(self._open_command_palette)

    def _setup_central_layout(self):
        self.status_bar = StatusBar(
            reduce_motion=getattr(self.config, "reduce_motion", False)
        )
        # 无模型启动后，用户在设置里配好模型即可点击状态栏恢复能力
        self.status_bar.set_retry_handler(self._on_retry_capabilities)


        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.top_nav_bar)

        # 视图切换栏：「文档」做语义检索，「笔记」做写作与链接
        self.view_switch = QWidget()
        self.view_switch.setObjectName("ViewSwitchBar")
        switch_layout = QHBoxLayout(self.view_switch)
        switch_layout.setContentsMargins(12, 6, 12, 6)
        switch_layout.setSpacing(6)

        self.docs_view_button = QPushButton("文档", self.view_switch)
        self.docs_view_button.setObjectName("ViewSwitchButton")
        self.docs_view_button.setProperty("btnType", "primary")
        self.notes_view_button = QPushButton("笔记", self.view_switch)
        self.notes_view_button.setObjectName("ViewSwitchButton")
        self.graph_view_button = QPushButton("图谱", self.view_switch)
        self.graph_view_button.setObjectName("ViewSwitchButton")
        self.graph_view_button.setToolTip("查看笔记之间的链接网络")

        self.docs_view_button.clicked.connect(lambda: self._switch_view("docs"))
        self.notes_view_button.clicked.connect(lambda: self._switch_view("notes"))
        self.graph_view_button.clicked.connect(lambda: self._switch_view("graph"))

        switch_layout.addWidget(self.docs_view_button)
        switch_layout.addWidget(self.notes_view_button)
        switch_layout.addWidget(self.graph_view_button)
        switch_layout.addStretch(1)

        main_layout.addWidget(self.view_switch)

        splitter = QSplitter(Qt.Horizontal)

        self.nav_panel = self._build_nav_panel()
        self.nav_panel.setMinimumWidth(220)
        self.nav_panel.setMaximumWidth(320)

        self.doc_list_panel = DocListPanel(
            reduce_motion=getattr(self.config, "reduce_motion", False)
        )
        self.doc_list_panel.documentSelected.connect(self._on_document_selected_id)
        self.doc_list_panel.contextMenuRequested.connect(self._show_document_context_menu)
        self.doc_list_panel.importRequested.connect(self._on_import)
        self.doc_list_panel.filesDropped.connect(self._import_paths)
        self.doc_list_panel.batchActionRequested.connect(self._on_batch_action)
        # §3.3.3 视图模式记忆到 config
        self.doc_list_panel.attach_config(self.config)
        self.doc_list_panel.set_theme(self._resolved_theme)

        self.detail_panel = DetailPanel(default_top_k=self.config.top_k)
        self.detail_panel.searchRequested.connect(self._on_search)
        self.detail_panel.resultClicked.connect(self._on_result_clicked)

        # 「文档」视图：导航 + 文档列表 + 详情
        splitter.addWidget(self.nav_panel)
        splitter.addWidget(self.doc_list_panel)
        splitter.addWidget(self.detail_panel)
        splitter.setSizes([220, 500, 680])

        self.docs_stack = QWidget()
        docs_layout = QHBoxLayout(self.docs_stack)
        docs_layout.setContentsMargins(0, 0, 0, 0)
        docs_layout.setSpacing(0)
        docs_layout.addWidget(self.nav_panel)
        docs_layout.addWidget(splitter)

        # 「笔记」视图
        current_ws = self._workspace_manager.get_current()
        self.note_store = NoteStore(
            str(current_ws.sqlite_path), current_ws.base_dir / "vault", self.metadata
        )
        self.note_workspace = NoteWorkspace(self.note_store)
        self.note_workspace.noteSaved.connect(lambda _p: self._on_note_saved())
        self.note_workspace.statsChanged.connect(self._on_note_stats)
        self.note_workspace.set_theme(self._resolve_theme())

        # 「图谱」视图
        self.graph_view = GraphView()
        self.graph_view.set_theme(self._resolve_theme())
        self.graph_view.nodeSelected.connect(self._open_graph_node)

        self.graph_stack = QWidget()
        graph_layout = QVBoxLayout(self.graph_stack)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_toolbar = QWidget(self.graph_stack)
        graph_toolbar.setObjectName("GraphToolbar")
        graph_toolbar_layout = QHBoxLayout(graph_toolbar)
        graph_toolbar_layout.setContentsMargins(12, 6, 12, 6)
        self.graph_status = QLabel("", graph_toolbar)
        self.graph_status.setObjectName("GraphStatus")
        self.graph_refresh_button = QPushButton("刷新", graph_toolbar)
        self.graph_refresh_button.clicked.connect(self._refresh_graph)
        graph_toolbar_layout.addWidget(self.graph_status, 1)
        graph_toolbar_layout.addWidget(self.graph_refresh_button)
        graph_layout.addWidget(graph_toolbar)
        graph_layout.addWidget(self.graph_view, 1)

        self.main_stack = QStackedWidget()
        self.main_stack.addWidget(self.docs_stack)
        self.main_stack.addWidget(self.note_workspace)
        self.main_stack.addWidget(self.graph_stack)

        main_layout.addWidget(self.main_stack, 1)
        main_layout.addWidget(self.status_bar)
        self.setCentralWidget(container)

    def _build_nav_panel(self) -> NavPanel:
        panel = NavPanel(default_partition_id=DEFAULT_PARTITION_ID)
        panel.partitionSelected.connect(self._on_partition_selected_id)
        panel.tagSelected.connect(self._on_tag_selected_id)
        panel.partitionCreateRequested.connect(self._create_partition)
        panel.partitionRenameRequested.connect(self._rename_partition)
        panel.partitionDeleteRequested.connect(self._delete_partition)
        panel.refreshStatsRequested.connect(self._refresh_status_panel)
        return panel

    def _setup_status_bar(self):
        self.progress_bar = self.status_bar._progress_bar
        self.status_bar.show_message("本地运行 · 就绪")

    def _check_environment(self):
        """根据运行时能力刷新状态提示。

        受限模式下**不视为错误**——笔记库等功能不受影响，因此这里给出的是
        「提示 + 重试入口」而非失败告警。
        """
        if self.capabilities.limited:
            self._apply_degraded_mode()
            return

        if not self.embedder.is_model_available():
            self.status_bar.show_message(f"模型未就绪: {self.config.embedding_model}")
            logger.warning("模型不可用: %s", self.config.embedding_model)
        else:
            self.status_bar.show_message("本地运行 · 就绪")
            self.status_bar.set_ollama_status(True)

    def _apply_degraded_mode(self) -> None:
        """进入受限模式：禁用依赖嵌入的功能，并提供配置指引。"""
        caps = self.capabilities
        logger.warning("受限模式：%s", caps.summary())
        for reason in caps.reasons:
            logger.warning("  - %s", reason)

        # 后端名如实反映配置：选 llama.cpp 时显示「模型」，
        # 否则显示「Ollama ✗」会让用户误以为需要启动 Ollama。
        self.status_bar.set_backend_label(
            "llama.cpp" if caps.backend_type == "llama_cpp" else "Ollama"
        )

        # 依赖嵌入模型的入口一律禁用，而不是让用户点了之后报错
        self.top_nav_bar.set_import_enabled(False)
        self.detail_panel.set_search_enabled(False)

        self.status_bar.show_message(
            "受限模式 · 笔记库可用，语义检索与导入已禁用（点击状态栏重试检测）", 0
        )
        self.status_bar.set_ollama_status(False)
        self.status_bar.set_degraded(True)

    def _on_retry_capabilities(self) -> None:
        """状态栏点击触发的能力重检（重新探测 + 刷新 UI 状态）。"""
        self.retry_capability_check()

    def retry_capability_check(self) -> None:
        """重新探测运行时能力，用户配置完模型后调用。"""
        from core.capabilities import probe

        self.capabilities = probe(self.config)
        self._log_and_apply_capabilities()
        from core.capabilities import probe

        self.capabilities = probe(self.config)
        self._log_and_apply_capabilities()

    def _log_and_apply_capabilities(self) -> None:
        caps = self.capabilities
        if caps.limited:
            self._apply_degraded_mode()
        else:
            self.top_nav_bar.set_import_enabled(True)
            self.detail_panel.set_search_enabled(True)
            self.status_bar.set_degraded(False)
            self.status_bar.set_backend_label(
                "llama.cpp" if caps.backend_type == "llama_cpp" else "Ollama"
            )
            self.status_bar.set_ollama_status(self.embedder.is_available())
            self.status_bar.show_message("本地运行 · 就绪")
            QMessageBox.information(self, "检测通过", caps.user_message())

    def capabilities_user_message(self) -> str:
        """面向用户的受限模式说明。"""
        return self.capabilities.user_message()

    def _reload_all(self):
        self._reload_workspace_combo()
        self._reload_nav_panel()
        self._reload_document_list()
        self._refresh_status_panel()

    def _reload_nav_panel(self):
        self.nav_panel.set_partitions(
            self.metadata.list_partitions_with_counts(),
            current_id=self._current_partition_id,
        )
        self.nav_panel.set_tags(
            self.metadata.list_tags_with_counts(),
            current_id=self._current_tag_id,
        )

    def _on_partition_selected_id(self, partition_id):
        self._current_partition_id = partition_id
        self._current_tag_id = None
        self._reload_document_list()

    def _on_tag_selected_id(self, tag_id):
        self._current_tag_id = tag_id
        self._current_partition_id = None
        self._reload_document_list()

    def _create_partition(self):
        name, ok = QInputDialog.getText(self, "新建分区", "分区名称:")
        if ok and name.strip():
            try:
                self.metadata.create_partition(name.strip())
            except ValueError as e:
                QMessageBox.warning(self, "创建失败", str(e))
                return
            self._reload_nav_panel()

    def _rename_partition(self, partition_id: str):
        partition = self.metadata.get_partition(partition_id)
        if not partition:
            return
        name, ok = QInputDialog.getText(
            self, "重命名分区", "新名称:", text=partition["name"]
        )
        if ok and name.strip():
            self.metadata.rename_partition(partition_id, name.strip())
            self._reload_nav_panel()
            self._reload_document_list()

    def _delete_partition(self, partition_id: str):
        reply = QMessageBox.question(
            self,
            "删除分区",
            "删除分区后，其中文档将移动到默认分区。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.metadata.delete_partition(partition_id, DEFAULT_PARTITION_ID)
            if self._current_partition_id == partition_id:
                self._current_partition_id = None
            self._reload_all()

    def _refresh_status_panel(self):
        stats = self.metadata.get_stats()
        chroma_count = self.vector_store.count()
        model_name = self.config.embedding_model.split('/')[-1]
        summary = (
            f"{stats.get('total_docs', 0)} 文档 · "
            f"{stats.get('total_chunks', 0)} 块 · {model_name}"
        )
        # §3.2 展开为 4 行详细统计
        details = [
            f"已索引: {stats.get('indexed_docs', 0)}",
            f"失败: {stats.get('failed_docs', 0)}",
            f"向量数: {chroma_count}",
            f"分区: {stats.get('partition_count', 0)} · 标签: {stats.get('tag_count', 0)}",
        ]
        self.nav_panel.set_stats(summary, details)

        # §3.5 工作区下拉旁展示文档数徽章
        self.top_nav_bar.set_doc_count_badge(stats.get("total_docs", 0))

        # §3.6 Ollama 状态指示
        self.status_bar.set_ollama_status(self.embedder.is_available())

    def _sync_doc_count_badge(self) -> None:
        """单独刷新文档数徽章（不重算完整统计）。"""
        stats = self.metadata.get_stats()
        self.top_nav_bar.set_doc_count_badge(stats.get("total_docs", 0))

    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要导入的文档",
            "",
            "支持的文档 (*.txt *.md *.pdf *.docx *.xlsx *.pptx)"
        )
        if not paths:
            return
        self._import_paths(paths)

    def _import_paths(self, paths: list[str]):
        """按给定路径列表启动导入（文件对话框 / 拖拽共用）。"""
        if not paths:
            return

        partition_id = self._current_partition_id or DEFAULT_PARTITION_ID

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self._ingest_worker = IngestWorker(
            file_paths=list(paths),
            ingest_fn=lambda p: self._ingest_with_partition(p, partition_id),
        )
        self._ingest_worker.progress.connect(self._on_ingest_progress)
        self._ingest_worker.file_done.connect(self._on_ingest_file_done)
        self._ingest_worker.finished_all.connect(self._on_ingest_finished)
        self._ingest_worker.start()

    def _on_batch_action(self, action_id: str, doc_ids: list[str]):
        """批量操作浮动条入口，分发到既有的批量处理器。"""
        if not doc_ids:
            return
        if action_id == "move":
            self._show_batch_move_menu(doc_ids)
        elif action_id == "tag":
            self._edit_tags_for_selected()
        elif action_id == "reindex":
            self._reindex_selected()
        elif action_id == "delete":
            self._delete_selected_docs()

    def _show_batch_move_menu(self, doc_ids: list[str]):
        from PySide6.QtGui import QCursor

        menu = QMenu(self)
        for p in self.metadata.list_partitions():
            action = QAction(p["name"], self)
            action.triggered.connect(lambda checked, pid=p["id"]: self._move_selected_docs(pid))
            menu.addAction(action)
        menu.exec(QCursor.pos())

    def _ingest_with_partition(self, path: str, partition_id: str) -> str:
        return ingest_document(
            path,
            self.config,
            self.parser,
            self.splitter,
            self.embedder,
            self.vector_store,
            self.metadata,
            partition_id=partition_id,
        )

    def _on_ingest_progress(self, percent: int, file_name: str):
        self.progress_bar.setValue(percent)
        self.status_bar.show_message(f"正在索引: {file_name} ({percent}%)")

    def _on_ingest_file_done(self, doc_id: str, success: bool, file_name: str, error: str):
        if success:
            self.status_bar.show_message(f"导入完成: {file_name}")
            logger.info("导入成功: %s -> %s", file_name, doc_id)
        else:
            QMessageBox.critical(self, "导入失败", f"{file_name}\n{error}")
            self.status_bar.show_message(f"导入失败: {file_name}")
            logger.error("导入失败: %s - %s", file_name, error)
        self._reload_all()

    def _on_ingest_finished(self, success_count: int, fail_count: int):
        self.progress_bar.setVisible(False)
        msg = f"批量导入完成: 成功 {success_count} 个"
        if fail_count:
            msg += f", 失败 {fail_count} 个"
        self.status_bar.show_message(msg)
        self._check_environment()

    def _reload_document_list(self):
        tag_ids = [self._current_tag_id] if self._current_tag_id else None
        self._all_documents = self.metadata.list_documents(
            partition_id=self._current_partition_id,
            tag_ids=tag_ids,
        )
        self._apply_document_filter()

    def _apply_document_filter(self):
        keyword = self._current_filter.strip().lower()

        docs = self._all_documents
        if keyword:
            tag_map = self.metadata.get_documents_tag_map([d.id for d in docs])
            docs = [
                doc for doc in docs
                if keyword in doc.file_name.lower()
                or keyword in doc.file_ext.lower()
                or (doc.partition_name and keyword in doc.partition_name.lower())
                or any(
                    keyword in tag["name"].lower()
                    for tag in tag_map.get(doc.id, [])
                )
            ]

        self.doc_list_panel.set_documents(docs)

    def _on_document_selected_id(self, doc_id):
        self._current_doc_id = doc_id
        if doc_id is None:
            self.detail_panel.preview_tab.clear_preview()
            return
        self._load_preview(doc_id)

    def _load_preview(self, doc_id: str):
        preview = self.detail_panel.preview_tab
        doc = self.metadata.get_document(doc_id)
        if doc is None:
            preview.set_not_found("文档不存在")
            return

        content = ""
        if doc.status == "indexed" and Path(doc.stored_path).exists():
            try:
                content = self.parser.parse(doc.stored_path).content
            except Exception:  # noqa: BLE001 —— 预览失败不应中断元数据加载
                logger.warning("预览加载失败: %s", doc_id, exc_info=True)
                content = ""

        html_text = preview.build_document_html(
            doc,
            content=content,
            chunks=self.metadata.get_document_chunks(doc_id),
            tags=self.metadata.get_document_tags(doc_id),
            partitions=doc.partition_name or "未分类",
            error_message=(doc.error_message or "") if doc.status == "failed" else "",
            size_label=format_size(doc.file_size),
            status_label=STATUS_LABELS.get(doc.status, doc.status),
        )
        preview.set_html(html_text)

        self._load_metadata(doc)
        self.detail_panel.switch_to_preview()

    def _load_metadata(self, doc):
        pairs = [
            ("文档 ID", doc.id),
            ("文件名", doc.file_name),
            ("格式", doc.file_ext.upper()),
            ("大小", format_size(doc.file_size)),
            ("状态", STATUS_LABELS.get(doc.status, doc.status)),
            ("块数", str(doc.chunk_count)),
            ("分区", doc.partition_name or "未分类"),
            ("标签", ", ".join(t["name"] for t in self.metadata.get_document_tags(doc.id))),
            ("存储路径", doc.stored_path),
            ("导入时间", format_time(doc.created_at)),
        ]
        if doc.status == "failed" and doc.error_message:
            pairs.append(("错误信息", doc.error_message))
        self.detail_panel.metadata_tab.set_metadata(pairs)

    def _on_global_search_changed(self, text: str):
        self._current_filter = text
        self._apply_document_filter()

    def _on_search(self, query: str, top_k: int):
        query = (query or "").strip()
        if not query:
            self.detail_panel.search_tab.clear_results()
            return

        filters = self._build_search_filters()
        if filters and filters.get("_empty"):
            self.detail_panel.search_tab.show_results([], self._score_color)
            self.status_bar.show_message("检索完成：无结果")
            return

        self.detail_panel.search_tab.set_busy(True)
        self.status_bar.show_message("正在检索...")

        self._search_worker = SearchWorker(
            retriever=self.retriever,
            query=query,
            top_k=top_k,
            filters=filters,
        )
        self._search_worker.results.connect(self._on_search_results)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.finished.connect(
            lambda: self.detail_panel.search_tab.set_busy(False)
        )
        self._search_worker.start()

    def _build_search_filters(self) -> dict | None:
        if not self._current_partition_id:
            return None
        doc_ids = [
            d.id
            for d in self.metadata.list_documents(
                partition_id=self._current_partition_id
            )
        ]
        if not doc_ids:
            return {"_empty": True}
        return {"document_id": {"$in": doc_ids}}

    def _on_search_results(self, results):
        self.detail_panel.search_tab.show_results(results, self._score_color)
        self.detail_panel.switch_to_search()
        if not results:
            self.status_bar.show_message("检索完成：无结果")
            return
        self.status_bar.show_message(f"检索完成：{len(results)} 条结果")

    def _on_search_error(self, error: str):
        self.detail_panel.search_tab.show_error(error)
        self.status_bar.show_message("检索失败")
        logger.error("检索失败: %s", error)

    def _on_result_clicked(self, result):
        if result is None:
            return

        document_id = result.document_id
        if self.doc_list_panel.select_doc(document_id):
            self._load_preview_with_chunk(document_id, result.chunk_index)

    def _load_preview_with_chunk(self, doc_id: str, chunk_index: int):
        self._load_preview(doc_id)
        chunks = self.metadata.get_document_chunks(doc_id)
        if 0 <= chunk_index < len(chunks):
            preview = _esc(chunks[chunk_index]["content_preview"])
            self.detail_panel.preview_tab.append_hit_chunk(
                f"<h3>检索命中块 {chunk_index + 1}</h3>"
                f"<p>{preview}</p>"
            )

    def _show_document_context_menu(self, global_pos, doc_ids: list[str]):
        if not doc_ids:
            return

        menu = QMenu(self)

        open_action = QAction("打开原始文件", self)
        open_action.triggered.connect(self._open_selected_original)
        menu.addAction(open_action)

        move_menu = QMenu("移动到分区", self)
        for p in self.metadata.list_partitions():
            action = QAction(p["name"], self)
            action.triggered.connect(lambda checked, pid=p["id"]: self._move_selected_docs(pid))
            move_menu.addAction(action)
        menu.addMenu(move_menu)

        tag_action = QAction("编辑标签", self)
        tag_action.triggered.connect(self._edit_tags_for_selected)
        menu.addAction(tag_action)

        reindex_action = QAction("重新索引", self)
        reindex_action.triggered.connect(self._reindex_selected)
        menu.addAction(reindex_action)

        if len(doc_ids) == 1:
            doc = self.metadata.get_document(doc_ids[0])
            if doc and doc.status == "failed":
                error_action = QAction("查看错误详情", self)
                error_action.triggered.connect(lambda: QMessageBox.critical(
                    self, "错误详情", _esc(doc.error_message or "未知错误")
                ))
                menu.addAction(error_action)

        menu.addSeparator()
        delete_action = QAction("删除文档", self)
        delete_action.triggered.connect(self._delete_selected_docs)
        menu.addAction(delete_action)

        menu.exec(global_pos)

    def _get_selected_doc_ids(self) -> list[str]:
        return self.doc_list_panel.selected_doc_ids()

    def _open_selected_original(self):
        for doc_id in self._get_selected_doc_ids():
            doc = self.metadata.get_document(doc_id)
            if doc and Path(doc.original_path).exists():
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(Path(doc.original_path).resolve()))
                )

    def _move_selected_docs(self, partition_id: str):
        for doc_id in self._get_selected_doc_ids():
            self.metadata.update_partition(doc_id, partition_id)
        self._reload_all()

    def _edit_tags_for_selected(self):
        doc_ids = self._get_selected_doc_ids()
        if not doc_ids:
            return

        # Only single-doc tag editing for simplicity
        doc_id = doc_ids[0]
        current_tags = self.metadata.get_document_tags(doc_id)

        dialog = QDialog(self)
        dialog.setWindowTitle("编辑标签")
        layout = QVBoxLayout(dialog)

        tag_input = QLineEdit(", ".join(t["name"] for t in current_tags))
        tag_input.setPlaceholderText("输入标签，用逗号分隔")
        layout.addWidget(tag_input)

        existing = ", ".join(t["name"] for t in self.metadata.list_tags())
        layout.addWidget(QLabel(f"已有标签: {existing}"))

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        names = [n.strip() for n in tag_input.text().split(",") if n.strip()]
        tag_ids = []
        for name in names:
            tag_ids.append(self.metadata.create_tag(name))

        self.metadata.set_document_tags(doc_id, tag_ids)
        self._reload_all()

    def _reindex_selected(self):
        doc_ids = self._get_selected_doc_ids()
        if not doc_ids:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self._reindex_worker = ReindexWorker(
            doc_ids=doc_ids,
            reindex_fn=self._reindex_document,
        )
        self._reindex_worker.progress.connect(self._on_ingest_progress)
        self._reindex_worker.file_done.connect(self._on_reindex_file_done)
        self._reindex_worker.finished_all.connect(self._on_reindex_finished)
        self._reindex_worker.start()

    def _reindex_document(self, doc_id: str) -> str:
        doc = self.metadata.get_document(doc_id)
        if not doc:
            raise ValueError("文档不存在")
        self.metadata.delete_document(doc_id, delete_file=False)
        return self._ingest_with_partition(doc.original_path or doc.stored_path, doc.partition_id or DEFAULT_PARTITION_ID)

    def _on_reindex_file_done(self, doc_id: str, success: bool, original_id: str, error: str):
        if success:
            self.status_bar.show_message(f"重新索引完成: {original_id}")
            logger.info("重新索引成功: %s -> %s", original_id, doc_id)
        else:
            QMessageBox.critical(self, "重新索引失败", f"{original_id}\n{error}")
            self.status_bar.show_message(f"重新索引失败: {original_id}")
            logger.error("重新索引失败: %s - %s", original_id, error)
        self._reload_all()

    def _on_reindex_finished(self, success_count: int, fail_count: int):
        self.progress_bar.setVisible(False)
        msg = f"重新索引完成: 成功 {success_count} 个"
        if fail_count:
            msg += f", 失败 {fail_count} 个"
        self.status_bar.show_message(msg)

    def _delete_selected_docs(self):
        doc_ids = self._get_selected_doc_ids()
        if not doc_ids:
            return

        reply = QMessageBox.question(
            self,
            "删除文档",
            f"确定要删除选中的 {len(doc_ids)} 个文档吗？\n将同时删除索引向量和本地副本。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        deleted = 0
        for doc_id in doc_ids:
            try:
                self.metadata.delete_document(doc_id, delete_file=True)
                deleted += 1
            except Exception as e:
                logger.exception("删除文档失败: %s", doc_id)
                QMessageBox.critical(self, "删除失败", f"{doc_id}\n{e}")

        self.status_bar.show_message(f"已删除 {deleted} 个文档")
        self._current_doc_id = None
        self._reload_all()

    def _open_settings(self):
        old_backend = self.config.embedding_backend
        old_theme = getattr(self.config, "theme", "dark")
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            # 主题运行时切换（无需重启）
            if self.config.theme != old_theme:
                self._apply_theme(self.config.theme)
            self.splitter = KnowledgeTextSplitter(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
            )
            self.embedder = self._build_embedder(self.config)
            self.retriever = Retriever(
                embedder=self.embedder,
                vector_store=self.vector_store,
                metadata=self.metadata,
                config=self.config,
            )
            if old_backend != self.config.embedding_backend:
                QMessageBox.information(
                    self, "后端已切换",
                    f"嵌入后端已从 {old_backend} 切换至 {self.config.embedding_backend}。\n"
                    "注意：后端切换可能改变向量维度，如检索异常请重建索引。",
                )
            self._check_environment()
            self._refresh_status_panel()

    def _build_embedder(self, config: Config) -> EmbeddingService:
        return EmbeddingService(config=config)

    def _open_logs_dir(self):
        path = self.config.logs_dir
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _score_color(self, score: float) -> str:
        """相似度分数 → 颜色。

        必须跟随当前主题——早前硬编码 ``TOKENS_DARK`` 导致浅色主题下返回深色
        配色，在浅背景上几乎不可读。
        """
        theme = getattr(self, "_resolved_theme", "dark")
        tokens = TOKENS_DARK if theme == "dark" else TOKENS_LIGHT
        return tokens[score_to_color(score)]

    def _reload_workspace_combo(self):
        workspaces = [
            (ws.id, ws.name) for ws in self._workspace_manager.list_workspaces()
        ]
        self.top_nav_bar.set_workspaces(
            workspaces, self._workspace_manager.config.workspaces.current
        )

    def _switch_workspace(self, ws_id: str):
        if not ws_id or ws_id == self._workspace_manager.config.workspaces.current:
            return
        # 切换前先落盘，否则未保存的编辑内容会随工作区重建而丢失
        self.note_workspace.save_current()
        try:
            self._workspace_manager.switch(ws_id)
            self._rebuild_services_for_workspace()
            self._reload_all()
            self.status_bar.show_message(f"已切换到工作区: {ws_id}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "切换失败", str(e))

    def _on_workspace_create(self):
        name, ok = QInputDialog.getText(self, "新建工作区", "工作区名称:")
        if not ok or not name.strip():
            return
        try:
            self._workspace_manager.create(name.strip())
            self._reload_workspace_combo()
            self.status_bar.show_message(f"已创建工作区: {name.strip()}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "创建失败", str(e))

    def _on_workspace_delete(self):
        ws_id = self._workspace_manager.config.workspaces.current
        if not ws_id:
            return
        if ws_id == "default":
            QMessageBox.warning(self, "无法删除", "不能删除默认工作区")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除工作区 {ws_id} 吗？\n数据将归档，可后续恢复。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._workspace_manager.delete(ws_id, archive=True)
            self._reload_workspace_combo()
            self._reload_all()
            self.status_bar.show_message(f"已归档工作区: {ws_id}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "删除失败", str(e))

    def _rebuild_services_for_workspace(self):
        ws = self._workspace_manager.get_current()
        self.vector_store = VectorStore(str(ws.chroma_dir))
        self.metadata = MetadataManager(
            str(ws.sqlite_path), vector_store=self.vector_store
        )
        self.retriever = Retriever(
            embedder=self.embedder,
            vector_store=self.vector_store,
            metadata=self.metadata,
            config=self.config,
        )
        self._rebuild_note_workspace(ws)

    def _rebuild_note_workspace(self, workspace) -> None:
        """为新的工作区重建笔记库（每个工作区拥有独立的 vault 目录）。"""
        self.note_store = NoteStore(
            str(workspace.sqlite_path), workspace.base_dir / "vault", self.metadata
        )

        # 就地替换内容，避免重建整个 NoteWorkspace 丢失当前编辑状态与滚动位置
        self.note_workspace.store = self.note_store
        self.note_workspace.refresh()
        self.note_workspace.editor.set_text("", None)
        self.note_workspace.viewer.clear_view()

    def closeEvent(self, event):
        # 关闭前保存未落盘的笔记编辑
        try:
            self.note_workspace.save_current()
        except Exception:  # noqa: BLE001 —— 关闭阶段不应因保存失败而卡住退出
            logger.warning("关闭前保存笔记失败", exc_info=True)

        if self._ingest_worker and self._ingest_worker.isRunning():
            self._ingest_worker.quit()
            self._ingest_worker.wait(3000)
        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.quit()
            self._search_worker.wait(3000)
        if self._reindex_worker and self._reindex_worker.isRunning():
            self._reindex_worker.quit()
            self._reindex_worker.wait(3000)
        event.accept()
