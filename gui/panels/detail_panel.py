"""详情面板：预览 / 检索 / 元数据三标签页容器。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget

from gui.panels.metadata_tab import MetadataTab
from gui.panels.preview_tab import PreviewTab
from gui.panels.search_tab import SearchTab

TAB_PREVIEW = 0
TAB_SEARCH = 1
TAB_METADATA = 2


class DetailPanel(QTabWidget):
    """详情面板，承载三个标签页。

    Signals:
        searchRequested(str, int): 转发自 SearchTab。
        resultClicked(object): 转发自 SearchTab。
    """

    searchRequested = Signal(str, int)
    resultClicked = Signal(object)

    def __init__(self, default_top_k: int = 5, parent=None):
        super().__init__(parent)
        self.setObjectName("DetailPanel")

        self.preview_tab = PreviewTab(self)
        self.search_tab = SearchTab(default_top_k, self)
        self.metadata_tab = MetadataTab(self)

        self.addTab(self.preview_tab, "预览")
        self.addTab(self.search_tab, "检索")
        self.addTab(self.metadata_tab, "元数据")

        self.search_tab.searchRequested.connect(self.searchRequested)
        self.search_tab.resultClicked.connect(self.resultClicked)

    def switch_to_preview(self):
        self.setCurrentIndex(TAB_PREVIEW)

    def switch_to_search(self):
        self.setCurrentIndex(TAB_SEARCH)

    def switch_to_metadata(self):
        self.setCurrentIndex(TAB_METADATA)

    def set_search_enabled(self, enabled: bool) -> None:
        """启用/禁用语义检索。

        受限模式下禁用检索标签页并给出原因，而不是让用户点下去才报错。
        """
        self.setTabEnabled(TAB_SEARCH, enabled)
        if enabled:
            self.search_tab.set_unavailable_reason("")
        else:
            self.search_tab.set_unavailable_reason(
                "受限模式：未配置本地嵌入模型，语义检索不可用。"
                "请在设置 → 模型中配置后重试。"
            )
