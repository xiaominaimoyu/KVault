"""分类标签页化设置对话框。

对应设计文档 §4.1：

- 窗口 560 x 480px
- 五个标签页：常规 / 检索 / 模型 / MCP / 外观
- 表单项 16px 间距、标签右对齐
- 保存按钮为主按钮
- 切分参数变更提示为 ``--accent-warm-dim`` 背景信息条
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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

from gui.dialogs.model_switch_dialog import ModelSwitchDialog
from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

#: 设计文档 4.1 规定的标签页顺序
TAB_ORDER = ("常规", "检索", "模型", "MCP", "外观")


def _form(tab: QWidget) -> QFormLayout:
    """构造符合规范的表单：16px 间距、标签右对齐。"""
    form = QFormLayout(tab)
    form.setSpacing(16)
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
    return form


class SettingsDialog(QDialog):
    """设置对话框。"""

    def __init__(self, config, parent=None, theme: str = "dark"):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setObjectName("SettingsDialog")
        self.resize(560, 480)
        self.config = config
        self._theme = theme

        self._model_manager = getattr(parent, "_model_manager", None) if parent else None
        self._rebuild_fn = getattr(parent, "_rebuild_all_fn", None) if parent else None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._build_tabs()
        self._build_buttons(layout)

    def _tokens(self) -> dict:
        return TOKENS_DARK if self._theme == "dark" else TOKENS_LIGHT

    # ---------------------------------------------------------------- 标签页

    def _build_tabs(self) -> None:
        builders = {
            "常规": self._build_general_tab,
            "检索": self._build_retrieval_tab,
            "模型": self._build_model_tab,
            "MCP": self._build_mcp_tab,
            "外观": self._build_appearance_tab,
        }
        for name in TAB_ORDER:
            self.tabs.addTab(builders[name](), name)

    def _build_general_tab(self) -> QWidget:
        """常规：数据目录 + 混合检索。"""
        tab = QWidget()
        form = _form(tab)

        self.data_dir = QLineEdit(str(self.config.files_dir.parent))
        self.data_dir.setReadOnly(True)
        form.addRow("数据目录", self.data_dir)

        self.hybrid_enabled = QPushButton(
            "已启用" if self.config.hybrid_search.enabled else "已禁用"
        )
        self.hybrid_enabled.setCheckable(True)
        self.hybrid_enabled.setChecked(self.config.hybrid_search.enabled)
        self.hybrid_enabled.toggled.connect(self._on_hybrid_toggled)
        form.addRow("混合检索", self.hybrid_enabled)

        return tab

    def _build_retrieval_tab(self) -> QWidget:
        """检索：切分参数 + 召回参数。"""
        tab = QWidget()
        form = _form(tab)

        self.chunk_size = QSpinBox()
        self.chunk_size.setRange(100, 4000)
        self.chunk_size.setValue(self.config.chunk_size)
        form.addRow("Chunk Size", self.chunk_size)

        self.chunk_overlap = QSpinBox()
        self.chunk_overlap.setRange(0, 1000)
        self.chunk_overlap.setValue(self.config.chunk_overlap)
        form.addRow("Chunk Overlap", self.chunk_overlap)

        # §4.1 切分参数变更提示：--accent-warm-dim 背景信息条
        self.chunk_hint = QLabel(
            "提示：切分参数仅对新增索引起效，存量文档需重建索引后生效。"
        )
        self.chunk_hint.setWordWrap(True)
        self.chunk_hint.setObjectName("SettingsHintBar")
        form.addRow("", self.chunk_hint)

        self.top_k = QSpinBox()
        self.top_k.setRange(1, 50)
        self.top_k.setValue(self.config.top_k)
        form.addRow("默认 Top-K", self.top_k)

        self.threshold = QLineEdit(str(self.config.similarity_threshold))
        form.addRow("相似度阈值", self.threshold)

        return tab

    def _build_model_tab(self) -> QWidget:
        """模型：嵌入后端 + 模型路径。"""
        tab = QWidget()
        form = _form(tab)

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
        ollama_form = _form(ollama_panel)
        self.ollama_url = QLineEdit(self.config.ollama_base_url)
        ollama_form.addRow("Base URL", self.ollama_url)
        self.model_name = QLineEdit(self.config.embedding_model)
        ollama_form.addRow("模型名", self.model_name)
        self.config_stack.addWidget(ollama_panel)

        llama_cpp_panel = QWidget()
        llama_form = _form(llama_cpp_panel)
        gguf_layout = QHBoxLayout()
        self.gguf_path = QLineEdit(self.config.llama_cpp.model_path)
        gguf_layout.addWidget(self.gguf_path)
        self.gguf_browse_btn = QPushButton("浏览...")
        self.gguf_browse_btn.setProperty("btnType", "secondary")
        self.gguf_browse_btn.clicked.connect(self._on_gguf_browse)
        gguf_layout.addWidget(self.gguf_browse_btn)
        llama_form.addRow("GGUF 模型", gguf_layout)

        self.n_gpu_layers = QSpinBox()
        self.n_gpu_layers.setRange(0, 100)
        self.n_gpu_layers.setValue(self.config.llama_cpp.n_gpu_layers)
        llama_form.addRow("GPU 层数", self.n_gpu_layers)

        self.n_ctx = QSpinBox()
        self.n_ctx.setRange(512, 65536)
        self.n_ctx.setValue(self.config.llama_cpp.n_ctx)
        llama_form.addRow("上下文长度", self.n_ctx)
        self.config_stack.addWidget(llama_cpp_panel)

        self.config_stack.setCurrentIndex(self.backend_combo.currentIndex())
        form.addRow(self.config_stack)

        self.backend_status_label = QLabel()
        self.backend_status_label.setWordWrap(True)
        form.addRow("后端状态", self.backend_status_label)

        if self._model_manager and self._rebuild_fn:
            self.switch_model_btn = QPushButton("切换模型...")
            self.switch_model_btn.setProperty("btnType", "secondary")
            self.switch_model_btn.clicked.connect(self._on_switch_model)
            form.addRow("模型管理", self.switch_model_btn)

        return tab

    def _build_mcp_tab(self) -> QWidget:
        """MCP：外部接口开关。"""
        tab = QWidget()
        form = _form(tab)

        self.mcp_enabled = QPushButton(
            "已启用" if self.config.mcp_enabled else "已禁用"
        )
        self.mcp_enabled.setCheckable(True)
        self.mcp_enabled.setChecked(self.config.mcp_enabled)
        self.mcp_enabled.toggled.connect(self._on_mcp_toggled)
        form.addRow("MCP 服务", self.mcp_enabled)

        note = QLabel(
            "启用后可通过 `python -m mcp_server` 以 stdio 方式暴露知识库检索能力。\n"
            "笔记写入工具需额外设置环境变量 KVAULT_ALLOW_WRITE=1，默认只读。"
        )
        note.setWordWrap(True)
        note.setObjectName("SettingsHintBar")
        form.addRow("", note)

        return tab

    def _build_appearance_tab(self) -> QWidget:
        """外观：主题 + 动效。"""
        tab = QWidget()
        form = _form(tab)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("跟随系统", "system")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.addItem("浅色", "light")
        theme_idx = self.theme_combo.findData(getattr(self.config, "theme", "system"))
        if theme_idx >= 0:
            self.theme_combo.setCurrentIndex(theme_idx)
        form.addRow("主题", self.theme_combo)

        # §6.1 reduce_motion：对应系统级 prefers-reduced-motion
        self.reduce_motion = QPushButton(
            "已关闭动效" if getattr(self.config, "reduce_motion", False) else "已启用动效"
        )
        self.reduce_motion.setCheckable(True)
        self.reduce_motion.setChecked(not getattr(self.config, "reduce_motion", False))
        self.reduce_motion.toggled.connect(self._on_reduce_motion_toggled)
        form.addRow("界面动效", self.reduce_motion)

        return tab

    # ---------------------------------------------------------------- 按钮

    def _build_buttons(self, layout: QVBoxLayout) -> None:
        button_row = QHBoxLayout()
        button_row.addStretch()

        save_btn = QPushButton("保存")
        save_btn.setProperty("btnType", "primary")
        save_btn.clicked.connect(self._on_save)

        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("btnType", "secondary")
        cancel_btn.clicked.connect(self.reject)

        button_row.addWidget(save_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

    # ---------------------------------------------------------------- 事件

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
        tokens = self._tokens()
        backend = self.backend_combo.itemData(index)

        if backend == "llama_cpp":
            from core.embedding_backends.llama_cpp_backend import LlamaCppBackend

            tmp = LlamaCppBackend(model_path=self.gguf_path.text().strip())
            if tmp.is_available() and tmp.is_model_available():
                self.backend_status_label.setText("✓ llama.cpp 后端就绪")
                self.backend_status_label.setStyleSheet(
                    f"color: {tokens['status-success']};"
                )
            elif not tmp.is_available():
                self.backend_status_label.setText("✗ 未安装 llama-cpp-python")
                self.backend_status_label.setStyleSheet(
                    f"color: {tokens['status-error']};"
                )
            else:
                self.backend_status_label.setText("✗ GGUF 模型文件不存在")
                self.backend_status_label.setStyleSheet(
                    f"color: {tokens['status-error']};"
                )
        else:
            self.backend_status_label.setText("Ollama 后端（需启动 Ollama 服务）")
            self.backend_status_label.setStyleSheet(f"color: {tokens['fg-muted']};")

    def _on_mcp_toggled(self, checked: bool):
        self.mcp_enabled.setText("已启用" if checked else "已禁用")

    def _on_hybrid_toggled(self, checked: bool):
        self.hybrid_enabled.setText("已启用" if checked else "已禁用")

    def _on_reduce_motion_toggled(self, checked: bool):
        self.reduce_motion.setText("已启用动效" if checked else "已关闭动效")

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
        self.config.reduce_motion = not self.reduce_motion.isChecked()

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