"""icons 图标系统测试。"""

from pathlib import Path

from gui.styles.icons import ICON_NAMES, icon

_ICONS_DIR = Path(__file__).resolve().parents[2] / "gui" / "styles" / "icons"


def test_icon_files_exist_for_all_names():
    for name in ICON_NAMES:
        assert (_ICONS_DIR / f"{name}.svg").exists(), f"缺少图标 {name}.svg"


def test_icon_names_cover_design_doc_mapping():
    expected = {
        "upload", "settings", "search", "file-text", "trash-2",
        "folder", "folder-plus", "folder-input", "tag", "tags",
        "refresh-cw", "external-link",
    }
    assert expected <= set(ICON_NAMES)


def test_icon_returns_non_empty_qicon(qapp):
    ic = icon("upload")
    assert not ic.isNull()
    assert not ic.pixmap(16, 16).isNull()


def test_icon_respects_size(qapp):
    ic = icon("search", size=20)
    pm = ic.pixmap(20, 20)
    assert pm.width() == 20
    assert pm.height() == 20


def test_unknown_icon_returns_null(qapp):
    assert icon("no-such-icon").isNull()


def test_svg_template_uses_stroke_color_placeholder():
    svg = (_ICONS_DIR / "upload.svg").read_text(encoding="utf-8")
    # 模板使用占位符，渲染时替换为具体色值
    assert "{{COLOR}}" in svg or "currentColor" in svg


def test_svg_is_lucide_style_24_viewbox():
    svg = (_ICONS_DIR / "search.svg").read_text(encoding="utf-8")
    assert 'viewBox="0 0 24 24"' in svg
    assert 'stroke-width="2"' in svg
    assert 'stroke-linecap="round"' in svg
