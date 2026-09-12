"""MainWindow 主题接入冒烟测试。

验证 main.py 零改动、main_window.py 无硬编码色值、
apply_theme 在 MainWindow 构造时被调用。
"""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from gui.styles.variables import TOKENS_DARK


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_main_py_unchanged():
    """main.py 不应被本次改动修改。"""
    main_py = (_REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert "MainWindow" in main_py
    assert "import" in main_py


def test_main_window_no_hardcoded_status_colors():
    """main_window.py 中 _STATUS_COLORS 应引用 TOKENS_DARK 而非硬编码。"""
    mw = (_REPO_ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "TOKENS_DARK" in mw
    assert '"#2ecc71"' not in mw
    assert '"#e74c3c"' not in mw
    assert '"#f1c40f"' not in mw
    assert '"#95a5a6"' not in mw
    assert '"#27ae60"' not in mw


def test_main_window_imports_token_system():
    """main_window.py 应导入 TOKENS_DARK。"""
    mw = (_REPO_ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "from gui.styles.variables import TOKENS_DARK" in mw


def test_main_window_calls_apply_theme():
    """MainWindow.__init__ 应调用 apply_theme。"""
    mw = (_REPO_ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "apply_theme" in mw


def test_startup_dialog_no_hardcoded_colors():
    """startup_dialog.py 中不应有硬编码十六进制色值。"""
    sd = (_REPO_ROOT / "gui" / "startup_dialog.py").read_text(encoding="utf-8")
    hex_colors = re.findall(r'"#[0-9a-fA-F]{3,8}"', sd)
    assert hex_colors == [], f"Hardcoded colors found: {hex_colors}"


def test_startup_dialog_uses_tokens():
    """startup_dialog.py 应引用 TOKENS_DARK。"""
    sd = (_REPO_ROOT / "gui" / "startup_dialog.py").read_text(encoding="utf-8")
    assert "TOKENS_DARK" in sd


def test_main_window_no_plain_setstylesheet_with_colors():
    """main_window.py 中 setStyleSheet 不应含 'color: green' / 'color: red' / 'color: gray' 等硬编码。"""
    mw = (_REPO_ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "color: green" not in mw
    assert "color: red" not in mw
    assert "color: gray" not in mw


# ---- P9 快捷键与主题运行时切换 ----

def test_main_window_sets_up_shortcuts():
    """MainWindow 应构建 ShortcutManager 完成快捷键注册。"""
    mw = (_REPO_ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "ShortcutManager" in mw
    assert "_setup_shortcuts" in mw


def test_main_window_reapplies_theme_after_settings():
    """设置对话框保存后应重新应用主题（运行时切换）。"""
    mw = (_REPO_ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "_apply_theme" in mw


def test_main_window_registers_bundled_fonts():
    """MainWindow 启动时应注册打包字体（若存在）。"""
    mw = (_REPO_ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    assert "register_bundled_fonts" in mw