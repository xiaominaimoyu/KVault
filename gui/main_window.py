import html
import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.config import Config
from core.document_parser import DocumentParser
from core.embedding_service import EmbeddingService
from core.ingest import ingest_document
from core.metadata_manager import DEFAULT_PARTITION_ID, MetadataManager
from core.retriever import Retriever
from core.text_splitter import KnowledgeTextSplitter
from core.vector_store import VectorStore
from gui.workers.ingest_worker import IngestWorker
from gui.workers.search_worker import SearchWorker

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    "indexed": "#2ecc71",
    "indexing": "#f1c40f",
    "pending": "#95a5a6",
    "failed": "#e74c3c",
}

_STATUS_LABELS = {
    "indexed": "已索引",
    "indexing": "索引中",
    "pending": "待处理",
    "failed": "失败",
}


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    value = float(size)
    for unit in ["KB", "MB", "GB"]:
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value / 1024:.1f} TB"


def _format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


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


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(420, 360)
        self.config = config

        layout = QFormLayout(self)

        self.data_dir = QLineEdit(str(config.files_dir.parent))
        self.data_dir.setReadOnly(True)
        layout.addRow("数据目录", self.data_dir)

        self.ollama_url = QLineEdit(config.ollama_base_url)
        layout.addRow("Ollama Base URL", self.ollama_url)

        self.model_name = QLineEdit(config.embedding_model)
        layout.addRow("Embedding 模型", self.model_name)

        self.chunk_size = QSpinBox()
        self.chunk_size.setRange(100, 4000)
        self.chunk_size.setValue(config.chunk_size)
        layout.addRow("Chunk Size", self.chunk_size)

        self.chunk_overlap = QSpinBox()
        self.chunk_overlap.setRange(0, 1000)
        self.chunk_overlap.setValue(config.chunk_overlap)
        layout.addRow("Chunk Overlap", self.chunk_overlap)

        self.top_k = QSpinBox()
        self.top_k.setRange(1, 50)
        self.top_k.setValue(config.top_k)
        layout.addRow("默认 Top-K", self.top_k)

        self.threshold = QLineEdit(str(config.similarity_threshold))
        layout.addRow("相似度阈值", self.threshold)

        self.mcp_enabled = QPushButton("已启用" if config.mcp_enabled else "已禁用")
        self.mcp_enabled.setCheckable(True)
        self.mcp_enabled.setChecked(config.mcp_enabled)
        self.mcp_enabled.toggled.connect(self._on_mcp_toggled)
        layout.addRow("MCP 服务", self.mcp_enabled)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_mcp_toggled(self, checked: bool):
        self.mcp_enabled.setText("已启用" if checked else "已禁用")

    def _on_save(self):
        try:
            threshold = float(self.threshold.text())
            if not 0 <= threshold <= 1:
                raise ValueError("threshold must be between 0 and 1")
        except ValueError as e:
            QMessageBox.warning(self, "Input Error", f"Invalid similarity threshold: {e}")
            return

        chunk_size = self.chunk_size.value()
        chunk_overlap = self.chunk_overlap.value()
        if chunk_overlap >= chunk_size:
            QMessageBox.warning(
                self,
                "Input Error",
                "Chunk overlap must be smaller than chunk size",
            )
            return

        self.config.ollama_base_url = self.ollama_url.text().strip()
        self.config.embedding_model = self.model_name.text().strip()
        self.config.chunk_size = chunk_size
        self.config.chunk_overlap = chunk_overlap
        self.config.top_k = self.top_k.value()
        self.config.similarity_threshold = threshold
        self.config.mcp_enabled = self.mcp_enabled.isChecked()
        self.config.save()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.parser = DocumentParser()
        self.splitter = KnowledgeTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
        )
        self.vector_store = VectorStore(str(config.chroma_dir))
        self.metadata = MetadataManager(str(config.sqlite_path), vector_store=self.vector_store)
        self.embedder = EmbeddingService(
            model=config.embedding_model,
            base_url=config.ollama_base_url,
            batch_size=config.embedding_batch_size,
        )

        self._current_doc_id: str | None = None
        self._current_partition_id: str | None = None
        self._current_tag_id: str | None = None
        self._ingest_worker: IngestWorker | None = None
        self._search_worker: SearchWorker | None = None
        self._reindex_worker: ReindexWorker | None = None
        self._all_documents: list = []
        self._current_filter: str = ""

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

        self._reload_all()
        self._check_environment()

    def _setup_toolbar(self):
        toolbar = self.addToolBar("工具栏")
        self.import_btn = QPushButton("导入文档")
        self.import_btn.clicked.connect(self._on_import)
        toolbar.addWidget(self.import_btn)

        toolbar.addSeparator()
        self.global_search = QLineEdit()
        self.global_search.setPlaceholderText("全局搜索：文件名 / 扩展名 / 分区 / 标签")
        self.global_search.setMinimumWidth(280)
        self.global_search.textChanged.connect(self._on_global_search_changed)
        toolbar.addWidget(self.global_search)

        toolbar.addSeparator()
        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(self._open_settings)
        toolbar.addWidget(settings_btn)

        logs_btn = QPushButton("日志")
        logs_btn.clicked.connect(self._open_logs_dir)
        toolbar.addWidget(logs_btn)

    def _setup_central_layout(self):
        splitter = QSplitter(Qt.Horizontal)

        self.nav_panel = self._build_nav_panel()
        self.nav_panel.setMinimumWidth(220)
        self.nav_panel.setMaximumWidth(320)

        self.doc_table = QTableWidget(0, 7)
        self.doc_table.setHorizontalHeaderLabels(
            ["文件名", "格式", "大小", "状态", "块数", "导入时间", "doc_id"]
        )
        self.doc_table.hideColumn(6)
        self.doc_table.horizontalHeader().setStretchLastSection(False)
        self.doc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.doc_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.doc_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.doc_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.doc_table.itemSelectionChanged.connect(self._on_document_selected)
        self.doc_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.doc_table.customContextMenuRequested.connect(self._show_document_context_menu)

        self.preview = QTextBrowser()
        self.preview.setPlaceholderText("选择文档以预览内容")

        self.retrieval_panel = self._build_retrieval_panel()

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self.preview)
        right_splitter.addWidget(self.retrieval_panel)
        right_splitter.setSizes([420, 320])

        splitter.addWidget(self.nav_panel)
        splitter.addWidget(self.doc_table)
        splitter.addWidget(right_splitter)
        splitter.setSizes([220, 500, 680])

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setCentralWidget(container)

    def _build_nav_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Partition tree
        layout.addWidget(QLabel("<b>分区</b>"))
        self.partition_tree = QTreeWidget()
        self.partition_tree.setHeaderHidden(True)
        self.partition_tree.itemClicked.connect(self._on_partition_selected)
        self.partition_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.partition_tree.customContextMenuRequested.connect(
            self._show_partition_context_menu
        )
        layout.addWidget(self.partition_tree)

        # Tag cloud
        layout.addWidget(QLabel("<b>标签</b>"))
        self.tag_list = QListWidget()
        self.tag_list.itemClicked.connect(self._on_tag_selected)
        layout.addWidget(self.tag_list)

        # Status panel
        layout.addWidget(QLabel("<b>向量库状态</b>"))
        self.status_panel = QTextBrowser()
        self.status_panel.setMaximumHeight(140)
        layout.addWidget(self.status_panel)

        refresh_btn = QPushButton("刷新状态")
        refresh_btn.clicked.connect(self._refresh_status_panel)
        layout.addWidget(refresh_btn)

        return panel

    def _build_retrieval_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        header = QLabel("<b>语义检索测试</b>")
        layout.addWidget(header)

        input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入自然语言查询...")
        self.search_input.returnPressed.connect(self._on_search)
        self.search_btn = QPushButton("检索")
        self.search_btn.clicked.connect(self._on_search)
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 20)
        self.top_k_spin.setValue(self.config.top_k)
        self.top_k_spin.setPrefix("Top-")
        input_layout.addWidget(self.search_input, 1)
        input_layout.addWidget(self.top_k_spin)
        input_layout.addWidget(self.search_btn)
        layout.addLayout(input_layout)

        self.result_list = QListWidget()
        self.result_list.setSpacing(4)
        self.result_list.itemClicked.connect(self._on_result_clicked)
        layout.addWidget(self.result_list)

        return panel

    def _setup_status_bar(self):
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().showMessage("本地运行 · 就绪")

    def _check_environment(self):
        if not self.embedder.is_available():
            self.statusBar().showMessage("Ollama 服务未启动，请检查设置")
            logger.warning("Ollama 服务不可访问")
        elif not self.embedder.is_model_available():
            self.statusBar().showMessage(f"模型未就绪: {self.config.embedding_model}")
            logger.warning("模型不可用: %s", self.config.embedding_model)
        else:
            self.statusBar().showMessage("本地运行 · 就绪")

    def _reload_all(self):
        self._reload_nav_panel()
        self._reload_document_list()
        self._refresh_status_panel()

    def _reload_nav_panel(self):
        self.partition_tree.clear()
        all_item = QTreeWidgetItem(self.partition_tree)
        all_item.setText(0, "所有文档")
        stats = self.metadata.get_stats()
        all_item.setText(0, f"所有文档 ({stats.get('total_docs', 0)})")
        all_item.setData(0, Qt.UserRole, "")
        all_item.setSelected(self._current_partition_id is None and self._current_tag_id is None)

        partitions = self.metadata.list_partitions_with_counts()
        for p in partitions:
            item = QTreeWidgetItem(self.partition_tree)
            item.setText(0, f"{p['name']} ({p['doc_count']})")
            item.setData(0, Qt.UserRole, p["id"])
            item.setSelected(p["id"] == self._current_partition_id)

        self.partition_tree.expandAll()

        self.tag_list.clear()
        all_tags = QListWidgetItem("全部标签")
        all_tags.setData(Qt.UserRole, "")
        self.tag_list.addItem(all_tags)
        if self._current_tag_id is None:
            self.tag_list.setCurrentItem(all_tags)

        tags = self.metadata.list_tags_with_counts()
        for t in tags:
            item = QListWidgetItem(f"{t['name']} ({t['doc_count']})")
            item.setData(Qt.UserRole, t["id"])
            self.tag_list.addItem(item)
            if t["id"] == self._current_tag_id:
                self.tag_list.setCurrentItem(item)

    def _on_partition_selected(self, item: QTreeWidgetItem):
        self._current_partition_id = item.data(0, Qt.UserRole) or None
        self._current_tag_id = None
        self.tag_list.clearSelection()
        self._reload_document_list()

    def _on_tag_selected(self, item: QListWidgetItem):
        self._current_tag_id = item.data(Qt.UserRole) or None
        self._current_partition_id = None
        self.partition_tree.clearSelection()
        self._reload_document_list()

    def _show_partition_context_menu(self, position):
        item = self.partition_tree.itemAt(position)
        partition_id = item.data(0, Qt.UserRole) if item else ""

        menu = QMenu(self)
        add_action = QAction("新建分区", self)
        add_action.triggered.connect(self._create_partition)
        menu.addAction(add_action)

        if partition_id and partition_id != DEFAULT_PARTITION_ID:
            rename_action = QAction("重命名分区", self)
            rename_action.triggered.connect(lambda: self._rename_partition(partition_id))
            menu.addAction(rename_action)

            delete_action = QAction("删除分区", self)
            delete_action.triggered.connect(lambda: self._delete_partition(partition_id))
            menu.addAction(delete_action)

        menu.exec(self.partition_tree.mapToGlobal(position))

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
        lines = [
            f"总文档数: {stats.get('total_docs', 0)}",
            f"已索引: {stats.get('indexed_docs', 0)}",
            f"失败: {stats.get('failed_docs', 0)}",
            f"总块数: {stats.get('total_chunks', 0)}",
            f"向量数: {chroma_count}",
            f"模型: {self.config.embedding_model.split('/')[-1]}",
        ]
        self.status_panel.setHtml("<br>".join(_esc(line) for line in lines))

    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要导入的文档",
            "",
            "支持的文档 (*.txt *.md *.pdf *.docx *.xlsx *.pptx)"
        )
        if not paths:
            return

        partition_id = self._current_partition_id or DEFAULT_PARTITION_ID

        self.import_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self._ingest_worker = IngestWorker(
            file_paths=paths,
            ingest_fn=lambda p: self._ingest_with_partition(p, partition_id),
        )
        self._ingest_worker.progress.connect(self._on_ingest_progress)
        self._ingest_worker.file_done.connect(self._on_ingest_file_done)
        self._ingest_worker.finished_all.connect(self._on_ingest_finished)
        self._ingest_worker.start()

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
        self.statusBar().showMessage(f"正在索引: {file_name} ({percent}%)")

    def _on_ingest_file_done(self, doc_id: str, success: bool, file_name: str, error: str):
        if success:
            self.statusBar().showMessage(f"导入完成: {file_name}")
            logger.info("导入成功: %s -> %s", file_name, doc_id)
        else:
            QMessageBox.critical(self, "导入失败", f"{file_name}\n{error}")
            self.statusBar().showMessage(f"导入失败: {file_name}")
            logger.error("导入失败: %s - %s", file_name, error)
        self._reload_all()

    def _on_ingest_finished(self, success_count: int, fail_count: int):
        self.import_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        msg = f"批量导入完成: 成功 {success_count} 个"
        if fail_count:
            msg += f", 失败 {fail_count} 个"
        self.statusBar().showMessage(msg)
        self._check_environment()

    def _reload_document_list(self):
        tag_ids = [self._current_tag_id] if self._current_tag_id else None
        self._all_documents = self.metadata.list_documents(
            partition_id=self._current_partition_id,
            tag_ids=tag_ids,
        )
        self._apply_document_filter()

    def _apply_document_filter(self):
        self.doc_table.setRowCount(0)
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

        for doc in docs:
            row = self.doc_table.rowCount()
            self.doc_table.insertRow(row)
            self.doc_table.setItem(row, 0, QTableWidgetItem(doc.file_name))
            self.doc_table.setItem(row, 1, QTableWidgetItem(doc.file_ext.upper()))
            self.doc_table.setItem(row, 2, QTableWidgetItem(_format_size(doc.file_size)))

            status_item = QTableWidgetItem(_STATUS_LABELS.get(doc.status, doc.status))
            color = _STATUS_COLORS.get(doc.status, "#95a5a6")
            status_item.setForeground(self._color_brush(color))
            self.doc_table.setItem(row, 3, status_item)

            chunk_item = QTableWidgetItem(str(doc.chunk_count))
            chunk_item.setTextAlignment(Qt.AlignCenter)
            self.doc_table.setItem(row, 4, chunk_item)

            self.doc_table.setItem(row, 5, QTableWidgetItem(_format_time(doc.created_at)))

            doc_id_item = QTableWidgetItem(doc.id)
            self.doc_table.setItem(row, 6, doc_id_item)

    def _on_document_selected(self):
        selected = self.doc_table.selectedItems()
        if not selected:
            self._current_doc_id = None
            self.preview.clear()
            return

        row = selected[0].row()
        doc_id = self.doc_table.item(row, 6).text()
        self._current_doc_id = doc_id
        self._load_preview(doc_id)

    def _load_preview(self, doc_id: str):
        doc = self.metadata.get_document(doc_id)
        if doc is None:
            self.preview.setText("文档不存在")
            return

        lines = [
            f"<h2>{_esc(doc.file_name)}</h2>",
            f"<p><b>格式:</b> {_esc(doc.file_ext.upper())} &nbsp; "
            f"<b>大小:</b> {_format_size(doc.file_size)} &nbsp; "
            f"<b>状态:</b> {_esc(_STATUS_LABELS.get(doc.status, doc.status))} &nbsp; "
            f"<b>块数:</b> {doc.chunk_count}</p>",
            f"<p><b>分区:</b> {_esc(doc.partition_name or '未分类')} &nbsp; "
            f"<b>标签:</b> {_esc(', '.join(t['name'] for t in self.metadata.get_document_tags(doc.id)))}</p>",
            f"<p><b>存储路径:</b> {_esc(doc.stored_path)}</p>",
            "<hr>",
        ]

        if doc.status == "indexed" and Path(doc.stored_path).exists():
            try:
                parsed = self.parser.parse(doc.stored_path)
                lines.append("<h3>内容预览</h3>")
                content = _esc(parsed.content).replace("\n", "<br>")
                lines.append(f"<p>{content[:4000]}</p>")

                chunks = self.metadata.get_document_chunks(doc_id)
                if chunks:
                    lines.append("<h3>文本块概览</h3>")
                    for ch in chunks:
                        idx = ch["chunk_index"]
                        preview = _esc(ch["content_preview"])
                        lines.append(
                            f"<p><b>块 {idx + 1}:</b> {preview}...</p>"
                        )
            except Exception as e:
                lines.append(f"<p style='color:red'>预览加载失败: {_esc(e)}</p>")
        elif doc.status == "failed":
            lines.append(
                f"<p style='color:red'><b>索引失败:</b> {_esc(doc.error_message or '未知错误')}</p>"
            )
        else:
            lines.append("<p>文档尚未完成索引，暂无预览。</p>")

        self.preview.setHtml("\n".join(lines))

    def _on_global_search_changed(self, text: str):
        self._current_filter = text
        self._apply_document_filter()

    def _on_search(self):
        query = self.search_input.text().strip()
        if not query:
            self.result_list.clear()
            return

        filters = self._build_search_filters()
        if filters and filters.get("_empty"):
            self.result_list.clear()
            self.result_list.addItem("未找到相关结果")
            self.statusBar().showMessage("检索完成：无结果")
            return

        self.search_btn.setEnabled(False)
        self.statusBar().showMessage("正在检索...")

        self._search_worker = SearchWorker(
            retriever=self.retriever,
            query=query,
            top_k=self.top_k_spin.value(),
            filters=filters,
        )
        self._search_worker.results.connect(self._on_search_results)
        self._search_worker.error.connect(self._on_search_error)
        self._search_worker.finished.connect(
            lambda: self.search_btn.setEnabled(True)
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
        self.result_list.clear()
        if not results:
            self.result_list.addItem("未找到相关结果")
            self.statusBar().showMessage("检索完成：无结果")
            return

        for result in results:
            color = self._score_color(result.score)
            item = QListWidgetItem()
            item.setText(
                f"{result.document_name} · 块 {result.chunk_index + 1} · "
                f"相似度 {result.score:.2f}"
            )
            item.setToolTip(result.content[:300])
            item.setData(Qt.UserRole, result)
            item.setForeground(self._color_brush(color))
            self.result_list.addItem(item)

        self.statusBar().showMessage(f"检索完成：{len(results)} 条结果")

    def _on_search_error(self, error: str):
        self.result_list.clear()
        self.result_list.addItem(f"检索失败: {error}")
        self.statusBar().showMessage("检索失败")
        logger.error("检索失败: %s", error)

    def _on_result_clicked(self, item: QListWidgetItem):
        result = item.data(Qt.UserRole)
        if result is None:
            return

        document_id = result.document_id
        for row in range(self.doc_table.rowCount()):
            if self.doc_table.item(row, 6).text() == document_id:
                self.doc_table.selectRow(row)
                self._load_preview_with_chunk(document_id, result.chunk_index)
                break

    def _load_preview_with_chunk(self, doc_id: str, chunk_index: int):
        self._load_preview(doc_id)
        chunks = self.metadata.get_document_chunks(doc_id)
        if 0 <= chunk_index < len(chunks):
            preview = _esc(chunks[chunk_index]["content_preview"])
            self.preview.append(
                f"<hr><h3>检索命中块 {chunk_index + 1}</h3>"
                f"<p>{preview}</p>"
            )

    def _show_document_context_menu(self, position):
        rows = set(idx.row() for idx in self.doc_table.selectedIndexes())
        if not rows:
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

        if len(rows) == 1:
            row = list(rows)[0]
            doc_id = self.doc_table.item(row, 6).text()
            doc = self.metadata.get_document(doc_id)
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

        menu.exec(self.doc_table.mapToGlobal(position))

    def _get_selected_doc_ids(self) -> list[str]:
        rows = set(idx.row() for idx in self.doc_table.selectedIndexes())
        return [self.doc_table.item(row, 6).text() for row in rows]

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

        self.import_btn.setEnabled(False)
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
            self.statusBar().showMessage(f"重新索引完成: {original_id}")
            logger.info("重新索引成功: %s -> %s", original_id, doc_id)
        else:
            QMessageBox.critical(self, "重新索引失败", f"{original_id}\n{error}")
            self.statusBar().showMessage(f"重新索引失败: {original_id}")
            logger.error("重新索引失败: %s - %s", original_id, error)
        self._reload_all()

    def _on_reindex_finished(self, success_count: int, fail_count: int):
        self.import_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        msg = f"重新索引完成: 成功 {success_count} 个"
        if fail_count:
            msg += f", 失败 {fail_count} 个"
        self.statusBar().showMessage(msg)

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

        self.statusBar().showMessage(f"已删除 {deleted} 个文档")
        self._current_doc_id = None
        self._reload_all()

    def _open_settings(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec() == QDialog.Accepted:
            self.splitter = KnowledgeTextSplitter(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
            )
            self.embedder = EmbeddingService(
                model=self.config.embedding_model,
                base_url=self.config.ollama_base_url,
                batch_size=self.config.embedding_batch_size,
            )
            self.retriever = Retriever(
                embedder=self.embedder,
                vector_store=self.vector_store,
                metadata=self.metadata,
                config=self.config,
            )
            self._check_environment()
            self._refresh_status_panel()

    def _open_logs_dir(self):
        path = self.config.logs_dir
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _score_color(self, score: float) -> str:
        if score >= 0.8:
            return "#27ae60"
        if score >= 0.5:
            return "#f39c12"
        return "#e74c3c"

    def _color_brush(self, color: str):
        return QBrush(QColor(color))

    def closeEvent(self, event):
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
