"""嵌入模型切换对话框。

对应设计文档 §4.4：

- 步骤指示器：备份 → 重建 → 校验 → 完成（或回滚）
- 状态实时更新，每步骤完成显示 ✓
- 失败回滚提示用 ``--status-error`` 背景信息条
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from gui.widgets.step_indicator import StepIndicator

STEPS = ("备份", "重建", "校验", "完成")


class ModelSwitchDialog(QDialog):
    """嵌入模型切换对话框，编排备份→重建→校验→可回滚工作流。"""

    def __init__(self, config, model_manager, rebuild_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("切换嵌入模型")
        self.setObjectName("ModelSwitchDialog")
        self.resize(480, 320)
        self.config = config
        self.model_manager = model_manager
        self.rebuild_fn = rebuild_fn

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("<b>切换嵌入模型</b>")
        title.setObjectName("MessageDialogTitle")
        layout.addWidget(title)

        self.steps = StepIndicator(list(STEPS))
        layout.addWidget(self.steps)

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.new_model_input = QLineEdit(config.embedding_model)
        form.addRow("新模型名", self.new_model_input)
        layout.addLayout(form)

        self.hint = QLabel(
            "切换将执行：备份当前索引 → 重建 → 校验 → 可回滚。\n"
            "如重建失败将自动回滚到备份。"
        )
        self.hint.setWordWrap(True)
        self.hint.setObjectName("SettingsHintBar")
        layout.addWidget(self.hint)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusMessage")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox()
        switch_btn = QPushButton("开始切换")
        switch_btn.setProperty("btnType", "primary")
        switch_btn.clicked.connect(self._on_switch)
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("btnType", "secondary")
        cancel_btn.clicked.connect(self.reject)
        buttons.addButton(switch_btn, QDialogButtonBox.AcceptRole)
        buttons.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        layout.addWidget(buttons)

    def _on_switch(self) -> None:
        """执行切换流程。"""
        new_model = self.new_model_input.text().strip()
        if not new_model:
            QMessageBox.warning(self, "输入错误", "请输入新模型名")
            return

        self.steps.set_current_step(0)
        self.status_label.setText("正在备份并切换，请稍候...")

        result = self.model_manager.switch_model(new_model, self.rebuild_fn)

        if result.success:
            self.steps.set_current_step(3)
            self.status_label.setText(f"切换成功，备份位于：{result.backup_path}")
            QMessageBox.information(
                self, "成功", f"已切换到模型 {new_model}\n备份位于: {result.backup_path}"
            )
            self.accept()
        else:
            # §4.4 失败回滚提示用 --status-error 背景信息条
            self.hint.setObjectName("ErrorBanner")
            self.hint.style().unpolish(self.hint)
            self.hint.style().polish(self.hint)

            message = f"切换失败：{result.error}"
            if result.rolled_back:
                message += "\n已自动回滚到备份索引"
                self.status_label.setText("已回滚")
            else:
                self.status_label.setText("切换失败，未回滚")

            self.hint.setText(message)
            QMessageBox.critical(self, "失败", message)