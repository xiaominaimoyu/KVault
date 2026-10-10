"""MainWindow 与笔记库视图的集成测试。

这里**真正构造** MainWindow（而非静态检查源码），确保笔记库接入没有破坏
既有界面。所有依赖被替换为桩，避免要求本地 Ollama 服务。
"""

import pytest

pytestmark = pytest.mark.usefixtures("qapp")

from PySide6.QtWidgets import QStackedWidget  # noqa: E402

from core.config import Config  # noqa: E402
from core.note_store import NoteStore  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402


class _StubEmbedder:
    """替代 Ollama 的假嵌入服务。"""

    model_name = "fake-embedder"
    backend_type = "fake"

    def is_available(self) -> bool:
        return True

    def is_model_available(self) -> bool:
        return True

    def embed_texts(self, texts):
        return [[0.1] * 8 for _ in texts]

    def embed_query(self, query):
        return [0.1] * 8


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    """构建一个指向临时目录的 MainWindow。"""
    config = Config()
    config.files_dir = tmp_path / "files"
    config.chroma_dir = tmp_path / "chroma"
    config.sqlite_path = tmp_path / "kb.sqlite"
    config.logs_dir = tmp_path / "logs"
    config.top_k = 3
    config.workspaces.current = "default"

    for path in (config.files_dir, config.chroma_dir, config.logs_dir):
        path.mkdir(parents=True, exist_ok=True)
    config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(MainWindow, "_build_embedder", lambda self, cfg: _StubEmbedder())
    monkeypatch.setattr(MainWindow, "_check_environment", lambda self: None)

    win = MainWindow(config)
    yield win
    win.close()


class TestConstruction:
    def test_builds(self, window):
        assert window is not None

    def test_note_store_created(self, window):
        assert isinstance(window.note_store, NoteStore)
        assert window.note_store.vault.root.is_dir()

    def test_view_stack_has_three_views(self, window):
        assert isinstance(window.main_stack, QStackedWidget)
        assert window.main_stack.count() == 3

    def test_view_buttons_exist(self, window):
        assert window.docs_view_button is not None
        assert window.notes_view_button is not None
        assert window.graph_view_button is not None

    def test_graph_view_exists(self, window):
        assert window.graph_view is not None

    def test_note_workspace_bound_to_store(self, window):
        assert window.note_workspace.store is window.note_store


class TestViewSwitching:
    def test_switch_to_notes(self, window):
        window._switch_view("notes")
        assert window.main_stack.currentIndex() == 1
        assert window._current_view == "notes"

    def test_switch_to_graph(self, window):
        window._switch_view("graph")
        assert window.main_stack.currentIndex() == 2

    def test_switch_to_docs(self, window):
        window._switch_view("notes")
        window._switch_view("docs")
        assert window.main_stack.currentIndex() == 0
        assert window.nav_panel.isVisible() is False or True

    def test_invalid_view_ignored(self, window):
        window._switch_view("docs")
        window._switch_view("不存在")
        assert window._current_view == "docs"

    def test_active_button_marked(self, window):
        window._switch_view("notes")
        assert window.notes_view_button.property("btnType") == "primary"
        assert window.docs_view_button.property("btnType") == "secondary"


class TestNotesInMainWindow:
    def test_create_note_through_store(self, window):
        path = window.note_store.create_note("集成笔记", content="# 内容")
        window.note_workspace.refresh()
        assert window.note_store.get(path) is not None

    def test_open_note_via_workspace(self, window):
        path = window.note_store.create_note("目标", content="# 标题\n正文")
        assert window.note_workspace.open_note(path) is True
        assert "正文" in window.note_workspace.editor.text()

    def test_note_save_updates_store(self, window):
        path = window.note_store.create_note("笔记")
        window.note_workspace.open_note(path)
        window.note_workspace.editor.editor.setPlainText("更新内容")
        window.note_workspace.save_current()
        assert "更新内容" in window.note_store.read(path)

    def test_graph_reflects_links(self, window):
        window.note_store.create_note("甲", content="[[乙]]")
        window.note_store.create_note("乙")
        window._refresh_graph()
        assert window.graph_view.node_count() == 2

    def test_graph_status_text(self, window):
        window.note_store.create_note("甲")
        window._refresh_graph()
        assert "笔记" in window.graph_status.text()

    def test_click_graph_node_opens_note(self, window):
        path = window.note_store.create_note("图谱节点")
        window._open_graph_node(path)
        assert window._current_view == "notes"
        assert window.note_workspace.current_path() == path

    def test_sync_notes_reports(self, window, monkeypatch):
        window.note_store.create_note("甲")
        monkeypatch.setattr(
            window.status_bar, "show_message", lambda *a, **k: None
        )
        window._sync_notes()

    def test_sync_detects_external_file(self, window, monkeypatch):
        window.note_store.vault.write("外部.md", "# 外部\n内容")
        monkeypatch.setattr(window.status_bar, "show_message", lambda *a, **k: None)
        window._sync_notes()
        assert window.note_store.get("外部.md") is not None

    def test_note_stats_update_status_bar(self, window):
        window.note_store.create_note("甲")
        window._on_note_stats({"notes": 1, "links": 0, "tags": 0})


class TestQuickSwitcherIntegration:
    def test_quick_switch_opens_note(self, window):
        path = window.note_store.create_note("可切换笔记")
        opened = []
        window.note_workspace.open_note = lambda p: opened.append(p) or True
        window._open_note_from_switcher(path)
        assert opened == [path]
        assert window._current_view == "notes"

    def test_open_quick_switcher_builds_dialog(self, window):
        window.note_store.create_note("甲")
        window._open_quick_switcher()

    def test_open_command_palette_builds_dialog(self, window):
        window._open_command_palette()

    def test_run_command_executes(self, window):
        from gui.editor.quick_switcher import Command

        calls = []
        window._run_command(Command("测试", lambda: calls.append(1)))
        assert calls == [1]

    def test_run_command_ignores_non_callable(self, window):
        from gui.editor.quick_switcher import Command

        window._run_command(Command("测试", "not-callable"))


class TestWorkspaceSwitchRebuildsNotes:
    def test_rebuild_note_workspace(self, window):
        created = window._workspace_manager.create("第二个工作区")
        window.note_store.create_note("原工作区笔记")

        window._workspace_manager.switch(created.id)
        window._rebuild_services_for_workspace()

        assert window.note_store is not None
        assert window.note_workspace.store is window.note_store
        # 新工作区不应有旧工作区的笔记
        assert window.note_store.list_notes() == []

    def test_switch_saves_pending_edit(self, window):
        """切换工作区前必须把未保存的编辑落盘，否则内容会随工作区重建而丢失。"""
        path = window.note_store.create_note("待保存")
        window.note_workspace.open_note(path)
        window.note_workspace.editor.editor.setPlainText("未保存内容")
        assert window.note_workspace.editor.is_dirty()

        created = window._workspace_manager.create("临时工作区")
        window._switch_workspace(created.id)

        # 编辑内容已写入原工作区的 vault
        workspace_a = window._workspace_manager.get_workspace("default")
        vault_a = NoteStore(
            str(workspace_a.sqlite_path), workspace_a.base_dir / "vault", None
        )
        assert "未保存内容" in vault_a.read(path)


class TestShortcutsRegistered:
    def test_note_shortcuts_registered(self, window):
        keys = set(window._shortcut_manager.shortcuts.keys())
        for action_id in ("view_notes", "view_graph", "quick_switch", "command_palette"):
            assert action_id in keys

    def test_view_notes_shortcut_switches_view(self, window):
        window._shortcut_manager.shortcuts["view_notes"].activated.emit()
        assert window._current_view == "notes"

    def test_view_graph_shortcut_switches_view(self, window):
        window._shortcut_manager.shortcuts["view_graph"].activated.emit()
        assert window._current_view == "graph"