"""P10 最终打磨：P7/P8 控件 QSS 覆盖检查。"""

from pathlib import Path

_STYLES_DIR = Path(__file__).resolve().parents[2] / "gui" / "styles"

# 设计文档要求的控件 selector 占位符
_REQUIRED_SELECTORS = [
    "ViewToggleButton",
    "FloatingActionBar",
    "FloatingActionBarInfo",
    "DropOverlay",
    "DocCard",
    "DocCardName",
    "DocCardMeta",
    "EmptyState",
    "StepIndicator",
    "StepLabel",
    "ScoreBar",
]


def test_dark_qss_covers_new_widget_selectors():
    qss = (_STYLES_DIR / "theme_dark.qss").read_text(encoding="utf-8")
    missing = [sel for sel in _REQUIRED_SELECTORS if f"#{sel}" not in qss]
    assert not missing, f"深色主题缺少样式: {missing}"


def test_light_qss_covers_new_widget_selectors():
    qss = (_STYLES_DIR / "theme_light.qss").read_text(encoding="utf-8")
    missing = [sel for sel in _REQUIRED_SELECTORS if f"#{sel}" not in qss]
    assert not missing, f"浅色主题缺少样式: {missing}"
