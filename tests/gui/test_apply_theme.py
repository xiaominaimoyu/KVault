"""gui/styles/apply.py 主题应用模块测试。

使用 mock 避免创建真实 QApplication（在无头环境中会阻塞）。
"""

from pathlib import Path
from unittest.mock import MagicMock

from gui.styles.apply import apply_theme, interpolate, resolve_system_theme
from gui.styles.variables import TOKENS_DARK


def test_interpolate_replaces_placeholders():
    template = "color: %(fg-primary)s; background: %(bg-vault)s;"
    result = interpolate(template, TOKENS_DARK)
    assert "%(" not in result
    assert TOKENS_DARK["fg-primary"] in result
    assert TOKENS_DARK["bg-vault"] in result


def test_interpolate_no_residual_placeholders():
    qss_path = Path(__file__).resolve().parents[2] / "gui" / "styles" / "theme_dark.qss"
    template = qss_path.read_text(encoding="utf-8")
    result = interpolate(template, TOKENS_DARK)
    assert "%(" not in result


def test_apply_theme_dark():
    app = MagicMock()
    applied = apply_theme(app, "dark")
    assert applied == "dark"
    assert app.setStyleSheet.called
    qss = app.setStyleSheet.call_args[0][0]
    assert len(qss) > 100
    assert "%(" not in qss


def test_apply_theme_system():
    app = MagicMock()
    applied = apply_theme(app, "system")
    assert applied in ("dark", "light")
    assert app.setStyleSheet.called


def test_resolve_system_theme_returns_valid():
    result = resolve_system_theme()
    assert result in ("dark", "light")


def test_apply_theme_fallback_on_missing():
    app = MagicMock()
    applied = apply_theme(app, "nonexistent")
    assert applied == "dark"
    assert app.setStyleSheet.called
