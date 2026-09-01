"""gui/styles/variables.py Token 系统测试。"""

from gui.styles.variables import (
    FONT_CONTENT,
    FONT_MONO,
    FONT_UI,
    RADIUS,
    SPACING,
    TEXT_LINE_HEIGHTS,
    TEXT_SIZES,
    TEXT_WEIGHTS,
    TOKENS_DARK,
    TOKENS_LIGHT,
    score_to_color,
)

_REQUIRED_COLOR_KEYS = {
    "bg-vault", "bg-surface", "bg-raised", "bg-inset",
    "fg-primary", "fg-secondary", "fg-muted", "fg-faint",
    "accent-primary", "accent-primary-dim", "accent-warm", "accent-warm-dim",
    "status-success", "status-warning", "status-error", "status-info",
}


def test_tokens_dark_has_all_color_keys():
    assert _REQUIRED_COLOR_KEYS <= set(TOKENS_DARK.keys())


def test_tokens_light_has_all_color_keys():
    assert _REQUIRED_COLOR_KEYS <= set(TOKENS_LIGHT.keys())


def test_spacing_values():
    assert SPACING == {"1": 4, "2": 8, "3": 12, "4": 16, "5": 20, "6": 24, "8": 32}


def test_radius_values():
    assert RADIUS == {"sm": 4, "md": 6, "lg": 8, "full": 9999}


def test_text_sizes():
    assert TEXT_SIZES == {"xs": 11, "sm": 13, "base": 14, "md": 15, "lg": 18, "xl": 22}


def test_text_line_heights():
    assert TEXT_LINE_HEIGHTS == {"xs": 16, "sm": 20, "base": 22, "md": 24, "lg": 28, "xl": 32}


def test_text_weights():
    assert TEXT_WEIGHTS == {"regular": 400, "medium": 500, "semibold": 600, "bold": 700}


def test_font_families_are_strings():
    assert isinstance(FONT_UI, str) and "sans-serif" in FONT_UI
    assert isinstance(FONT_MONO, str) and "monospace" in FONT_MONO
    assert isinstance(FONT_CONTENT, str) and "serif" in FONT_CONTENT


def test_score_to_color_high():
    assert score_to_color(0.9) == "status-success"
    assert score_to_color(0.8) == "status-success"


def test_score_to_color_mid():
    assert score_to_color(0.7) == "status-warning"
    assert score_to_color(0.5) == "status-warning"


def test_score_to_color_low():
    assert score_to_color(0.4) == "status-error"
    assert score_to_color(0.0) == "status-error"