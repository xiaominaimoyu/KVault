"""深色主题 QSS 模板测试：验证占位符与 Token 键匹配。"""

import re
from pathlib import Path

from gui.styles.variables import TOKENS_DARK


def _load_qss() -> str:
    qss_path = Path(__file__).resolve().parents[2] / "gui" / "styles" / "theme_dark.qss"
    return qss_path.read_text(encoding="utf-8")


def _extract_placeholders(qss: str) -> set[str]:
    return set(re.findall(r"%\(([\w-]+)\)s", qss))


def test_qss_file_exists_and_non_empty():
    qss = _load_qss()
    assert len(qss) > 0


def test_all_placeholders_have_token_keys():
    qss = _load_qss()
    placeholders = _extract_placeholders(qss)
    missing = placeholders - set(TOKENS_DARK.keys())
    assert missing == set(), f"Missing token keys for placeholders: {missing}"


def test_qss_covers_main_controls():
    qss = _load_qss()
    for selector in [
        "QMainWindow", "QWidget", "QLabel", "QPushButton",
        "QLineEdit", "QComboBox", "QTableWidget", "QHeaderView",
        "QTreeWidget", "QListWidget", "QTabWidget", "QTabBar",
        "QProgressBar", "QMenu", "QScrollBar", "QSplitter",
        "QDialog", "QCheckBox", "QRadioButton", "QSpinBox",
        "QGroupBox", "QToolTip", "QTextBrowser",
    ]:
        assert selector in qss, f"QSS missing selector: {selector}"


def test_primary_button_style():
    qss = _load_qss()
    assert 'btnType="primary"' in qss
    assert 'btnType="secondary"' in qss
    assert 'btnType="icon"' in qss


def test_no_hardcoded_hex_colors():
    qss = _load_qss()
    placeholders = _extract_placeholders(qss)
    lines = qss.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("/*") or stripped.startswith("*") or stripped.endswith("*/"):
            continue
        if stripped.startswith("background-image"):
            continue
        hex_matches = re.findall(r"#(?:[0-9A-Fa-f]{3,8})\b", stripped)
        for hex_val in hex_matches:
            if hex_val in ("#FFFFFF", "#fff"):
                continue
            assert any(ph in stripped for ph in placeholders), (
                f"Line {i+1}: hardcoded color '{hex_val}' without placeholder: {stripped}"
            )