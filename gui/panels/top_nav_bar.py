"""顶部导航栏面板。

替换原 QToolBar，提供结构化导航：Logo + 全局搜索 + 工作区下拉 + 操作按钮。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from gui.styles.icons import icon


class TopNavBar(QWidget):
    """顶部导航栏，高 56px。

    Signals:
        importRequested: 导入按钮点击。
        searchChanged(str): 全局搜索文本变化。
        settingsRequested: 设置按钮点击。
        logsRequested: 日志按钮点击。
        workspaceSwitchRequested(str): 工作区切换（ws_id）。
        workspaceCreateRequested: 新建工作区。
        workspaceDeleteRequested: 删除工作区。
    """

    importRequested = Signal()
    searchChanged = Signal(str)
    settingsRequested = Signal()
    logsRequested = Signal()
    workspaceSwitchRequested = Signal(str)
    workspaceCreateRequested = Signal()
    workspaceDeleteRequested = Signal()
    viewActionRequested = Signal(str)
    """菜单请求切换视图，参数为 ``docs`` / ``notes`` / ``graph``。"""
    quickSwitchRequested = Signal()
    commandPaletteRequested = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setFixedHeight(56)
        self.setObjectName("TopNavBar")
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # §3.5 Logo：16px SVG 图标 + 文字
        logo_label = QLabel()
        logo_label.setObjectName("TopNavBarLogo")
        logo_label.setPixmap(icon("layers", size=16).pixmap(16, 16))
        layout.addWidget(logo_label)

        title_label = QLabel("KVault")
        title_label.setObjectName("TopNavBarTitle")
        layout.addWidget(title_label)

        self._search_box = QLineEdit()
        self._search_box.setObjectName("TopNavBarSearch")
        self._search_box.setPlaceholderText("全局搜索：文件名 / 扩展名 / 分区 / 标签")
        self._search_box.setMinimumWidth(320)
        self._search_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # §3.5 搜索框左侧搜索图标
        self._search_box.addAction(
            icon("search", size=14), QLineEdit.LeadingPosition
        )
        self._search_box.textChanged.connect(self.searchChanged.emit)
        layout.addWidget(self._search_box)

        self._workspace_combo = QComboBox()
        self._workspace_combo.setMinimumWidth(140)
        self._workspace_combo.currentIndexChanged.connect(self._on_workspace_changed)
        layout.addWidget(self._workspace_combo)

        # §3.5 工作区下拉旁展示文档数徽章
        self._doc_count_badge = QLabel("")
        self._doc_count_badge.setObjectName("DocCountBadge")
        layout.addWidget(self._doc_count_badge)

        ws_create_btn = QPushButton()
        ws_create_btn.setProperty("btnType", "icon")
        ws_create_btn.setIcon(icon("folder-plus", size=16))
        ws_create_btn.setToolTip("新建工作区")
        ws_create_btn.clicked.connect(self.workspaceCreateRequested.emit)
        layout.addWidget(ws_create_btn)

        ws_delete_btn = QPushButton()
        ws_delete_btn.setProperty("btnType", "icon")
        ws_delete_btn.setIcon(icon("trash-2", size=16))
        ws_delete_btn.setToolTip("删除工作区")
        ws_delete_btn.clicked.connect(self.workspaceDeleteRequested.emit)
        layout.addWidget(ws_delete_btn)

        self._import_btn = QPushButton("导入文档")
        self._import_btn.setProperty("btnType", "primary")
        self._import_btn.setIcon(icon("upload"))
        self._import_btn.clicked.connect(self.importRequested.emit)
        layout.addWidget(self._import_btn)

        self._settings_btn = QPushButton()
        self._settings_btn.setProperty("btnType", "icon")
        self._settings_btn.setIcon(icon("settings"))
        self._settings_btn.setToolTip("设置")
        self._settings_btn.clicked.connect(self.settingsRequested.emit)
        layout.addWidget(self._settings_btn)

        self._logs_btn = QPushButton()
        self._logs_btn.setProperty("btnType", "icon")
        self._logs_btn.setIcon(icon("file-text"))
        self._logs_btn.setToolTip("日志")
        self._logs_btn.clicked.connect(self.logsRequested.emit)
        layout.addWidget(self._logs_btn)

        # §3.5 右侧菜单按钮
        self._menu_btn = QPushButton()
        self._menu_btn.setProperty("btnType", "icon")
        self._menu_btn.setText("☰")
        self._menu_btn.setToolTip("更多")
        self._menu_btn.clicked.connect(self._on_menu_clicked)
        layout.addWidget(self._menu_btn)

        self._menu = self._build_menu()

    def _build_menu(self) -> QMenu:
        """构建「更多」下拉菜单。"""
        menu = QMenu(self)

        notes_action = QAction("笔记库", menu)
        notes_action.triggered.connect(lambda: self.viewActionRequested.emit("notes"))
        menu.addAction(notes_action)

        graph_action = QAction("知识图谱", menu)
        graph_action.triggered.connect(lambda: self.viewActionRequested.emit("graph"))
        menu.addAction(graph_action)

        menu.addSeparator()

        switch_action = QAction("快速切换笔记", menu)
        switch_action.setShortcut("Ctrl+O")
        switch_action.triggered.connect(self.quickSwitchRequested.emit)
        menu.addAction(switch_action)

        palette_action = QAction("命令面板", menu)
        palette_action.setShortcut("Ctrl+P")
        palette_action.triggered.connect(self.commandPaletteRequested.emit)
        menu.addAction(palette_action)

        return menu

    def _on_menu_clicked(self) -> None:
        """弹出「更多」菜单。"""
        self._menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))

    def _on_workspace_changed(self, index: int):
        if index >= 0:
            ws_id = self._workspace_combo.itemData(index)
            if ws_id:
                self.workspaceSwitchRequested.emit(ws_id)

    def set_workspaces(self, workspaces: list[tuple[str, str]], current_ws_id: str = ""):
        """填充工作区下拉。

        Args:
            workspaces: [(ws_id, ws_name), ...] 列表。
            current_ws_id: 当前工作区 ID。
        """
        self._workspace_combo.blockSignals(True)
        self._workspace_combo.clear()
        for ws_id, ws_name in workspaces:
            self._workspace_combo.addItem(ws_name, ws_id)
        if current_ws_id:
            for i in range(self._workspace_combo.count()):
                if self._workspace_combo.itemData(i) == current_ws_id:
                    self._workspace_combo.setCurrentIndex(i)
                    break
        self._workspace_combo.blockSignals(False)

    def set_doc_count_badge(self, count: int):
        self._doc_count_badge.setText(f"· {count} 文档" if count > 0 else "")

    def focus_global_search(self):
        self._search_box.setFocus()

    def get_search_text(self) -> str:
        return self._search_box.text()