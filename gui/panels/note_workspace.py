"""笔记工作台。

把笔记库的核心操作组装成一个可用的三栏界面：

```
┌──────────┬──────────────────────────┬──────────────────┐
│ 笔记列表  │  编辑 / 阅读（可切换）     │  反链 / 出链      │
│ + 标签    │                           │                  │
└──────────┴──────────────────────────┴──────────────────┘
```

与 KVault 既有的「文档」视图并列，构成完整知识库：**文档**用于导入外部资料做语义
检索，**笔记**用于自己写作、链接与沉淀。

本控件只负责交互编排，磁盘与索引操作全部委托给 :class:`~core.note_store.NoteStore`。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.note_store import NoteStore
from core.vault import VaultError
from core.title import headings
from gui.editor.link_panels import BacklinkPanel, OutgoingLinkPanel
from gui.editor.markdown_editor import MarkdownEditor
from gui.editor.note_viewer import NoteViewer


class NoteListPanel(QWidget):
    """笔记列表：目录树 + 标签筛选。"""

    noteSelected = Signal(str)
    createRequested = Signal()
    deleteRequested = Signal(str)
    renameRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notes: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.search = QLineEdit(self)
        self.search.setObjectName("NoteListSearch")
        self.search.setPlaceholderText("搜索笔记…")

        self.tag_filter = QComboBox(self)
        self.tag_filter.setObjectName("NoteListTagFilter")
        self.tag_filter.addItem("全部标签", "")

        buttons = QHBoxLayout()
        self.new_button = QPushButton("新建", self)
        self.rename_button = QPushButton("重命名", self)
        self.delete_button = QPushButton("删除", self)
        self.new_button.setObjectName("NoteListNew")
        buttons.addWidget(self.new_button)
        buttons.addWidget(self.rename_button)
        buttons.addWidget(self.delete_button)

        self.tree = QTreeWidget(self)
        self.tree.setObjectName("NoteTree")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)

        self.count_label = QLabel("0 篇笔记", self)
        self.count_label.setObjectName("NoteListCount")

        layout.addWidget(self.search)
        layout.addWidget(self.tag_filter)
        layout.addLayout(buttons)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.count_label)

        self._populate()

    def _populate(self) -> None:
        """建立按钮与信号的初始连接。

        搜索与标签的过滤信号也在这里连接，使面板**自足**——
        单独使用（不经 NoteWorkspace）时同样会实时过滤。
        """
        self.new_button.clicked.connect(self.createRequested.emit)
        self.rename_button.clicked.connect(
            lambda: self.renameRequested.emit(self.current_path() or "")
        )
        self.delete_button.clicked.connect(
            lambda: self.deleteRequested.emit(self.current_path() or "")
        )
        self.search.textChanged.connect(lambda _text: self._apply_filter())
        self.tag_filter.currentIndexChanged.connect(lambda _index: self._apply_filter())

    def _apply_filter(self) -> None:
        """按当前搜索词与标签重新过滤已加载的笔记。"""
        self.set_notes(self._notes)

    # ---------------------------------------------------------------- 数据

    def set_notes(self, notes: list) -> None:
        """更新笔记列表，按目录分组展示。"""
        self._notes = list(notes)
        keyword = self.search.text().strip().lower()
        tag = self.tag_filter.currentData() or ""

        visible = [
            note for note in self._notes
            if (not keyword or keyword in note.title.lower() or keyword in note.path.lower())
            and (not tag or tag in note.tags)
        ]

        self.tree.clear()
        folders: dict[str, QTreeWidgetItem] = {}
        root = self.tree.invisibleRootItem()

        for note in sorted(visible, key=lambda n: n.path):
            folder = note.folder
            if folder:
                parent = folders.get(folder)
                if parent is None:
                    parent = QTreeWidgetItem(self.tree, [folder])
                    parent.setData(0, Qt.UserRole, None)
                    folders[folder] = parent
                holder = parent
            else:
                holder = root

            item = QTreeWidgetItem(holder, [note.title or note.name])
            item.setData(0, Qt.UserRole, note.path)
            item.setToolTip(0, note.path)

        self.tree.expandAll()
        self.count_label.setText(f"{len(visible)} 篇笔记")

    def set_tags(self, counts: dict[str, int]) -> None:
        """更新标签下拉框。"""
        current = self.tag_filter.currentData()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItem("全部标签", "")
        for tag, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            self.tag_filter.addItem(f"#{tag} ({count})", tag)
        index = self.tag_filter.findData(current)
        if index >= 0:
            self.tag_filter.setCurrentIndex(index)
        self.tag_filter.blockSignals(False)

    def current_path(self) -> str | None:
        """当前选中的笔记路径。"""
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def select_path(self, path: str) -> bool:
        """按路径选中笔记。"""
        root = self.tree.invisibleRootItem()
        if self._select_in(root, path):
            return True
        for i in range(self.tree.topLevelItemCount()):
            if self._select_in(self.tree.topLevelItem(i), path):
                return True
        return False

    def _select_in(self, parent: QTreeWidgetItem, path: str) -> bool:
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, Qt.UserRole) == path:
                self.tree.setCurrentItem(child)
                return True
            if self._select_in(child, path):
                return True
        return False

    # ---------------------------------------------------------------- 事件

    def _on_current_changed(self, current, _previous) -> None:
        if current is not None and current.data(0, Qt.UserRole):
            self.noteSelected.emit(current.data(0, Qt.UserRole))

    def _on_double_clicked(self, item, _column) -> None:
        path = item.data(0, Qt.UserRole)
        if path:
            self.renameRequested.emit(path)


class NoteWorkspace(QWidget):
    """完整的笔记工作台。"""

    #: 需要新建笔记时上抛（标题可为空）
    noteCreateRequested = Signal(str)
    #: 笔记内容已保存
    noteSaved = Signal(str)
    #: 统计信息变化
    statsChanged = Signal(dict)

    MODE_EDIT = "编辑"
    MODE_READ = "阅读"
    MODE_SPLIT = "分栏"

    def __init__(self, store: NoteStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._current_path: str | None = None
        self._loading = False
        self._theme = "dark"

        self.list_panel = NoteListPanel(self)
        self.editor = MarkdownEditor(self)
        self.viewer = NoteViewer(self)
        self.backlinks = BacklinkPanel(self)
        self.outgoing = OutgoingLinkPanel(self)

        self._build_ui()
        self._connect()
        self.refresh()

    # ---------------------------------------------------------------- 构建

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left = QWidget(self)
        left.setObjectName("NoteListColumn")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.list_panel)

        # 右侧：标题栏 + 内容区 + 链接面板
        right = QWidget(self)
        right.setObjectName("NoteDetailColumn")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        header = QWidget(right)
        header.setObjectName("NoteHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)

        self.title_label = QLabel("", header)
        self.title_label.setObjectName("NoteTitle")
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.mode_select = QComboBox(header)
        self.mode_select.setObjectName("NoteModeSelect")
        self.mode_select.addItems([self.MODE_EDIT, self.MODE_READ, self.MODE_SPLIT])
        self.mode_select.setCurrentText(self.MODE_SPLIT)

        header_layout.addWidget(self.title_label, 1)
        header_layout.addWidget(self.mode_select)

        # 三种模式共用一个栈：编辑 / 阅读 / 分栏
        split = QSplitter(Qt.Vertical, self)
        split.addWidget(self.editor)
        split.addWidget(self.viewer)
        split.setSizes([400, 400])
        self.split_view = split

        self.mode_stack = QStackedWidget(right)
        self.mode_stack.addWidget(self.editor)
        self.mode_stack.addWidget(self.viewer)
        self.mode_stack.addWidget(split)

        side = QTabWidget(right)
        side.setObjectName("NoteSideTabs")
        side.addTab(self.backlinks, "反链")
        side.addTab(self.outgoing, "出链")

        right_layout.addWidget(header)
        right_layout.addWidget(self.mode_stack, 1)
        right_layout.addWidget(side, 1)

        outer = QSplitter(Qt.Horizontal, self)
        outer.addWidget(left)
        outer.addWidget(right)
        outer.setSizes([300, 900])
        outer.setStretchFactor(1, 1)

        layout.addWidget(outer)
        self.outer_splitter = outer

    def _connect(self) -> None:
        panel = self.list_panel
        panel.noteSelected.connect(self.open_note)
        panel.createRequested.connect(self._prompt_new_note)
        panel.renameRequested.connect(self._prompt_rename)
        panel.deleteRequested.connect(self._prompt_delete)

        self.editor.saveRequested.connect(self.save_current)
        self.editor.openLinkRequested.connect(self._open_link_target)
        self.editor.textChangedSignal.connect(self._on_editor_changed)

        self.viewer.linkClicked.connect(self._open_link_target)
        self.viewer.brokenLinkClicked.connect(self._create_from_link)

        self.backlinks.noteSelected.connect(self.open_note)
        self.outgoing.noteSelected.connect(self.open_note)
        self.outgoing.createRequested.connect(self._create_from_link)

        self.mode_select.currentTextChanged.connect(self._apply_mode)

    # ---------------------------------------------------------------- 模式

    def _apply_mode(self, mode: str) -> None:
        index = {self.MODE_EDIT: 0, self.MODE_READ: 1, self.MODE_SPLIT: 2}.get(mode, 2)
        self.mode_stack.setCurrentIndex(index)
        self._refresh_viewer()

    def set_theme(self, theme: str) -> None:
        """切换主题。"""
        self._theme = theme
        self.editor.set_theme(theme)

    # ---------------------------------------------------------------- 刷新

    def refresh(self) -> None:
        """从 store 重新载入列表与标签。"""
        self._reload_list()
        self.list_panel.set_tags(self.store.list_tags())
        self.statsChanged.emit(self.store.stats())

    def _reload_list(self) -> None:
        current = self.list_panel.current_path()
        self.list_panel.set_notes(self.store.list_notes())
        if current:
            self.list_panel.select_path(current)

    # ---------------------------------------------------------------- 打开

    def open_note(self, path: str) -> bool:
        """打开指定笔记。"""
        if not path:
            return False
        try:
            content = self.store.read(path)
        except (VaultError, OSError, ValueError, UnicodeDecodeError):
            return False

        self._current_path = path
        self._loading = True
        try:
            record = self.store.get(path)
            self.title_label.setText(record.title if record else path)
            self.editor.set_text(content, path)
            self.viewer.set_note_path(path)
            self.viewer.render_markdown(content, record.title if record else "")
        finally:
            self._loading = False

        self._refresh_links()
        self.list_panel.select_path(path)
        return True

    def current_path(self) -> str | None:
        """当前打开的笔记路径。"""
        return self._current_path

    def _refresh_links(self) -> None:
        path = self._current_path
        if not path:
            self.backlinks.set_links([])
            self.outgoing.set_links([])
            return
        self.backlinks.set_links(self.store.backlinks(path))
        self.outgoing.set_links(self.store.outgoing_links(path))

    def _refresh_viewer(self) -> None:
        if self._current_path and self.mode_stack.currentIndex() in (1, 2):
            try:
                content = self.store.read(self._current_path)
            except (OSError, ValueError):
                return
            record = self.store.get(self._current_path)
            self.viewer.render_markdown(content, record.title if record else "")

    # ---------------------------------------------------------------- 保存

    def _on_editor_changed(self, _text: str) -> None:
        """编辑过程中实时刷新阅读视图（分栏/阅读模式才需要）。"""
        if self._loading or self.mode_stack.currentIndex() == 0:
            return
        self._refresh_viewer()

    def save_current(self) -> bool:
        """保存当前笔记。"""
        path = self._current_path
        if not path:
            return False
        content = self.editor.text()
        try:
            record = self.store.save_note(path, content)
        except Exception:  # noqa: BLE001 —— 保存失败要以对话框告知用户，不能崩
            QMessageBox.warning(self, "保存失败", f"无法写入笔记：\n{path}")
            return False

        if record is not None:
            self.title_label.setText(record.title)
            self._current_path = record.path

        self.editor.mark_clean()
        self.noteSaved.emit(self._current_path or "")
        self._reload_list()
        self._refresh_links()
        self._refresh_viewer()
        return True

    def _open_link_target(self, target: str) -> None:
        """跳转到链接目标。"""
        resolved = self.store.vault.resolve_link(target, self._current_path or "")
        if resolved and self.open_note(resolved):
            return
        self._create_from_link(target)

    def _create_from_link(self, target: str) -> None:
        """由未解析的链接创建笔记。"""
        if not target:
            return
        path = self.store.create_note(target, content=f"# {target}\n\n")
        self.refresh()
        self.open_note(path)

    # ---------------------------------------------------------------- 增删改

    def _prompt_new_note(self) -> None:
        title, ok = QInputDialog.getText(self, "新建笔记", "笔记标题：")
        if not ok or not title.strip():
            return
        path = self.store.create_note(title.strip())
        self.noteCreateRequested.emit(path)
        self.refresh()
        self.open_note(path)

    def _prompt_rename(self, path: str | None) -> None:
        if not path:
            return
        current = self.store.get(path)
        title, ok = QInputDialog.getText(
            self, "重命名笔记", "新标题：", text=current.title if current else ""
        )
        if not ok or not title.strip():
            return
        new_path = self.store.rename_note(path, title.strip())
        self.editor.set_path(new_path)
        self._current_path = new_path
        self.refresh()
        self.open_note(new_path)

    def _prompt_delete(self, path: str | None) -> None:
        if not path:
            return
        confirm = QMessageBox.question(
            self,
            "删除笔记",
            f"确定删除「{path}」吗？\n文件会从磁盘移除，此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.store.delete_note(path)
        self._current_path = None
        self.editor.set_text("", None)
        self.viewer.clear_view()
        self.title_label.setText("")
        self.backlinks.set_links([])
        self.outgoing.set_links([])
        self.refresh()

    # ---------------------------------------------------------------- 查询

    def note_candidates(self) -> list:
        """返回全部笔记，供快速切换器使用。"""
        return self.store.list_notes()

    def show_graph(self, graph_widget) -> None:
        """把图谱数据交给外部的图谱控件渲染。"""
        graph_widget.show_graph(
            self.store.linked_notes(),
            {record.path: record.title for record in self.store.list_notes()},
        )

    def outline_for_current(self) -> list[tuple[int, str]]:
        """返回当前笔记的大纲。"""
        if not self._current_path:
            return []
        try:
            return headings(self.store.read(self._current_path))
        except (OSError, ValueError):
            return []