"""主题应用模块：加载 QSS 模板、插值 Token、应用到 QApplication。

提供 apply_theme(app, theme, appearance) / current_tokens() /
resolve_system_theme() / interpolate(qss, tokens) 接口。
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from core.config import AppearanceConfig
from gui.styles.palettes import build_tokens
from gui.styles.variables import TOKENS_DARK

logger = logging.getLogger(__name__)

_STYLES_DIR = Path(__file__).resolve().parent
_QSS_CACHE: dict[str, str] = {}
_CURRENT_TOKENS: dict[str, str] = dict(TOKENS_DARK)


def _load_qss(theme: str) -> str:
    """读取对应主题的 QSS 模板文件，带缓存。"""
    if theme in _QSS_CACHE:
        return _QSS_CACHE[theme]
    qss_path = _STYLES_DIR / f"theme_{theme}.qss"
    if not qss_path.exists():
        raise FileNotFoundError(f"QSS file not found: {qss_path}")
    content = qss_path.read_text(encoding="utf-8")
    _QSS_CACHE[theme] = content
    return content


def interpolate(qss_template: str, tokens: dict[str, str]) -> str:
    """将 QSS 模板中的占位符替换为 Token 值。

    Args:
        qss_template: 含 %(token-name)s 占位符的 QSS 字符串。
        tokens: Token 字典（如 TOKENS_DARK）。

    Returns:
        插值后的 QSS 字符串，无残留占位符。
    """
    return qss_template % tokens


def current_tokens() -> dict[str, str]:
    """返回当前已应用主题的 Token 副本，供运行时取色。"""
    return dict(_CURRENT_TOKENS)


def resolve_system_theme() -> str:
    """检测操作系统暗色模式，返回 'dark' 或 'light'。

    通过 QGuiApplication.styleHints().colorScheme() 获取，
    Unknown 或未初始化时回退 'dark'。
    """
    try:
        app = QGuiApplication.instance()
        if app is None:
            return "dark"
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Light:
            return "light"
        elif scheme == Qt.ColorScheme.Dark:
            return "dark"
        else:
            return "dark"
    except Exception:
        return "dark"


def _remember(tokens: dict[str, str]) -> None:
    _CURRENT_TOKENS.clear()
    _CURRENT_TOKENS.update(tokens)


def _apply(app: QGuiApplication, theme: str, tokens: dict[str, str]) -> str:
    """应用主题；失败时回退深色，并始终同步 current_tokens。"""
    try:
        qss = interpolate(_load_qss(theme), tokens)
        app.setStyleSheet(qss)
        _remember(tokens)
        logger.info("theme applied: %s", theme)
        return theme
    except Exception as exc:
        logger.warning(
            "theme application failed for '%s': %s, falling back to dark", theme, exc
        )

    if theme != "dark":
        return _apply(app, "dark", build_tokens("dark"))
    app.setStyleSheet("")
    _remember(dict(TOKENS_DARK))
    return "dark"


def apply_theme(
    app: QGuiApplication,
    theme: str = "dark",
    appearance: AppearanceConfig | None = None,
) -> str:
    """应用指定主题与外观设置到 QApplication。

    Args:
        app: QApplication 实例。
        theme: 'dark' / 'light' / 'system'。
        appearance: 外观配置；缺省使用默认预设与背景。

    Returns:
        实际应用的主题名（'dark' 或 'light'）。
    """
    if theme == "system":
        return apply_theme(app, resolve_system_theme(), appearance)

    if theme not in ("dark", "light"):
        logger.warning("unknown theme '%s', falling back to dark", theme)
        theme = "dark"

    return _apply(app, theme, build_tokens(theme, appearance))
