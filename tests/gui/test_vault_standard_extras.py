"""Vault Standard 补充实现测试：TagPill、ScoreBar 区间、增量/模型切换对话框。"""

import pytest

pytestmark = pytest.mark.usefixtures("qapp")

from gui.widgets.score_bar import ScoreBar, score_band  # noqa: E402
from gui.widgets.tag_pill import TagPill  # noqa: E402


class TestTagPill:
    """§8.4 / §9.2 标签 pill 控件。"""

    def test_constructs(self, qapp):
        pill = TagPill("项目", 3)
        assert pill.objectName() == "TagPill"
        assert pill.tag_name() == "项目"
        assert pill.count() == 3

    def test_display_format(self, qapp):
        """显示为 `#标签 · 数量`。"""
        assert TagPill("项目", 3).text() == "#项目 · 3"
        assert TagPill("想法", 0).text() == "#想法"

    def test_checkable(self, qapp):
        pill = TagPill("甲")
        assert pill.isCheckable() is True

    def test_toggle_sets_property(self, qapp):
        pill = TagPill("甲")
        pill.setChecked(True)
        assert pill.is_selected() is True
        assert pill.property("selected") is True

        pill.setChecked(False)
        assert pill.is_selected() is False
        assert pill.property("selected") is False

    def test_toggled_signal(self, qapp):
        pill = TagPill("甲")
        events = []
        pill.toggledState.connect(lambda name, state: events.append((name, state)))

        pill.setChecked(True)
        assert events == [("甲", True)]

    def test_set_count_refreshes_text(self, qapp):
        pill = TagPill("甲", 1)
        pill.set_count(9)
        assert pill.text() == "#甲 · 9"

    def test_set_count_clamps_negative(self, qapp):
        pill = TagPill("甲", 5)
        pill.set_count(-3)
        assert pill.count() == 0

    def test_rename(self, qapp):
        pill = TagPill("旧", 2)
        pill.set_tag_name("新")
        assert pill.tag_name() == "新"
        assert pill.text() == "#新 · 2"

    def test_tooltip_includes_count(self, qapp):
        assert "3" in TagPill("项目", 3).toolTip()

    def test_focus_policy(self, qapp):
        """可键盘访问。"""
        from PySide6.QtCore import Qt

        assert TagPill("甲").focusPolicy() == Qt.StrongFocus


class TestScoreBarBand:
    """§8.7 分数条按区间着色。"""

    def test_band_thresholds(self):
        assert score_band(0.9) == "success"
        assert score_band(0.8) == "success"
        assert score_band(0.79) == "warning"
        assert score_band(0.5) == "warning"
        assert score_band(0.49) == "error"

    def test_bar_exposes_band(self, qapp):
        bar = ScoreBar(0.9)
        assert bar.band() == "success"
        bar.set_score(0.2)
        assert bar.band() == "error"

    def test_bar_sets_dynamic_property(self, qapp):
        bar = ScoreBar(0.6)
        assert bar._bar.property("band") == "warning"

    def test_bar_height_is_4px(self, qapp):
        """§8.7 高度 4px。"""
        assert ScoreBar(0.5)._bar.height() == 4 or ScoreBar(0.5)._bar.maximumHeight() == 4

    def test_score_clamped(self, qapp):
        assert ScoreBar(1.5).score() == 1.0
        assert ScoreBar(-0.5).score() == 0.0

    def test_label_shows_percentage(self, qapp):
        assert ScoreBar(0.85)._score_label.text() == "85%"


class TestIncrementalDialog:
    """§4.3 增量更新对话框。"""

    def test_constructs_with_report(self, qapp):
        from types import SimpleNamespace

        from gui.dialogs.incremental_dialog import IncrementalUpdateDialog

        updater = SimpleNamespace(
            scan_diffs=lambda: SimpleNamespace(
                added=["a.txt"], modified=["b.txt"], deleted=["c.txt"], unreadable=[]
            ),
            update=lambda report: SimpleNamespace(
                success_count=3, fail_count=0, dirty_doc_ids=[]
            ),
        )
        dialog = IncrementalUpdateDialog(updater)
        assert dialog.result_count() == 3
        assert "共 3 项变更" in dialog.status_label.text()

    def test_step_indicator_present(self, qapp):
        from types import SimpleNamespace

        from gui.dialogs.incremental_dialog import STEPS, IncrementalUpdateDialog

        updater = SimpleNamespace(
            scan_diffs=lambda: SimpleNamespace(
                added=[], modified=[], deleted=[], unreadable=[]
            ),
            update=lambda report: SimpleNamespace(
                success_count=0, fail_count=0, dirty_doc_ids=[]
            ),
        )
        dialog = IncrementalUpdateDialog(updater)
        assert dialog.steps is not None
        assert list(STEPS) == ["扫描", "确认", "执行", "完成"]

    def test_no_diff_disables_update(self, qapp):
        from types import SimpleNamespace

        from gui.dialogs.incremental_dialog import IncrementalUpdateDialog

        updater = SimpleNamespace(
            scan_diffs=lambda: SimpleNamespace(
                added=[], modified=[], deleted=[], unreadable=[]
            ),
            update=lambda report: SimpleNamespace(
                success_count=0, fail_count=0, dirty_doc_ids=[]
            ),
        )
        dialog = IncrementalUpdateDialog(updater)
        assert dialog.update_btn.isEnabled() is False


class TestModelSwitchDialog:
    """§4.4 模型切换对话框。"""

    def test_constructs(self, qapp):
        from types import SimpleNamespace

        from gui.dialogs.model_switch_dialog import ModelSwitchDialog

        config = SimpleNamespace(embedding_model="old-model")
        dialog = ModelSwitchDialog(config, None, None)
        assert dialog.new_model_input.text() == "old-model"
        assert dialog.steps is not None

    def test_success_marks_last_step(self, qapp, monkeypatch):
        from types import SimpleNamespace

        from gui.dialogs.model_switch_dialog import ModelSwitchDialog
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

        config = SimpleNamespace(embedding_model="old")
        manager = SimpleNamespace(
            switch_model=lambda name, fn: SimpleNamespace(
                success=True, backup_path="D:/backup", error="", rolled_back=False
            )
        )
        dialog = ModelSwitchDialog(config, manager, lambda: None)
        dialog._on_switch()

        assert dialog.steps.current_step() == 3
        assert "切换成功" in dialog.status_label.text()

    def test_failure_shows_error_banner(self, qapp, monkeypatch):
        from types import SimpleNamespace

        from gui.dialogs.model_switch_dialog import ModelSwitchDialog
        from PySide6.QtWidgets import QMessageBox

        monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

        config = SimpleNamespace(embedding_model="old")
        manager = SimpleNamespace(
            switch_model=lambda name, fn: SimpleNamespace(
                success=False, backup_path=None, error="模型缺失", rolled_back=True
            )
        )
        dialog = ModelSwitchDialog(config, manager, lambda: None)
        dialog._on_switch()

        assert dialog.hint.objectName() == "ErrorBanner"
        assert "已自动回滚" in dialog.hint.text()


class TestExtraQss:
    """补充样式文件必须能正常插值。"""

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_interpolates_without_error(self, theme):
        from gui.styles.apply import _load_extra_qss, interpolate
        from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

        tokens = TOKENS_DARK if theme == "dark" else TOKENS_LIGHT
        rendered = interpolate(_load_extra_qss(theme), tokens)
        assert rendered.strip()
        # 不应残留未替换的占位符
        assert "%(" not in rendered

    @pytest.mark.parametrize("theme", ["dark", "light"])
    def test_no_stray_percent(self, theme):
        """QSS 用 % 格式插值，字面量百分号必须转义成 %%。"""
        import re

        from gui.styles.apply import _load_extra_qss

        raw = _load_extra_qss(theme)
        stray = [
            m.group(0)
            for m in re.finditer(r"%(?!\([a-z0-9\-]+\)s|%)", raw)
        ]
        assert not stray, f"存在未转义的百分号: {stray}"

    def test_covered_selectors_present(self):
        from gui.styles.apply import _load_extra_qss

        css = _load_extra_qss("dark")
        for selector in (
            "#TopNavBar",
            "#StatusBar",
            "#SearchResultCard",
            "#PreviewBody",
            "#ScoreBarTrack",
            "QPushButton#TagPill",
            "#SettingsHintBar",
            "#ErrorBanner",
            "#DiffAdded",
        ):
            assert selector in css, f"缺少 {selector}"


class TestMainWindowThemeWiring:
    """主题解析结果应被记录，供 _score_color 等使用。"""

    def test_resolved_theme_recorded(self, qapp, tmp_path, monkeypatch):
        from core.config import Config
        from gui.main_window import MainWindow

        config = Config()
        config.files_dir = tmp_path / "f"
        config.chroma_dir = tmp_path / "c"
        config.sqlite_path = tmp_path / "k.sqlite"
        config.logs_dir = tmp_path / "l"
        for path in (config.files_dir, config.chroma_dir, config.logs_dir):
            path.mkdir(parents=True, exist_ok=True)

        class _StubEmbedder:
            def is_available(self):
                return True

            def is_model_available(self):
                return True

        monkeypatch.setattr(MainWindow, "_build_embedder", lambda self, cfg: _StubEmbedder())
        monkeypatch.setattr(MainWindow, "_check_environment", lambda self: None)

        win = MainWindow(config)
        try:
            assert win._resolved_theme in ("dark", "light")
            # 分数色必须跟随主题，而不是硬编码深色
            color = win._score_color(0.9)
            assert color.startswith("#")
        finally:
            win.close()