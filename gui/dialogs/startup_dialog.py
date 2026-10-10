"""启动检查对话框。

对应设计文档 §4.2：

- 背景 ``--bg-surface``、卡片 ``--bg-raised`` + ``--radius-md``
- 通过/失败图标为 24px 圆形，✓ 用 ``--status-success``、✗ 用 ``--status-error``
- 建议文字 ``--text-sm`` ``--fg-secondary`` 斜体
- 重试为主按钮、跳过为次要按钮
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.startup_check import CheckResult
from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT


class StartupDialog(QDialog):
    """首启环境检查结果报告。"""

    def __init__(self, results: list[CheckResult], parent=None, theme: str = "dark"):
        super().__init__(parent)
        self.setWindowTitle("KVault 启动检查")
        self.setObjectName("StartupDialog")
        self.setMinimumSize(520, 420)
        self.results = results
        self._theme = theme
        self._init_ui()

    # ---------------------------------------------------------------- 内部

    def _tokens(self) -> dict:
        return TOKENS_DARK if self._theme == "dark" else TOKENS_LIGHT

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title_label = QLabel("<b>KVault 启动检查</b>")
        title_label.setObjectName("MessageDialogTitle")
        layout.addWidget(title_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(0, 0, 0, 0)

        has_error = False
        for result in self.results:
            content_layout.addWidget(self._build_card(result))
            if not result.passed:
                has_error = True

        content_layout.addStretch(1)
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()

        if has_error:
            retry_btn = QPushButton("重试")
            retry_btn.clicked.connect(self.accept)
            retry_btn.setProperty("btnType", "primary")
            button_row.addWidget(retry_btn)

            skip_btn = QPushButton("跳过继续")
            skip_btn.clicked.connect(self.reject)
            skip_btn.setProperty("btnType", "secondary")
            button_row.addWidget(skip_btn)
        else:
            ok_btn = QPushButton("确定")
            ok_btn.clicked.connect(self.accept)
            ok_btn.setProperty("btnType", "primary")
            button_row.addWidget(ok_btn)

        layout.addLayout(button_row)

    def _build_card(self, result: CheckResult) -> QFrame:
        """构建单条检查结果卡片。"""
        tokens = self._tokens()
        card = QFrame()
        card.setObjectName("StartupCheckCard")

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(4)
        card_layout.setContentsMargins(12, 12, 12, 12)

        header = QHBoxLayout()
        header.setSpacing(8)

        # §4.2 通过/失败图标：24px 圆形背景
        color = tokens["status-success"] if result.passed else tokens["status-error"]
        icon = QLabel("✓" if result.passed else "✗")
        icon.setFixedSize(24, 24)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f"background-color: {color}; color: {tokens['bg-vault']};"
            "border-radius: 12px; font-weight: bold;"
        )
        header.addWidget(icon)

        name_label = QLabel(f"<b>{result.name}</b>")
        name_label.setStyleSheet(f"color: {tokens['fg-primary']};")
        header.addWidget(name_label)
        header.addStretch()
        card_layout.addLayout(header)

        msg_label = QLabel(result.message)
        msg_label.setObjectName("StartupCheckSuggestion")
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(f"color: {tokens['fg-secondary']}; font-size: 13px;")
        card_layout.addWidget(msg_label)

        if result.suggestion:
            suggest_label = QLabel(f"<i>{result.suggestion}</i>")
            suggest_label.setObjectName("StartupCheckSuggestion")
            suggest_label.setWordWrap(True)
            suggest_label.setStyleSheet(
                f"color: {tokens['fg-muted']}; font-size: 13px; font-style: italic;"
            )
            card_layout.addWidget(suggest_label)

        return card