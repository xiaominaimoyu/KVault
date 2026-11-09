"""gui/styles/apply.py 主题应用模块测试。

使用 mock 避免创建真实 QApplication（在无头环境中会阻塞）。
"""

from pathlib import Path
from unittest.mock import MagicMock

from core.config import AppearanceConfig
from gui.styles.apply import (
    apply_theme,
    current_tokens,
    interpolate,
    resolve_system_theme,
)
from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT


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


def test_resolve_system_theme_follows_color_scheme(monkeypatch):
    from PySide6.QtCore import Qt

    class FakeHints:
        def colorScheme(self):
            return Qt.ColorScheme.Light

    class FakeApp:
        @staticmethod
        def instance():
            return FakeApp()

        def styleHints(self):
            return FakeHints()

    monkeypatch.setattr("gui.styles.apply.QGuiApplication", FakeApp)
    assert resolve_system_theme() == "light"


def test_apply_theme_fallback_on_missing():
    app = MagicMock()
    applied = apply_theme(app, "nonexistent")
    assert applied == "dark"
    assert app.setStyleSheet.called


# ---- 外观参数 ----

def test_apply_theme_with_custom_accent():
    app = MagicMock()
    applied = apply_theme(
        app, "dark", AppearanceConfig(accent_custom="#FF0000")
    )
    assert applied == "dark"
    qss = app.setStyleSheet.call_args[0][0]
    assert "#FF0000" in qss
    assert current_tokens()["accent-primary"] == "#FF0000"


def test_apply_theme_light_tokens_are_active():
    app = MagicMock()
    apply_theme(app, "light")
    tokens = current_tokens()
    assert tokens["fg-primary"] == TOKENS_LIGHT["fg-primary"]
    assert tokens["bg-vault"] == TOKENS_LIGHT["bg-vault"]


def test_apply_theme_image_background_has_no_residual_placeholders():
    app = MagicMock()
    apply_theme(
        app,
        "dark",
        AppearanceConfig(background_mode="image", background_image="bg.png"),
    )
    qss = app.setStyleSheet.call_args[0][0]
    assert "%(" not in qss
    assert "transparent" in qss
    assert current_tokens()["bg-vault"] == "transparent"
