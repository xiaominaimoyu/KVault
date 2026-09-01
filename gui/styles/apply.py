"""主题应用模块：加载 QSS 模板、插值 Token、应用到 QApplication。

提供 apply_theme(app, theme) / resolve_system_theme() / interpolate(qss, tokens) 接口。
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QGuiApplication

from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

logger = logging.getLogger(__name__)

_STYLES_DIR = Path(__file__).resolve().parent
_QSS_CACHE: dict[str, str] = {}


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
        if scheme == QGuiApplication.ColorScheme.Light:
            return "light"
        elif scheme == QGuiApplication.ColorScheme.Dark:
            return "dark"
        else:
            return "dark"
    except Exception:
        return "dark"


def apply_theme(app: QGuiApplication, theme: str = "dark") -> str:
    """应用指定主题到 QApplication。

    Args:
        app: QApplication 实例。
        theme: 'dark' / 'light' / 'system'。

    Returns:
        实际应用的主题名（'dark' 或 'light'）。
    """
    if theme == "system":
        resolved = resolve_system_theme()
        return apply_theme(app, resolved)

    if theme not in ("dark", "light"):
        logger.warning("unknown theme '%s', falling back to dark", theme)
        theme = "dark"

    tokens = TOKENS_DARK if theme == "dark" else TOKENS_LIGHT
    qss_theme = theme

    try:
        qss_template = _load_qss(qss_theme)
        qss = interpolate(qss_template, tokens)
        app.setStyleSheet(qss)
        logger.info("theme applied: %s", theme)
        return theme
    except FileNotFoundError:
        logger.warning("QSS file for theme '%s' not found, falling back to dark", theme)
        try:
            qss_template = _load_qss("dark")
            qss = interpolate(qss_template, TOKENS_DARK)
            app.setStyleSheet(qss)
            return "dark"
        except Exception:
            logger.error("even dark theme QSS failed, applying empty stylesheet")
            app.setStyleSheet("")
            return "dark"
    except Exception as e:
        logger.warning("theme application failed: %s, falling back to dark", e)
        try:
            qss_template = _load_qss("dark")
            qss = interpolate(qss_template, TOKENS_DARK)
            app.setStyleSheet(qss)
            return "dark"
        except Exception:
            app.setStyleSheet("")
            return "dark"