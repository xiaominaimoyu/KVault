"""配色预设与主题 Token 派生。

在 variables.py 的深/浅色基底之上，叠加用户选择的强调色与背景设置，
输出可直接用于 QSS 插值的完整 Token 表。
"""

from __future__ import annotations

import re

from core.config import AppearanceConfig
from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

ACCENT_PRESETS: dict[str, dict[str, str]] = {
    "vault-teal": {"label": "青碧", "dark": "#2DD4BF", "light": "#0D9488"},
    "ocean-blue": {"label": "海蓝", "dark": "#60A5FA", "light": "#2563EB"},
    "indigo": {"label": "靛紫", "dark": "#818CF8", "light": "#4F46E5"},
    "violet": {"label": "罗兰", "dark": "#C084FC", "light": "#7C3AED"},
    "rose": {"label": "玫瑰", "dark": "#FB7185", "light": "#E11D48"},
    "emerald": {"label": "翡翠", "dark": "#34D399", "light": "#059669"},
}

PRESET_ORDER: list[str] = list(ACCENT_PRESETS)
DEFAULT_PRESET = "vault-teal"
DARK_TEXT = "#0F1115"

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def is_hex_color(value: str) -> bool:
    """判断是否为 #RRGGBB 格式的完整颜色值。"""
    return bool(value) and bool(_HEX_COLOR_RE.match(value))


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """将 #RRGGBB 转为 (r, g, b)。非法值回退黑色。"""
    if not is_hex_color(value):
        return (0, 0, 0)
    text = value.lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """将 (r, g, b) 转为大写 #RRGGBB。"""
    r, g, b = (max(0, min(255, int(channel))) for channel in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(color_a: str, color_b: str, weight: float) -> str:
    """按 weight 比例混合两色，weight 是 color_b 的占比。"""
    ratio = max(0.0, min(1.0, weight))
    a = hex_to_rgb(color_a)
    b = hex_to_rgb(color_b)
    return rgb_to_hex(
        tuple(round(a[i] + (b[i] - a[i]) * ratio) for i in range(3))
    )


def lighten(color: str, amount: float) -> str:
    return mix(color, "#FFFFFF", amount)


def darken(color: str, amount: float) -> str:
    return mix(color, "#000000", amount)


def relative_luminance(color: str) -> float:
    """WCAG 相对亮度，用于决定前景文字色。"""
    channels = []
    for raw in hex_to_rgb(color):
        value = raw / 255
        channels.append(
            value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        )
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_text(color: str) -> str:
    """在白色与深色文字之间选择对比度更高的一个。"""
    return "#FFFFFF" if relative_luminance(color) < 0.6 else DARK_TEXT


def rgba_str(color: str, alpha: float) -> str:
    """输出 QSS 可用的 rgba 字符串。"""
    red, green, blue = hex_to_rgb(color)
    safe_alpha = max(0.0, min(1.0, alpha))
    return f"rgba({red}, {green}, {blue}, {safe_alpha:.2f})"


def resolve_accent(theme: str, appearance: AppearanceConfig) -> str:
    """解析当前生效的强调色：自定义色优先，其次预设。"""
    custom = appearance.accent_custom.strip()
    if is_hex_color(custom):
        return custom.upper()
    preset = ACCENT_PRESETS.get(appearance.accent_preset, ACCENT_PRESETS[DEFAULT_PRESET])
    return preset[theme if theme == "light" else "dark"]


def resolve_base_theme(theme: str, appearance: AppearanceConfig) -> str:
    """纯色背景过亮时切换为浅色基底，保证文字对比度。"""
    if appearance.background_mode != "color":
        return theme
    color = appearance.background_color
    if is_hex_color(color) and relative_luminance(color) > 0.6:
        return "light"
    return theme


def build_tokens(
    theme: str = "dark", appearance: AppearanceConfig | None = None
) -> dict[str, str]:
    """构建完整 Token 表。

    Args:
        theme: 基础主题（dark / light）。
        appearance: 外观设置，缺省使用默认预设。

    Returns:
        可直接用于 QSS 插值的 Token 字典，所有值均为字符串。
    """
    appearance = appearance or AppearanceConfig()
    base_theme = resolve_base_theme(theme, appearance)
    base = TOKENS_DARK if base_theme == "dark" else TOKENS_LIGHT
    tokens = dict(base)

    accent = resolve_accent(base_theme, appearance)
    tokens["accent-primary"] = accent
    tokens["accent-primary-hover"] = lighten(accent, 0.18)
    tokens["accent-primary-dim"] = darken(accent, 0.22)
    tokens["accent-rgb"] = ", ".join(str(channel) for channel in hex_to_rgb(accent))
    tokens["accent-fg"] = contrast_text(accent)

    mode = appearance.background_mode
    if mode == "color" and is_hex_color(appearance.background_color):
        color = appearance.background_color.upper()
        tokens["bg-vault"] = color
        tokens["bg-window"] = color
        if base_theme == "light":
            tokens["bg-surface"] = mix(color, "#FFFFFF", 0.55)
            tokens["bg-raised"] = mix(color, "#FFFFFF", 0.30)
            tokens["bg-inset"] = darken(color, 0.06)
        else:
            tokens["bg-surface"] = lighten(color, 0.06)
            tokens["bg-raised"] = lighten(color, 0.12)
            tokens["bg-inset"] = darken(color, 0.25)
    elif mode == "image":
        alpha = max(0.3, min(1.0, appearance.surface_alpha))
        tokens["bg-vault"] = "transparent"
        tokens["bg-surface"] = rgba_str(base["bg-surface"], alpha)
        tokens["bg-raised"] = rgba_str(base["bg-raised"], min(1.0, alpha + 0.04))
        tokens["bg-inset"] = rgba_str(base["bg-inset"], max(0.3, alpha - 0.10))

    return tokens
