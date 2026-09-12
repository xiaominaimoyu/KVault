"""浅色主题 QSS 模板与应用测试。"""

from pathlib import Path
from unittest.mock import MagicMock

from gui.styles.apply import apply_theme, interpolate
from gui.styles.variables import TOKENS_LIGHT

_STYLES_DIR = Path(__file__).resolve().parents[2] / "gui" / "styles"


def test_light_qss_file_exists():
    assert (_STYLES_DIR / "theme_light.qss").exists()


def test_light_qss_interpolates_without_residual():
    template = (_STYLES_DIR / "theme_light.qss").read_text(encoding="utf-8")
    result = interpolate(template, TOKENS_LIGHT)
    assert "%(" not in result


def test_apply_theme_light_returns_light():
    app = MagicMock()
    applied = apply_theme(app, "light")
    assert applied == "light"
    assert app.setStyleSheet.called
    qss = app.setStyleSheet.call_args[0][0]
    assert TOKENS_LIGHT["bg-vault"] in qss
    assert "%(" not in qss


def test_light_qss_same_placeholder_set_as_dark():
    import re

    dark = (_STYLES_DIR / "theme_dark.qss").read_text(encoding="utf-8")
    light = (_STYLES_DIR / "theme_light.qss").read_text(encoding="utf-8")
    dark_tokens = set(re.findall(r"%\(([^)]+)\)s", dark))
    light_tokens = set(re.findall(r"%\(([^)]+)\)s", light))
    assert dark_tokens == light_tokens
