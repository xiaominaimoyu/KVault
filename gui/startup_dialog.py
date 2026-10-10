"""启动检查对话框（兼容转发）。

设计文档 §9.3 要求该对话框位于 ``gui/dialogs/startup_dialog.py``；
此文件仅为向后兼容保留，实际实现已迁移。
"""

from gui.dialogs.startup_dialog import StartupDialog

__all__ = ["StartupDialog"]