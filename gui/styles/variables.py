"""Vault Standard 设计 Token 定义。

所有色彩、间距、圆角、字体、字号常量集中管理，
QSS 模板通过 %(token-name)s 占位符引用。
"""

from __future__ import annotations

TOKENS_DARK: dict[str, str] = {
    "bg-vault": "#0F1115",
    "bg-surface": "#161922",
    "bg-raised": "#1E222C",
    "bg-inset": "#0C0E13",
    "fg-primary": "#E8EAED",
    "fg-secondary": "#9BA1AC",
    "fg-muted": "#5C6370",
    "fg-faint": "#3A4049",
    "accent-primary": "#2DD4BF",
    "accent-primary-dim": "#1A8B7E",
    "accent-primary-hover": "#3DEDCF",
    "accent-warm": "#F5A623",
    "accent-warm-dim": "#B87714",
    "status-success": "#34D399",
    "status-warning": "#FBBF24",
    "status-error": "#F87171",
    "status-info": "#60A5FA",
}

TOKENS_LIGHT: dict[str, str] = {
    "bg-vault": "#F7F8FA",
    "bg-surface": "#FFFFFF",
    "bg-raised": "#F1F3F5",
    "bg-inset": "#E8EBEE",
    "fg-primary": "#1A1D23",
    "fg-secondary": "#5C6370",
    "fg-muted": "#9BA1AC",
    "fg-faint": "#D1D5DB",
    "accent-primary": "#0D9488",
    "accent-primary-dim": "#5EEAD4",
    "accent-primary-hover": "#14B8A6",
    "accent-warm": "#D97706",
    "accent-warm-dim": "#FDE68A",
    "status-success": "#059669",
    "status-warning": "#D97706",
    "status-error": "#DC2626",
    "status-info": "#2563EB",
}

SPACING: dict[str, int] = {
    "1": 4,
    "2": 8,
    "3": 12,
    "4": 16,
    "5": 20,
    "6": 24,
    "8": 32,
}

RADIUS: dict[str, int] = {
    "sm": 4,
    "md": 6,
    "lg": 8,
    "full": 9999,
}

FONT_UI = '"Inter", "Microsoft YaHei UI", "Segoe UI", sans-serif'
FONT_MONO = '"JetBrains Mono", "Cascadia Code", "Consolas", monospace'
FONT_CONTENT = '"Inter", "Source Han Serif SC", "Noto Serif CJK SC", serif'

TEXT_SIZES: dict[str, int] = {
    "xs": 11,
    "sm": 13,
    "base": 14,
    "md": 15,
    "lg": 18,
    "xl": 22,
}

TEXT_LINE_HEIGHTS: dict[str, int] = {
    "xs": 16,
    "sm": 20,
    "base": 22,
    "md": 24,
    "lg": 28,
    "xl": 32,
}

TEXT_WEIGHTS: dict[str, int] = {
    "regular": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
}


def score_to_color(score: float) -> str:
    """将相似度分数映射为状态色 Token 名。

    Args:
        score: 相似度分数 [0.0, 1.0]。

    Returns:
        Token 名：'status-success' / 'status-warning' / 'status-error'。
    """
    if score >= 0.8:
        return "status-success"
    elif score >= 0.5:
        return "status-warning"
    else:
        return "status-error"