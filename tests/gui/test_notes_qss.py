"""笔记库主题样式测试。"""

import re
from pathlib import Path

import pytest

from gui.styles.apply import _load_notes_qss, interpolate
from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

_STYLES = Path(__file__).resolve().parents[2] / "gui" / "styles"


@pytest.mark.parametrize("theme", ["dark", "light"])
class TestNotesQss:
    def test_file_exists(self, theme):
        assert (_STYLES / f"notes_{theme}.qss").is_file()

    def test_loads(self, theme):
        assert _load_notes_qss(theme).strip()

    def test_all_placeholders_resolve(self, theme):
        """不能残留未替换的 %(token)s 占位符。"""
        tokens = TOKENS_DARK if theme == "dark" else TOKENS_LIGHT
        rendered = interpolate(_load_notes_qss(theme), tokens)
        assert "%(" not in rendered

    def test_uses_only_known_tokens(self, theme):
        """引用的令牌必须在 variables.py 中已定义。"""
        known = set(TOKENS_DARK)
        used = set(re.findall(r"%\(([a-z0-9\-]+)\)s", _load_notes_qss(theme)))
        assert used <= known, f"未知令牌: {used - known}"

    def test_no_hardcoded_hex(self, theme):
        """颜色一律走令牌，禁止硬编码十六进制。"""
        content = _load_notes_qss(theme)
        # 去掉占位符后再检查是否还有裸色值
        stripped = re.sub(r"%\([a-z0-9\-]+\)s", "", content)
        assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", stripped)

    def test_covers_new_widgets(self, theme):
        """新增控件都必须有对应样式。"""
        content = _load_notes_qss(theme)
        for selector in (
            "#ViewSwitchBar",
            "#NoteListColumn",
            "#NoteTree",
            "#NoteHeader",
            "#MarkdownEditorText",
            "#NoteViewer",
            "#LinkPanelList",
            "#GraphView",
            "#QuickSwitcherList",
            "#WikiLinkCompleterPopup",
        ):
            assert selector in content, f"缺少 {selector} 的样式"

    def test_structure_matches_between_themes(self, theme):
        """深浅两套主题的选择器集合必须一致。"""
        dark = set(re.findall(r"^#[\w\-]+", _load_notes_qss("dark"), re.MULTILINE))
        light = set(re.findall(r"^#[\w\-]+", _load_notes_qss("light"), re.MULTILINE))
        assert dark == light


def test_notes_qss_is_appended(qapp):
    """apply_theme 的产物必须包含笔记库样式。"""
    from gui.styles.apply import apply_theme

    apply_theme(qapp, "dark")
    sheet = qapp.styleSheet()
    assert "#NoteTree" in sheet
    assert "#ViewSwitchBar" in sheet


def test_light_theme_notes_rules_present(qapp):
    from gui.styles.apply import apply_theme

    apply_theme(qapp, "light")
    assert "#NoteTree" in qapp.styleSheet()