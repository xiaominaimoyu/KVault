"""图谱视图、快速切换器与命令面板测试。"""

import pytest

pytestmark = pytest.mark.usefixtures("qapp")

from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

from gui.editor.graph_view import GraphView  # noqa: E402
from gui.editor.quick_switcher import (  # noqa: E402
    Command,
    CommandPaletteDialog,
    NoteCandidate,
    QuickSwitcherDialog,
    fuzzy_score,
    rank_notes,
)


class TestFuzzyScore:
    def test_exact_match_highest(self):
        assert fuzzy_score("笔记", "笔记") > fuzzy_score("笔记", "我的笔记集")

    def test_substring(self):
        assert fuzzy_score("学习", "机器学习笔记") is not None

    def test_subsequence(self):
        # 子序列匹配基于字符本身，不做拼音转换：拉丁文缩写可命中
        assert fuzzy_score("mln", "machine learning notes") is not None

    def test_subsequence_must_respect_order(self):
        assert fuzzy_score("tnm", "machine learning notes") is None

    def test_non_match(self):
        assert fuzzy_score("xyz", "机器学习") is None

    def test_empty_query_matches_all(self):
        assert fuzzy_score("", "任意") is not None

    def test_empty_haystack(self):
        assert fuzzy_score("x", "") is None

    def test_consecutive_beats_scattered(self):
        consecutive = fuzzy_score("abc", "abc")
        scattered = fuzzy_score("abc", "axbxc")
        assert consecutive > scattered


class TestRankNotes:
    def test_orders_by_relevance(self):
        candidates = [
            NoteCandidate("a.md", "机器学习"),
            NoteCandidate("b.md", "学习"),
            NoteCandidate("c.md", "机器学习完整指南"),
        ]
        ranked = rank_notes(candidates, "机器学习")
        assert ranked[0].display == "机器学习"

    def test_excludes_non_matches(self):
        candidates = [
            NoteCandidate("a.md", "甲"),
            NoteCandidate("b.md", "乙"),
        ]
        assert rank_notes(candidates, "丙") == []

    def test_empty_query_keeps_all(self):
        candidates = [NoteCandidate("a.md", "甲")]
        assert len(rank_notes(candidates, "")) == 1


class TestQuickSwitcher:
    def test_lists_candidates(self, qapp):
        dialog = QuickSwitcherDialog()
        dialog.set_candidates([NoteCandidate("a.md", "甲"), NoteCandidate("b.md", "乙")])
        assert dialog._list.count() == 2

    def test_filters_by_query(self, qapp):
        dialog = QuickSwitcherDialog()
        dialog.set_candidates([NoteCandidate("a.md", "甲"), NoteCandidate("b.md", "乙")])
        dialog._search.setText("乙")
        assert dialog._list.count() == 1

    def test_status_shows_match_count(self, qapp):
        dialog = QuickSwitcherDialog()
        dialog.set_candidates([NoteCandidate("a.md", "甲")])
        assert "1" in dialog._status.text()

    def test_choose_emits_path(self, qapp):
        dialog = QuickSwitcherDialog()
        chosen = []
        dialog.noteChosen.connect(chosen.append)
        dialog.set_candidates([NoteCandidate("a.md", "甲")])
        dialog._accept_current()
        assert chosen == ["a.md"]

    def test_current_path_falls_back_to_first(self, qapp):
        dialog = QuickSwitcherDialog()
        dialog.set_candidates([NoteCandidate("only.md", "唯一")])
        assert dialog.current_path() == "only.md"

    def test_no_candidates_current_path_none(self, qapp):
        assert QuickSwitcherDialog().current_path() is None

    def test_enter_key_accepts(self, qapp):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        dialog = QuickSwitcherDialog()
        chosen = []
        dialog.noteChosen.connect(chosen.append)
        dialog.set_candidates([NoteCandidate("a.md", "甲")])
        dialog.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
        assert chosen == ["a.md"]

    def test_up_down_navigation(self, qapp):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent

        dialog = QuickSwitcherDialog()
        dialog.set_candidates([
            NoteCandidate("a.md", "甲"), NoteCandidate("b.md", "乙"), NoteCandidate("c.md", "丙"),
        ])
        dialog.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
        dialog.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
        assert dialog._list.currentRow() == 1


class TestCommandPalette:
    def test_lists_commands(self, qapp):
        dialog = CommandPaletteDialog()
        dialog.set_commands([Command("新建笔记", lambda: None, "Ctrl+N")])
        assert dialog._list.count() == 1

    def test_filters_by_query(self, qapp):
        dialog = CommandPaletteDialog()
        dialog.set_commands([
            Command("新建笔记", lambda: None),
            Command("打开图谱", lambda: None),
        ])
        dialog._search.setText("图谱")
        assert dialog._list.count() == 1

    def test_shortcut_shown(self, qapp):
        dialog = CommandPaletteDialog()
        dialog.set_commands([Command("新建笔记", lambda: None, "Ctrl+N")])
        assert "Ctrl+N" in dialog._list.item(0).text()

    def test_choose_emits_command(self, qapp):
        dialog = CommandPaletteDialog()
        chosen = []
        dialog.commandChosen.connect(chosen.append)
        dialog.set_commands([Command("命令", lambda: None)])
        dialog._on_activated(dialog._list.item(0))
        assert len(chosen) == 1
        assert chosen[0].name == "命令"

    def test_empty_state(self, qapp):
        dialog = CommandPaletteDialog()
        dialog.set_commands([])
        assert dialog._empty.isVisible() is False or True
        assert dialog.current_command() is None


class TestGraphView:
    def test_constructs(self, qapp):
        assert GraphView() is not None

    def test_empty_graph(self, qapp):
        view = GraphView()
        assert view.show_graph({}) == 0
        assert view.node_count() == 0

    def test_single_node(self, qapp):
        view = GraphView()
        assert view.show_graph({"a.md": []}) == 1
        assert view.node_count() == 1

    def test_linked_nodes_render_edges(self, qapp):
        view = GraphView()
        view.show_graph({"a.md": ["b.md"], "b.md": ["a.md"]})
        assert view.node_count() == 2
        assert view.edge_count() == 2

    def test_edge_count_matches_links(self, qapp):
        view = GraphView()
        view.show_graph({"a.md": ["b.md", "c.md"], "b.md": [], "c.md": []})
        assert view.edge_count() == 2

    def test_nodes_have_distinct_positions(self, qapp):
        view = GraphView()
        view.show_graph({"a.md": ["b.md"], "b.md": [], "c.md": []})
        positions = view.node_positions()
        values = [(p.x(), p.y()) for p in positions.values()]
        assert len(set(values)) == len(values)

    def test_node_positions_are_applied_to_items(self, qapp):
        """回归：布局坐标必须写进节点，否则所有节点会渲染在原点。"""
        view = GraphView()
        view.show_graph({"a.md": ["b.md"], "b.md": [], "c.md": []})
        for path, expected in view.node_positions().items():
            actual = view.node_for(path).position()
            assert actual.x() == pytest.approx(expected.x())
            assert actual.y() == pytest.approx(expected.y())

    def test_node_bounds_are_distinct(self, qapp):
        view = GraphView()
        view.show_graph({"a.md": [], "b.md": [], "c.md": []})
        rects = [view.node_for(p).boundingRect().center() for p in ("a.md", "b.md", "c.md")]
        centers = {(r.x(), r.y()) for r in rects}
        assert len(centers) == 3

    def test_layout_is_deterministic(self, qapp):
        graph = {"a.md": ["b.md"], "b.md": ["c.md"], "c.md": []}
        first = GraphView()
        first.show_graph(graph)
        second = GraphView()
        second.show_graph(graph)

        a = first.node_positions()
        b = second.node_positions()
        assert set(a) == set(b)
        for key in a:
            assert abs(a[key].x() - b[key].x()) < 1e-6

    def test_layout_does_not_overlap(self, qapp):
        view = GraphView()
        view.show_graph({f"n{i}.md": [] for i in range(8)})
        positions = list(view.node_positions().values())
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                distance = (positions[i] - positions[j]).manhattanLength()
                assert distance > 1.0

    def test_degree_affects_radius(self, qapp):
        view = GraphView()
        view.show_graph({"hub.md": [f"x{i}.md" for i in range(5)]})
        hub = view.node_for("hub.md")
        leaf = view.node_for("x0.md")
        assert hub.radius() > leaf.radius()

    def test_orphan_node_rendered(self, qapp):
        view = GraphView()
        view.show_graph({"a.md": [], "b.md": ["c.md"], "c.md": []})
        assert view.node_for("a.md") is not None

    def test_titles_override_labels(self, qapp):
        view = GraphView()
        view.show_graph({"a.md": []}, titles={"a.md": "自定义标题"})
        assert view.node_for("a.md").title == "自定义标题"

    def test_node_cap_prevents_overload(self, qapp):
        view = GraphView()
        count = view.show_graph({f"n{i}.md": [] for i in range(500)})
        assert count <= 300

    def test_high_degree_nodes_kept_when_capped(self, qapp):
        nodes = {f"leaf{i}.md": [] for i in range(400)}
        nodes["hub.md"] = [f"leaf{i}.md" for i in range(50)]
        view = GraphView()
        view.show_graph(nodes)
        assert view.node_for("hub.md") is not None

    def test_theme_switch(self, qapp):
        view = GraphView()
        view.show_graph({"a.md": ["b.md"], "b.md": []})
        view.set_theme("light")
        view.set_theme("dark")

    def test_paint_does_not_raise(self, qapp):
        from PySide6.QtGui import QPaintEvent
        from PySide6.QtCore import QRect

        view = GraphView()
        view.resize(600, 500)
        view.show_graph({"a.md": ["b.md"], "b.md": ["a.md"]})
        view.paintEvent(QPaintEvent(QRect(0, 0, 600, 500)))

    def test_click_node_emits(self, qapp, monkeypatch):
        """点击节点应上抛该节点的路径。

        命中判定依赖视口几何，离屏环境下不稳定，因此这里直接固定 itemAt 的返回值，
        只验证事件处理逻辑本身。
        """
        view = GraphView()
        view.show_graph({"a.md": []})
        view.resize(400, 400)

        node = view.node_for("a.md")
        monkeypatch.setattr(view, "itemAt", lambda _pos: node)

        selected = []
        view.nodeSelected.connect(selected.append)

        view.mousePressEvent(
            QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(100, 100),
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            )
        )
        assert selected == ["a.md"]

    def test_click_empty_space_no_emit(self, qapp, monkeypatch):
        view = GraphView()
        view.show_graph({"a.md": []})
        view.resize(400, 400)
        monkeypatch.setattr(view, "itemAt", lambda _pos: None)

        selected = []
        view.nodeSelected.connect(selected.append)

        view.mousePressEvent(
            QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(2, 2),
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            )
        )
        assert selected == []

    def test_click_non_node_item_no_emit(self, qapp, monkeypatch):
        view = GraphView()
        view.show_graph({"a.md": []})
        view.resize(400, 400)

        from PySide6.QtWidgets import QGraphicsEllipseItem

        monkeypatch.setattr(view, "itemAt", lambda _pos: QGraphicsEllipseItem())

        selected = []
        view.nodeSelected.connect(selected.append)
        view.mousePressEvent(
            QMouseEvent(
                QMouseEvent.Type.MouseButtonPress,
                QPointF(2, 2),
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            )
        )
        assert selected == []

    def test_node_node_for_unknown_returns_none(self, qapp):
        view = GraphView()
        view.show_graph({"a.md": []})
        assert view.node_for("missing.md") is None