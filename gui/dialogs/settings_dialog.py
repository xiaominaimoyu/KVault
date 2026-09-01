"""分类标签页化设置对话框。

常规（数据目录 / MCP / 混合检索）、模型（后端 / Ollama / llama.cpp）、
检索（切分 / Top-K / 阈值）三个标签页。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.styles.variables import TOKENS_DARK


class ModelSwitchDialog(QDialog):
    """嵌入模型切换对话框，编排备份→重建→校验→可回滚工作流。"""

    def __init__(self, config, model_manager, rebuild_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("切换嵌入模型")
        self.resize(400, 200)
        self.config = config
        self.model_manager = model_manager
        self.rebuild_fn = rebuild_fn

        layout = QFormLayout(self)
        self.new_model_input = QLineEdit(config.embedding_model)
        layout.addRow("新模型名", self.new_model_input)

        self.hint = QLabel(
            "切换将执行：备份当前索引 → 重建 → 校验 → 可回滚。\n"
            "如重建失败将自动回滚到备份。"
        )
        self.hint.setWordWrap(True)

        layout.addRow("", self.hint)

        self.status_label = QLabel("")
        layout.addRow("状态", self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("开始切换")
        buttons.accepted.connect(self._on_switch)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_switch(self):
        new_model = self.new_model_input.text().strip()
        if not new_model:
            QMessageBox.warning(self, "输入错误", "请输入新模型名")
            return
        self.status_label.setText("正在切换，请稍候...")
        result = self.model_manager.switch_model(new_model, self.rebuild_fn)
        if result.success:
            self.status_label.setText("切换成功")
            QMessageBox.information(
                self, "成功", f"已切换到模型 {new_model}\n备份位于: {result.backup_path}"
            )
            self.accept()
        else:
            msg = f"切换失败: {result.error}"
            if result.rolled_back:
                msg += "\n已自动回滚到备份索引"
            self.status_label.setText("切换失败")
            QMessageBox.critical(self, "失败", msg)


class SettingsDialog(QDialog):
    """分类标签页化设置对话框。

    标签页：常规（数据目录 / MCP / 混合检索）、模型（后端配置）、检索（切分与召回参数）。
    保存逻辑与原单页版一致：写入 config → validate → save。
    """

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(480, 420)
        self.config = config

        self._model_manager = getattr(parent, "_model_manager", None) if parent else None
        self._rebuild_fn = getattr(parent, "_rebuild_all_fn", None) if parent else None

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_general_tab(), "常规")
        self.tabs.addTab(self._build_model_tab(), "模型")
        self.tabs.addTab(self._build_retrieval_tab(), "检索")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---- 标签页构建 ----

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        self._general_tab = tab
        form = QFormLayout(tab)

        self.data_dir = QLineEdit(str(self.config.files_dir.parent))
        self.data_dir.setReadOnly(True)
        form.addRow("数据目录", self.data_dir)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.addItem("浅色", "light")
        theme_idx = self.theme_combo.findData(getattr(self.config, "theme", "system"))
        if theme_idx >= 0:
            self.theme_combo.setCurrentIndex(theme_idx)
        form.addRow("主题", self.theme_combo)

        self.mcp_enabled = QPushButton(
            "已启用" if self.config.mcp_enabled else "已禁用"
        )
        self.mcp_enabled.setCheckable(True)
        self.mcp_enabled.setChecked(self.config.mcp_enabled)
        self.mcp_enabled.toggled.connect(self._on_mcp_toggled)
        form.addRow("MCP 服务", self.mcp_enabled)

        self.hybrid_enabled = QPushButton(
            "已启用" if self.config.hybrid_search.enabled else "已禁用"
        )
        self.hybrid_enabled.setCheckable(True)
        self.hybrid_enabled.setChecked(self.config.hybrid_search.enabled)
        self.hybrid_enabled.toggled.connect(self._on_hybrid_toggled)
        form.addRow("混合检索", self.hybrid_enabled)

        return tab

    def _build_model_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Ollama", "ollama")
        self.backend_combo.addItem("llama.cpp", "llama_cpp")
        backend_idx = self.backend_combo.findData(self.config.embedding_backend)
        if backend_idx >= 0:
            self.backend_combo.setCurrentIndex(backend_idx)
        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        form.addRow("嵌入后端", self.backend_combo)

        self.config_stack = QStackedWidget()

        ollama_panel = QWidget()
        ollama_layout = QFormLayout(ollama_panel)
        self.ollama_url = QLineEdit(self.config.ollama_base_url)
        ollama_layout.addRow("Base URL", self.ollama_url)
        self.model_name = QLineEdit(self.config.embedding_model)
        ollama_layout.addRow("模型名", self.model_name)
        self.config_stack.addWidget(ollama_panel)

        llama_cpp_panel = QWidget()
        llama_cpp_layout = QFormLayout(llama_cpp_panel)
        gguf_layout = QHBoxLayout()
        self.gguf_path = QLineEdit(self.config.llama_cpp.model_path)
        gguf_layout.addWidget(self.gguf_path)
        self.gguf_browse_btn = QPushButton("浏览...")
        self.gguf_browse_btn.clicked.connect(self._on_gguf_browse)
        gguf_layout.addWidget(self.gguf_browse_btn)
        llama_cpp_layout.addRow("GGUF 模型", gguf_layout)
        self.n_gpu_layers = QSpinBox()
        self.n_gpu_layers.setRange(0, 100)
        self.n_gpu_layers.setValue(self.config.llama_cpp.n_gpu_layers)
        llama_cpp_layout.addRow("GPU 层数", self.n_gpu_layers)
        self.n_ctx = QSpinBox()
        self.n_ctx.setRange(512, 65536)
        self.n_ctx.setValue(self.config.llama_cpp.n_ctx)
        llama_cpp_layout.addRow("上下文长度", self.n_ctx)
        self.config_stack.addWidget(llama_cpp_panel)

        self.config_stack.setCurrentIndex(self.backend_combo.currentIndex())
        form.addRow(self.config_stack)

        self.backend_status_label = QLabel()
        form.addRow("后端状态", self.backend_status_label)

        if self._model_manager and self._rebuild_fn:
            self.switch_model_btn = QPushButton("切换模型...")
            self.switch_model_btn.clicked.connect(self._on_switch_model)
            form.addRow("模型管理", self.switch_model_btn)

        return tab

    def _build_retrieval_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)

        self.chunk_size = QSpinBox()
        self.chunk_size.setRange(100, 4000)
        self.chunk_size.setValue(self.config.chunk_size)
        form.addRow("Chunk Size", self.chunk_size)

        self.chunk_overlap = QSpinBox()
        self.chunk_overlap.setRange(0, 1000)
        self.chunk_overlap.setValue(self.config.chunk_overlap)
        form.addRow("Chunk Overlap", self.chunk_overlap)

        self.chunk_hint = QLabel(
            "提示：切分参数仅对新增索引起效，存量文档需重建索引后生效。"
        )
        self.chunk_hint.setWordWrap(True)
        form.addRow("", self.chunk_hint)

        self.top_k = QSpinBox()
        self.top_k.setRange(1, 50)
        self.top_k.setValue(self.config.top_k)
        form.addRow("默认 Top-K", self.top_k)

        self.threshold = QLineEdit(str(self.config.similarity_threshold))
        form.addRow("相似度阈值", self.threshold)

        return tab

    # ---- 事件处理 ----

    def _on_switch_model(self):
        dialog = ModelSwitchDialog(
            self.config, self._model_manager, self._rebuild_fn, parent=self
        )
        dialog.exec()

    def _on_gguf_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 GGUF 模型", "", "GGUF Models (*.gguf);;All Files (*.*)"
        )
        if path:
            self.gguf_path.setText(path)

    def _on_backend_changed(self, index: int):
        self.config_stack.setCurrentIndex(index)
        backend = self.backend_combo.itemData(index)
        if backend == "llama_cpp":
            from core.embedding_backends.llama_cpp_backend import LlamaCppBackend

            tmp = LlamaCppBackend(model_path=self.gguf_path.text().strip())
            if tmp.is_available() and tmp.is_model_available():
                self.backend_status_label.setText("✓ llama.cpp 后端就绪")
                self.backend_status_label.setStyleSheet(
                    f"color: {TOKENS_DARK['status-success']};"
                )
            elif not tmp.is_available():
                self.backend_status_label.setText("✗ 未安装 llama-cpp-python")
                self.backend_status_label.setStyleSheet(
                    f"color: {TOKENS_DARK['status-error']};"
                )
            else:
                self.backend_status_label.setText("✗ GGUF 模型文件不存在")
                self.backend_status_label.setStyleSheet(
                    f"color: {TOKENS_DARK['status-error']};"
                )
        else:
            self.backend_status_label.setText("Ollama 后端（需启动 Ollama 服务）")
            self.backend_status_label.setStyleSheet(
                f"color: {TOKENS_DARK['fg-muted']};"
            )

    def _on_mcp_toggled(self, checked: bool):
        self.mcp_enabled.setText("已启用" if checked else "已禁用")

    def _on_hybrid_toggled(self, checked: bool):
        self.hybrid_enabled.setText("已启用" if checked else "已禁用")

    def _on_save(self):
        try:
            threshold = float(self.threshold.text())
        except ValueError as e:
            QMessageBox.warning(
                self, "Input Error", f"Invalid similarity threshold: {e}"
            )
            return

        self.config.ollama_base_url = self.ollama_url.text().strip()
        self.config.embedding_model = self.model_name.text().strip()
        self.config.embedding_backend = self.backend_combo.currentData()
        if self.config.embedding_backend == "llama_cpp":
            self.config.llama_cpp.model_path = self.gguf_path.text().strip()
            self.config.llama_cpp.n_gpu_layers = self.n_gpu_layers.value()
            self.config.llama_cpp.n_ctx = self.n_ctx.value()
        self.config.chunk_size = self.chunk_size.value()
        self.config.chunk_overlap = self.chunk_overlap.value()
        self.config.top_k = self.top_k.value()
        self.config.similarity_threshold = threshold
        self.config.mcp_enabled = self.mcp_enabled.isChecked()
        self.config.hybrid_search.enabled = self.hybrid_enabled.isChecked()
        self.config.theme = self.theme_combo.currentData()

        errors = self.config.validate()
        if errors:
            QMessageBox.warning(
                self,
                "配置校验失败",
                "以下配置项存在问题，已阻止保存：\n\n• " + "\n• ".join(errors),
            )
            return

        self.config.save()
        self.accept()
