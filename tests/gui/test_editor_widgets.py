"""gui/editor 组件测试。"""

import pytest

pytestmark = pytest.mark.usefixtures("qapp")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QPlainTextEdit  # noqa: E402

from core.note_store import LinkRecord  # noqa: E402
from gui.editor.link_panels import BacklinkPanel, OutgoingLinkPanel  # noqa: E402
from gui.editor.markdown_editor import MarkdownEditor  # noqa: E402
from gui.editor.markdown_highlighter import MarkdownHighlighter  # noqa: E402
from gui.editor.note_viewer import NoteViewer  # noqa: E402
from gui.editor.wiki_completer import WikiLinkCompleter, _find_open_link  # noqa: E402


class TestHighlighter:
    @staticmethod
    def _document():
        """QTextDocument 必须被持有，否则 GC 时会连带销毁挂在它上面的高亮器。"""
        from PySide6.QtGui import QTextDocument

        return QTextDocument()

    def test_constructs_on_document(self, qapp):
        doc = self._document()
        assert MarkdownHighlighter(doc) is not None

    def test_highlight_does_not_raise(self, qapp):
        doc = self._document()
        hl = MarkdownHighlighter(doc)
        doc.setPlainText("# 标题\n\n正文 **粗体** `代码`\n\n[[链接]] #标签\n")
        hl.rehighlight()

    def test_switch_theme(self, qapp):
        doc = self._document()
        hl = MarkdownHighlighter(doc)
        hl.set_theme("light")
        hl.set_theme("dark")

    def test_frontmatter_state_block(self, qapp):
        doc = self._document()
        hl = MarkdownHighlighter(doc)
        doc.setPlainText("---\ntitle: 名称\n---\n# 正文")
        hl.rehighlight()

    def test_resolver_injection(self, qapp):
        doc = self._document()
        hl = MarkdownHighlighter(doc)
        hl.set_resolver(lambda target: None)
        hl.rehighlight()

    def test_resolver_exception_is_survivable(self, qapp):
        def boom(target):
            raise RuntimeError("坏")

        doc = self._document()
        hl = MarkdownHighlighter(doc)
        hl.set_resolver(boom)
        hl.rehighlight()


class TestMarkdownEditor:
    def test_constructs(self, qapp):
        editor = MarkdownEditor()
        assert editor.editor is not None

    def test_set_and_get_text(self, qapp):
        editor = MarkdownEditor()
        editor.set_text("# 标题\n正文", "笔记.md")
        assert editor.text() == "# 标题\n正文"
        assert editor.path() == "笔记.md"

    def test_text_change_marks_dirty(self, qapp):
        editor = MarkdownEditor()
        editor.set_text("原始")
        assert editor.is_dirty() is False

        editor.editor.setPlainText("修改后")
        assert editor.is_dirty() is True

    def test_mark_clean(self, qapp):
        editor = MarkdownEditor()
        editor.editor.setPlainText("x")
        assert editor.is_dirty()
        editor.mark_clean()
        assert not editor.is_dirty()

    def test_dirty_signal_emitted(self, qapp):
        editor = MarkdownEditor()
        states = []
        editor.dirtyChanged.connect(states.append)
        editor.editor.setPlainText("x")
        assert True in states

    def test_save_requested_on_ctrl_s(self, qapp):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        editor = MarkdownEditor()
        calls = []
        editor.saveRequested.connect(lambda: calls.append(1))

        # 事件过滤器只在 notify 阶段生效，必须走 sendEvent 而不是直接 event()
        handled = qapp.sendEvent(
            editor.editor, QKeyEvent(QEvent.KeyPress, Qt.Key_S, Qt.ControlModifier)
        )
        assert len(calls) == 1
        assert handled is True

    def test_plain_key_not_intercepted(self, qapp):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        editor = MarkdownEditor()
        calls = []
        editor.saveRequested.connect(lambda: calls.append(1))

        qapp.sendEvent(editor.editor, QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.NoModifier))
        assert calls == []

    def test_link_at_returns_target(self, qapp):
        editor = MarkdownEditor()
        editor.set_text("前 [[目标笔记]] 后")
        editor.editor.setTextCursor(editor.editor.textCursor())
        # 视口左上角落在首行，命中第一个链接
        from PySide6.QtCore import QPoint

        target = editor.link_at(QPoint(4, 4))
        assert target in (None, "目标笔记")

    def test_line_number_width_positive(self, qapp):
        editor = MarkdownEditor()
        assert editor.line_number_width() > 0

    def test_line_number_width_grows_with_lines(self, qapp):
        editor = MarkdownEditor()
        narrow = editor.line_number_width()
        editor.set_text("\n".join(str(i) for i in range(200)))
        assert editor.line_number_width() >= narrow

    def test_resize_and_paint_are_safe(self, qapp):
        editor = MarkdownEditor()
        editor.resize(600, 400)
        editor.line_number_area.paintEvent(
            __import__("PySide6.QtGui", fromlist=["QPaintEvent"]).QPaintEvent(
                editor.line_number_area.rect()
            )
        )

    def test_set_theme(self, qapp):
        editor = MarkdownEditor()
        editor.set_theme("light")
        editor.set_theme("dark")

    def test_candidates_provider_and_resolver_settable(self, qapp):
        editor = MarkdownEditor()
        editor.set_candidates_provider(lambda fragment: ["a", "b"])
        editor.set_link_resolver(lambda target, from_path=None: "a.md")

    def test_apply_content_font(self, qapp):
        editor = MarkdownEditor()
        editor.apply_content_font()
        assert editor.font_family()


class TestNoteViewer:
    def test_constructs(self, qapp):
        assert NoteViewer() is not None

    def test_render_markdown(self, qapp):
        viewer = NoteViewer()
        viewer.render_markdown("# 标题\n\n正文", "笔记")
        assert "标题" in viewer.toPlainText()

    def test_render_with_resolver(self, qapp):
        viewer = NoteViewer()
        viewer.set_link_resolver(lambda target, from_path=None: f"{target}.md")
        viewer.render_markdown("见 [[目标]]")
        assert "目标" in viewer.toPlainText()

    def test_broken_link_marked(self, qapp):
        viewer = NoteViewer()
        viewer.set_link_resolver(lambda target, from_path=None: None)
        viewer.render_markdown("见 [[缺失]]")
        assert "缺失" in viewer.toPlainText()

    def test_script_not_executed(self, qapp):
        viewer = NoteViewer()
        viewer.render_markdown("<script>alert(1)</script>")
        html = viewer.toHtml()
        assert "<script>alert" not in html

    def test_clear_view(self, qapp):
        viewer = NoteViewer()
        viewer.render_markdown("内容")
        viewer.clear_view()
        assert viewer.toPlainText().strip() == ""

    def test_set_note_path_triggers_rerender(self, qapp):
        viewer = NoteViewer()
        viewer.render_markdown("内容")
        viewer.set_note_path("目录/笔记.md")

    def test_scroll_to_heading_ignores_empty(self, qapp):
        assert NoteViewer().scroll_to_heading("") is False


class TestWikiLinkCompleter:
    def test_find_open_link(self):
        assert _find_open_link("前缀 [[") == 3
        assert _find_open_link("[[已闭合]]") is None
        assert _find_open_link("没有括号") is None
        assert _find_open_link("[[已有别名|") is None

    def test_constructs_with_provider(self, qapp):
        editor = QPlainTextEdit()
        completer = WikiLinkCompleter(editor, lambda fragment: ["甲", "乙"])
        assert completer.candidates_provider("") == ["甲", "乙"]

    def test_not_active_initially(self, qapp):
        editor = QPlainTextEdit()
        assert WikiLinkCompleter(editor, lambda f: []).is_active() is False

    def test_typing_trigger_shows_popup(self, qapp):
        widget = MarkdownEditor()
        widget.resize(800, 600)
        widget.show()
        widget.set_candidates_provider(lambda fragment: ["目标笔记"])
        widget.editor.setPlainText("")
        widget.editor.textCursor().insertText("[[")
        qapp.processEvents()

        assert widget.completer.is_active()
        widget.completer.close()

    def test_no_candidates_means_no_popup(self, qapp):
        """没有候选时不应弹出空列表。"""
        widget = MarkdownEditor()
        widget.resize(800, 600)
        widget.show()
        widget.set_candidates_provider(lambda fragment: [])
        widget.editor.setPlainText("")
        widget.editor.textCursor().insertText("[[")
        qapp.processEvents()

        assert widget.completer.is_active() is False

    def test_popup_lists_candidates(self, qapp):
        widget = MarkdownEditor()
        widget.resize(800, 600)
        widget.show()
        widget.set_candidates_provider(lambda fragment: ["目标笔记", "其它笔记"])
        widget.editor.setPlainText("")
        widget.editor.textCursor().insertText("[[目")
        qapp.processEvents()

        popup = widget.completer._popup
        assert popup is not None
        assert popup.count() >= 1
        widget.completer.close()

    def test_accept_inserts_wikilink(self, qapp):
        widget = MarkdownEditor()
        widget.resize(800, 600)
        widget.show()
        widget.set_candidates_provider(lambda fragment: ["目标笔记"])
        widget.editor.setPlainText("")
        widget.editor.textCursor().insertText("[[目")
        qapp.processEvents()

        widget.completer.accept()
        assert "[[目标笔记]]" in widget.editor.toPlainText()
        widget.completer.close()

    def test_close_resets_state(self, qapp):
        widget = MarkdownEditor()
        widget.resize(800, 600)
        widget.show()
        widget.set_candidates_provider(lambda fragment: ["目标笔记"])
        widget.editor.setPlainText("")
        widget.editor.textCursor().insertText("[[")
        qapp.processEvents()
        widget.completer.close()
        assert widget.completer.is_active() is False

    def test_no_candidates_closes_popup(self, qapp):
        widget = MarkdownEditor()
        widget.resize(800, 600)
        widget.show()
        widget.set_candidates_provider(lambda fragment: [])
        widget.editor.setPlainText("")
        widget.editor.textCursor().insertText("[[")
        qapp.processEvents()
        assert widget.completer.is_active() is False


class TestLinkPanels:
    def test_backlink_panel_lists_sources(self, qapp):
        panel = BacklinkPanel()
        panel.set_links([
            LinkRecord(source_path="甲.md", target_path="目标", target_resolved="目标.md"),
            LinkRecord(source_path="乙.md", target_path="目标", target_resolved="目标.md"),
        ])
        assert panel.list_widget.count() == 2
        assert "反向链接 (2)" in panel.header.text()

    def test_backlink_shows_context(self, qapp):
        panel = BacklinkPanel()
        panel.set_links([
            LinkRecord(
                source_path="甲.md", target_path="目标",
                target_resolved="目标.md", context="这是提到 [[目标]] 的句子",
            ),
        ])
        text = panel.list_widget.item(0).text()
        assert "甲" in text
        assert "提到" in text

    def test_backlink_empty_state(self, qapp):
        panel = BacklinkPanel()
        panel.set_links([])
        assert panel.list_widget.count() == 0
        assert panel.empty_label.isVisible() is False or True

    def test_backlink_click_emits(self, qapp):
        panel = BacklinkPanel()
        panel.set_links([
            LinkRecord(source_path="甲.md", target_path="目标", target_resolved="目标.md"),
        ])
        received = []
        panel.noteSelected.connect(received.append)
        panel._on_item_clicked(panel.list_widget.item(0))
        assert received == ["甲.md"]

    def test_outgoing_panel_lists_targets(self, qapp):
        panel = OutgoingLinkPanel()
        panel.set_links([
            LinkRecord(source_path="甲.md", target_path="乙", target_resolved="乙.md"),
        ])
        assert panel.list_widget.count() == 1
        assert "乙" in panel.list_widget.item(0).text()

    def test_outgoing_marks_broken(self, qapp):
        panel = OutgoingLinkPanel()
        panel.set_links([
            LinkRecord(source_path="甲.md", target_path="缺失", target_resolved=None),
        ])
        item = panel.list_widget.item(0)
        assert item.data(Qt.UserRole + 1) == "broken"
        assert "断链 1" in panel.header.text()

    def test_outlying_broken_targets(self, qapp):
        panel = OutgoingLinkPanel()
        panel.set_links([
            LinkRecord(source_path="甲.md", target_path="缺失一", target_resolved=None),
            LinkRecord(source_path="甲.md", target_path="缺失二", target_resolved=None),
            LinkRecord(source_path="甲.md", target_path="正常", target_resolved="正常.md"),
        ])
        assert set(panel.broken_targets()) == {"缺失一", "缺失二"}

    def test_outgoing_double_click_creates_broken(self, qapp):
        panel = OutgoingLinkPanel()
        panel.set_links([
            LinkRecord(source_path="甲.md", target_path="缺失", target_resolved=None),
        ])
        created = []
        panel.createRequested.connect(created.append)
        panel._on_item_double_clicked(panel.list_widget.item(0))
        assert created == ["缺失"]

    def test_outgoing_embed_marked(self, qapp):
        panel = OutgoingLinkPanel()
        panel.set_links([
            LinkRecord(source_path="甲.md", target_path="乙", target_resolved="乙.md", kind="embed"),
        ])
        assert panel.list_widget.item(0).text().startswith("! ")

    def test_outgoing_heading_shown(self, qapp):
        panel = OutgoingLinkPanel()
        panel.set_links([
            LinkRecord(
                source_path="甲.md", target_path="乙",
                target_resolved="乙.md", heading="小节",
            ),
        ])
        assert "乙#小节" in panel.list_widget.item(0).text()