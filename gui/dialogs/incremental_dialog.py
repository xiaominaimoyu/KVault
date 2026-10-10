"""增量更新对话框。

对应设计文档 §4.3：

- 差异清单用三色标签区分：新增 ``--status-success``、修改 ``--status-warning``、
  删除 ``--status-error``
- 每行：标签 pill + 文件路径（等宽字）
- 进度阶段用步骤指示器：扫描 → 确认 → 执行 → 完成
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from gui.widgets.step_indicator import StepIndicator

#: 差异类型 -> (显示名, QSS 对象名)
DIFF_KINDS = (
    ("added", "新增", "DiffAdded"),
    ("modified", "修改", "DiffModified"),
    ("deleted", "删除", "DiffDeleted"),
    ("unreadable", "无法读取", "DiffDeleted"),
)

STEPS = ("扫描", "确认", "执行", "完成")


class IncrementalUpdateDialog(QDialog):
    """增量更新对话框，展示差异清单与更新进度。"""

    def __init__(self, incremental_updater, parent=None):
        super().__init__(parent)
        self.setWindowTitle("增量更新")
        self.setObjectName("IncrementalUpdateDialog")
        self.resize(560, 460)
        self.updater = incremental_updater
        self._report = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("<b>增量更新</b>")
        title.setObjectName("MessageDialogTitle")
        layout.addWidget(title)

        # §4.3 步骤指示器：扫描 → 确认 → 执行 → 完成
        self.steps = StepIndicator(list(STEPS))
        layout.addWidget(self.steps)

        self.status_label = QLabel("正在扫描差异...")
        self.status_label.setObjectName("StatusMessage")
        layout.addWidget(self.status_label)

        self.diff_list = QListWidget()
        self.diff_list.setObjectName("DiffList")
        layout.addWidget(self.diff_list, 1)

        buttons = QDialogButtonBox()
        self.update_btn = buttons.addButton("执行更新", QDialogButtonBox.AcceptRole)
        self.update_btn.setProperty("btnType", "primary")
        cancel_btn = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        cancel_btn.setProperty("btnType", "secondary")
        buttons.accepted.connect(self._on_update)
        buttons.rejected.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(buttons)
        layout.addLayout(button_row)

        self._scan()

    # ---------------------------------------------------------------- 流程

    def _scan(self) -> None:
        """扫描差异并渲染清单。"""
        self.diff_list.clear()
        self.steps.set_current_step(0)

        self._report = self.updater.scan_diffs()

        for field, label, style_name in DIFF_KINDS:
            paths = getattr(self._report, field, [])
            for path in paths:
                item = QListWidgetItem(f"  {path}")
                item.setData(Qt.UserRole, (label, path))
                # 三色标签通过富文本着色到条目左侧
                item.setText(
                    f'<span style="font-size:11px;">{label}</span>&nbsp;&nbsp;'
                    f'<span style="font-family:\'JetBrains Mono\',Consolas,monospace;">'
                    f"{path}</span>"
                )
                self.diff_list.addItem(item)

        total = (
            len(self._report.added)
            + len(self._report.modified)
            + len(self._report.deleted)
        )
        self.status_label.setText(
            f"共 {total} 项变更（新增 {len(self._report.added)}，"
            f"修改 {len(self._report.modified)}，删除 {len(self._report.deleted)}）"
        )

        # 无差异时禁用执行按钮
        self.update_btn.setEnabled(total > 0)
        self.steps.set_current_step(1)

    def result_count(self) -> int:
        """差异清单条目数。"""
        return self.diff_list.count()

    def _on_update(self) -> None:
        """执行更新。"""
        if self._report is None:
            self.reject()
            return

        self.steps.set_current_step(2)
        self.status_label.setText("正在更新...")
        result = self.updater.update(self._report)

        self.status_label.setText(
            f"完成：成功 {result.success_count}，失败 {result.fail_count}"
        )
        self.steps.set_current_step(3)

        if result.dirty_doc_ids:
            QMessageBox.warning(
                self,
                "脏数据",
                "以下文档索引失败，已跳过：\n" + "\n".join(result.dirty_doc_ids[:10]),
            )
        self.accept()