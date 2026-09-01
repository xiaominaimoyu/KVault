from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
)

from core.startup_check import CheckResult
from gui.styles.variables import TOKENS_DARK


class StartupDialog(QDialog):
    def __init__(self, results: list[CheckResult], parent=None):
        super().__init__(parent)
        self.setWindowTitle("KVault 启动检查")
        self.setMinimumSize(500, 400)
        self.results = results
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        title_label = QLabel("<h2>KVault 启动检查</h2>")
        layout.addWidget(title_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        content_widget = QFrame()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)

        has_error = False
        for result in self.results:
            row = QFrame()
            row.setProperty("panelType", "card")
            row_layout = QVBoxLayout(row)
            row_layout.setSpacing(4)

            header = QHBoxLayout()
            status_icon = QLabel()
            if result.passed:
                status_icon.setText("✓")
                status_icon.setStyleSheet(
                    f"font-size: 18px; color: {TOKENS_DARK['status-success']}; font-weight: bold;"
                )
            else:
                has_error = True
                status_icon.setText("✗")
                status_icon.setStyleSheet(
                    f"font-size: 18px; color: {TOKENS_DARK['status-error']}; font-weight: bold;"
                )
            header.addWidget(status_icon)
            header.addWidget(QLabel(f"<b>{result.name}</b>"))
            header.addStretch()
            row_layout.addLayout(header)

            msg_label = QLabel(result.message)
            msg_label.setStyleSheet(f"color: {TOKENS_DARK['fg-secondary']};")
            row_layout.addWidget(msg_label)

            if result.suggestion:
                suggest_label = QLabel(f"<i>{result.suggestion}</i>")
                suggest_label.setStyleSheet(
                    f"color: {TOKENS_DARK['fg-muted']}; font-size: 13px;"
                )
                row_layout.addWidget(suggest_label)

            content_layout.addWidget(row)

        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)

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
        self.setLayout(layout)
