"""GUI 测试共享夹具。

为所有 GUI 测试提供唯一的 QApplication 实例，
并强制使用 offscreen 平台插件以支持无头运行。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """会话级 QApplication，确保 QWidget 可在测试中构造。"""
    app = QApplication.instance() or QApplication([])
    yield app
