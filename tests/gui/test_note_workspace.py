"""笔记工作台集成测试。"""

import pytest

pytestmark = pytest.mark.usefixtures("qapp")

from core.note_store import NoteStore  # noqa: E402
from gui.panels.note_workspace import NoteListPanel, NoteWorkspace  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return NoteStore(str(tmp_path / "kb.sqlite"), tmp_path / "vault")


@pytest.fixture
def workspace(qapp, store):
    widget = NoteWorkspace(store)
    widget.resize(1200, 800)
    return widget


class TestNoteListPanel:
    def test_constructs(self, qapp):
        assert NoteListPanel() is not None

    def test_shows_notes(self, qapp):
        panel = NoteListPanel()
        from core.note_store import NoteRecord

        panel.set_notes([NoteRecord("a.md", "甲"), NoteRecord("b.md", "乙")])
        assert panel.tree.topLevelItemCount() == 2
        assert "2 篇笔记" in panel.count_label.text()

    def test_groups_by_folder(self, qapp):
        panel = NoteListPanel()
        from core.note_store import NoteRecord

        panel.set_notes([
            NoteRecord("目录/甲.md", "甲"),
            NoteRecord("乙.md", "乙"),
        ])
        assert panel.tree.topLevelItemCount() == 2

    def test_filters_by_keyword(self, qapp):
        panel = NoteListPanel()
        from core.note_store import NoteRecord

        panel.set_notes([NoteRecord("a.md", "机器学习"), NoteRecord("b.md", "烹饪")])
        panel.search.setText("机器")
        assert panel.tree.topLevelItemCount() == 1

    def test_filters_by_tag(self, qapp):
        panel = NoteListPanel()
        from core.note_store import NoteRecord

        panel.set_notes([
            NoteRecord("a.md", "甲", tags=["项目"]),
            NoteRecord("b.md", "乙", tags=["其它"]),
        ])
        # 必须先填充标签下拉框，否则找不到对应项
        panel.set_tags({"项目": 1, "其它": 1})
        assert panel.tree.topLevelItemCount() == 2

        panel.tag_filter.setCurrentIndex(panel.tag_filter.findData("项目"))
        assert panel.tree.topLevelItemCount() == 1

    def test_set_tags_populates_filter(self, qapp):
        panel = NoteListPanel()
        panel.set_tags({"项目": 2, "想法": 1})
        assert panel.tag_filter.count() == 3

    def test_select_path(self, qapp):
        panel = NoteListPanel()
        from core.note_store import NoteRecord

        panel.set_notes([NoteRecord("a.md", "甲")])
        assert panel.select_path("a.md") is True
        assert panel.current_path() == "a.md"

    def test_select_missing_path(self, qapp):
        panel = NoteListPanel()
        assert panel.select_path("missing.md") is False

    def test_current_path_none_initially(self, qapp):
        assert NoteListPanel().current_path() is None


class TestNoteWorkspace:
    def test_constructs(self, workspace):
        assert workspace.list_panel is not None
        assert workspace.editor is not None
        assert workspace.viewer is not None

    def test_lists_existing_notes(self, qapp, workspace, store):
        store.create_note("已有笔记")
        workspace.refresh()
        assert workspace.list_panel.tree.topLevelItemCount() == 1

    def test_open_note_loads_content(self, workspace, store):
        path = store.create_note("目标", content="# 标题\n正文内容")
        assert workspace.open_note(path) is True
        assert "正文内容" in workspace.editor.text()
        assert workspace.current_path() == path

    def test_open_missing_note_returns_false(self, workspace):
        assert workspace.open_note("不存在.md") is False

    def test_open_note_updates_title_label(self, workspace, store):
        path = store.create_note("显示标题")
        workspace.open_note(path)
        assert workspace.title_label.text() == "显示标题"

    def test_open_note_refreshes_links(self, workspace, store):
        store.create_note("目标")
        source = store.create_note("来源", content="见 [[目标]]")
        workspace.open_note(source)
        assert workspace.backlinks.list_widget.count() == 0
        assert workspace.outgoing.list_widget.count() == 1

        target = store.list_notes()[0]
        del target
        workspace.open_note([p for p in store.list_notes()][0].path)
        del source

    def test_save_persists_content(self, workspace, store):
        path = store.create_note("笔记")
        workspace.open_note(path)
        workspace.editor.editor.setPlainText("修改后的内容")
        assert workspace.save_current() is True
        assert "修改后的内容" in store.read(path)

    def test_save_clears_dirty_flag(self, workspace, store):
        path = store.create_note("笔记")
        workspace.open_note(path)
        workspace.editor.editor.setPlainText("新内容")
        assert workspace.editor.is_dirty()
        workspace.save_current()
        assert workspace.editor.is_dirty() is False

    def test_save_without_note_returns_false(self, workspace):
        assert workspace.save_current() is False

    def test_link_click_opens_target(self, workspace, store):
        target = store.create_note("目标笔记")
        source = store.create_note("来源", content="见 [[目标笔记]]")
        workspace.open_note(source)
        workspace._open_link_target("目标笔记")
        assert workspace.current_path() == target

    def test_broken_link_creates_note(self, workspace, store):
        source = store.create_note("来源", content="见 [[尚未存在]]")
        workspace.open_note(source)
        workspace._create_from_link("尚未存在")
        assert any(note.title == "尚未存在" for note in store.list_notes())

    def test_create_via_link_opens_it(self, workspace, store):
        source = store.create_note("来源", content="见 [[新概念]]")
        workspace.open_note(source)
        workspace._open_link_target("新概念")
        assert workspace.current_path() is not None
        assert "新概念" in workspace.current_path()

    def test_mode_switching(self, workspace):
        workspace.mode_select.setCurrentText(workspace.MODE_EDIT)
        assert workspace.mode_stack.currentIndex() == 0
        workspace.mode_select.setCurrentText(workspace.MODE_READ)
        assert workspace.mode_stack.currentIndex() == 1
        workspace.mode_select.setCurrentText(workspace.MODE_SPLIT)
        assert workspace.mode_stack.currentIndex() == 2

    def test_refresh_updates_stats_signal(self, workspace, store):
        received = []
        workspace.statsChanged.connect(received.append)
        store.create_note("统计")
        workspace.refresh()
        assert received and received[-1]["notes"] == 1

    def test_note_candidates(self, workspace, store):
        store.create_note("甲")
        store.create_note("乙")
        assert len(workspace.note_candidates()) == 2

    def test_outline_of_current_note(self, workspace, store):
        path = store.create_note("大纲", content="# 一\n正文\n## 二")
        workspace.open_note(path)
        outline = workspace.outline_for_current()
        assert [(level, text) for level, text in outline] == [(1, "一"), (2, "二")]

    def test_outline_without_note(self, workspace):
        assert workspace.outline_for_current() == []

    def test_delete_note_flow(self, qapp, workspace, store, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        path = store.create_note("待删除")
        workspace.open_note(path)

        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
        workspace._prompt_delete(path)

        assert store.get(path) is None
        assert workspace.current_path() is None
        assert workspace.editor.text() == ""

    def test_delete_cancelled_keeps_note(self, qapp, workspace, store, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        path = store.create_note("保留")
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))
        workspace._prompt_delete(path)
        assert store.get(path) is not None

    def test_rename_flow(self, qapp, workspace, store, monkeypatch):
        from PySide6.QtWidgets import QInputDialog

        path = store.create_note("旧名")
        monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("新名", True)))
        workspace._prompt_rename(path)

        assert store.get("新名.md") is not None
        assert workspace.current_path() == "新名.md"

    def test_create_flow(self, qapp, workspace, store, monkeypatch):
        from PySide6.QtWidgets import QInputDialog

        monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("全新笔记", True)))
        created = []
        workspace.noteCreateRequested.connect(created.append)
        workspace._prompt_new_note()

        assert created
        assert workspace.current_path() is not None

    def test_create_cancelled(self, qapp, workspace, monkeypatch):
        from PySide6.QtWidgets import QInputDialog

        monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
        created = []
        workspace.noteCreateRequested.connect(created.append)
        workspace._prompt_new_note()
        assert created == []

    def test_save_emits_signal(self, workspace, store):
        saved = []
        workspace.noteSaved.connect(saved.append)
        path = store.create_note("笔记")
        workspace.open_note(path)
        workspace.editor.editor.setPlainText("x")
        workspace.save_current()
        assert saved == [path]

    def test_show_graph_delegates(self, workspace, store):
        from gui.editor.graph_view import GraphView

        store.create_note("甲", content="[[乙]]")
        store.create_note("乙")
        graph = GraphView()
        workspace.show_graph(graph)
        assert graph.node_count() == 2

    def test_set_theme(self, workspace):
        workspace.set_theme("light")
        workspace.set_theme("dark")

    def test_viewer_renders_in_read_mode(self, workspace, store):
        path = store.create_note("阅读", content="# 标题\n\n正文")
        workspace.mode_select.setCurrentText(workspace.MODE_READ)
        workspace.open_note(path)
        assert "标题" in workspace.viewer.toPlainText()

    def test_search_filters_list_live(self, workspace, store):
        store.create_note("机器学习")
        store.create_note("烹饪指南")
        workspace.refresh()
        workspace.list_panel.search.setText("机器")
        assert workspace.list_panel.tree.topLevelItemCount() == 1

    def test_stats_reflects_tags(self, workspace, store):
        store.create_note("甲", content="#标签")
        workspace.refresh()
        counts = workspace.list_panel.tag_filter
        assert counts.count() >= 2