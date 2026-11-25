"""知识图谱视图（Obsidian 风格）。

用 :class:`QGraphicsView` 绘制笔记之间的链接网络：

- **力导向布局** —— 自实现的 Fruchterman-Reingold 变体（numpy 向量化），
  斥力让节点散开、引力把相连节点拉近、向心力把整张图收成一个圆盘。
- **视觉风格** —— 深色画布、细小圆点、半透明细连线；节点按顶层文件夹自动
  分配颜色组，大小反映链接数量。
- **交互** —— 悬停高亮节点及其邻居、其余淡出；滚轮缩放时标签渐显；
  点击节点打开笔记；拖拽空白处平移。
- **右上角浮动设置面板** —— 筛选（搜索 / 孤立文件）、颜色组（点击隐藏/显示）、
  外观（标签、节点大小、连线粗细、标签阈值）、力度（向心力 / 排斥力 / 吸引力 /
  连线长度，调整后平滑过渡到新布局）。

大型笔记库的图会退化成一团毛球，因此对节点数设有上限，超出时只绘制链接数
最高的节点，避免界面卡死。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import ClassVar

import numpy as np
from PySide6.QtCore import (
    QEasingCurve,
    QLineF,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

#: 超过该节点数时只保留链接数最高的部分，避免布局退化
MAX_NODES = 300

#: 布局迭代上限
_MAX_ITERATIONS = 260

#: 颜色组调色板（参考 Obsidian 关系图谱的高饱和点色）
GROUP_PALETTE = [
    "#F08C2E",  # 橙
    "#E6DB2E",  # 黄
    "#3D5AFE",  # 蓝
    "#2FCB4E",  # 绿
    "#EF3B3B",  # 红
    "#A970FF",  # 紫
    "#22C3D6",  # 青
    "#F062A8",  # 粉
]

#: 图谱专用配色（比全局主题更中性，贴近 Obsidian 关系图谱）
GRAPH_THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#1B1B1D",
        "node": "#A8A8AD",
        "edge": "#8A8A90",
        "label": "#DCDDDE",
        "accent": "#8B6CEF",
        "panel-bg": "#232326",
        "panel-border": "#34343A",
        "panel-fg": "#DCDDDE",
        "panel-muted": "#8E8E96",
        "input-bg": "#1B1B1D",
        "track": "#4A4A52",
        "knob": "#FFFFFF",
        "knob-border": "#FFFFFF",
    },
    "light": {
        "bg": "#FAFAFA",
        "node": "#7C7C84",
        "edge": "#9A9AA2",
        "label": "#2E2E33",
        "accent": "#7B5CE6",
        "panel-bg": "#FFFFFF",
        "panel-border": "#E2E2E6",
        "panel-fg": "#2E2E33",
        "panel-muted": "#7C7C84",
        "input-bg": "#F3F3F5",
        "track": "#D0D0D6",
        "knob": "#FFFFFF",
        "knob-border": "#B8B8C0",
    },
}

ROOT_GROUP = "根目录"


@dataclass
class GraphSettings:
    """图谱的可调参数，滑块值统一归一化到 0~1。"""

    show_orphans: bool = True
    show_labels: bool = True
    node_size: float = 0.5
    link_width: float = 0.35
    text_fade: float = 0.5
    center_force: float = 0.5
    repel_force: float = 0.5
    link_force: float = 0.5
    link_distance: float = 0.5


# ====================================================================== 节点


class NoteNode(QGraphicsObject):
    """图中的一个笔记节点。"""

    def __init__(self, path: str, title: str, degree: int, radius: float):
        super().__init__()
        self.path = path
        self.title = title
        self.degree = degree
        self.group = ROOT_GROUP
        self._radius = radius
        self._pos = QPointF(0.0, 0.0)
        self._color = QColor(GRAPH_THEMES["dark"]["node"])
        self._accent = QColor(GRAPH_THEMES["dark"]["accent"])
        self._dim = False
        self._hovered = False
        self._hover_callback = None
        self.setAcceptHoverEvents(True)
        self.setToolTip(title)
        self.setCursor(Qt.PointingHandCursor)

    # ------------------------------------------------------------ 几何

    def boundingRect(self) -> QRectF:
        # 预留光晕空间
        r = self._radius * 2.2
        return QRectF(self._pos.x() - r, self._pos.y() - r, r * 2, r * 2)

    def shape(self):
        from PySide6.QtGui import QPainterPath

        path = QPainterPath()
        hit = max(self._radius, 4.0)
        path.addEllipse(self._pos, hit, hit)
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = QColor(self._color)
        if self._dim:
            color.setAlphaF(0.12)
        painter.setPen(Qt.NoPen)

        if self._hovered:
            halo = QRadialGradient(self._pos, self._radius * 2.2)
            glow = QColor(self._accent)
            glow.setAlpha(110)
            halo.setColorAt(0.0, glow)
            glow.setAlpha(0)
            halo.setColorAt(1.0, glow)
            painter.setBrush(QBrush(halo))
            painter.drawEllipse(self._pos, self._radius * 2.2, self._radius * 2.2)
            color = QColor(self._accent)

        painter.setBrush(QBrush(color))
        painter.drawEllipse(self._pos, self._radius, self._radius)

    # ------------------------------------------------------------ 状态

    def position(self) -> QPointF:
        return self._pos

    def set_position(self, point: QPointF) -> None:
        self.prepareGeometryChange()
        self._pos = QPointF(point)
        self.update()

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_accent(self, color: QColor) -> None:
        self._accent = QColor(color)

    def set_radius(self, radius: float) -> None:
        self.prepareGeometryChange()
        self._radius = radius
        self.update()

    def radius(self) -> float:
        return self._radius

    def set_dim(self, dim: bool) -> None:
        if dim != self._dim:
            self._dim = dim
            self.update()

    def is_dim(self) -> bool:
        return self._dim

    def set_hover_callback(self, callback) -> None:
        self._hover_callback = callback

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        if self._hover_callback:
            self._hover_callback(self.path)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        if self._hover_callback:
            self._hover_callback(None)
        self.update()
        super().hoverLeaveEvent(event)


# ====================================================================== 面板小部件


class ToggleSwitch(QAbstractButton):
    """Obsidian 风格的胶囊开关。"""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self._on = QColor(GRAPH_THEMES["dark"]["accent"])
        self._off = QColor(GRAPH_THEMES["dark"]["track"])
        self._knob = QColor("#FFFFFF")

    def set_colors(self, on: str, off: str, knob: str) -> None:
        self._on, self._off, self._knob = QColor(on), QColor(off), QColor(knob)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(30, 16)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(Qt.NoPen)
        p.setBrush(self._on if self.isChecked() else self._off)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        d = rect.height() - 4
        x = rect.right() - d - 2 if self.isChecked() else rect.left() + 2
        p.setBrush(self._knob)
        p.drawEllipse(QRectF(x, rect.top() + 2, d, d))


class _Section(QWidget):
    """可折叠的分组：标题行 + 内容区。"""

    toggled = Signal(bool)

    def __init__(self, title: str, expanded: bool = True, extras=(), parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.header = QToolButton(self)
        self.header.setObjectName("GraphSectionHeader")
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.header.setCursor(Qt.PointingHandCursor)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(2, 0, 2, 4)
        self.body_layout.setSpacing(6)
        self.body.setVisible(expanded)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addWidget(self.header)
        header_row.addStretch(1)
        for widget in extras:
            header_row.addWidget(widget)
        layout.addLayout(header_row)
        layout.addWidget(self.body)
        self.header.toggled.connect(self._on_toggled)

    def _on_toggled(self, on: bool) -> None:
        self.header.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.body.setVisible(on)
        self.toggled.emit(on)


class GraphSettingsPanel(QFrame):
    """图谱右上角的浮动设置面板。"""

    settingsChanged = Signal(str)  # 参数为变更的字段名
    searchChanged = Signal(str)
    groupToggled = Signal(str, bool)
    resetRequested = Signal()
    closeRequested = Signal()
    layoutChanged = Signal()

    _SLIDERS: ClassVar[dict[str, list[tuple[str, str]]]] = {
        "appearance": [
            ("node_size", "节点大小"),
            ("link_width", "连线粗细"),
            ("text_fade", "标签显示阈值"),
        ],
        "forces": [
            ("center_force", "图谱向心力"),
            ("repel_force", "节点间的排斥力"),
            ("link_force", "相连节点间的吸引力"),
            ("link_distance", "连线长度"),
        ],
    }

    def __init__(self, settings: GraphSettings, parent=None):
        super().__init__(parent)
        self.setObjectName("GraphPanel")
        self.setFixedWidth(250)
        self._settings = settings
        self._sliders: dict[str, QSlider] = {}
        self._toggles: dict[str, ToggleSwitch] = {}
        self._group_rows: dict[str, QPushButton] = {}
        self._theme = GRAPH_THEMES["dark"]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self._scroll)

        content = QWidget()
        content.setObjectName("GraphPanelContent")
        self._scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        # ---- 筛选
        self.reset_button = QToolButton()
        self.reset_button.setObjectName("GraphPanelIcon")
        self.reset_button.setText("↺")
        self.reset_button.setToolTip("恢复默认设置")
        self.reset_button.clicked.connect(self.resetRequested)
        self.close_button = QToolButton()
        self.close_button.setObjectName("GraphPanelIcon")
        self.close_button.setText("✕")
        self.close_button.setToolTip("收起面板")
        self.close_button.clicked.connect(self.closeRequested)
        self.filter_section = _Section("筛选", extras=(self.reset_button, self.close_button))

        self.search = QLineEdit()
        self.search.setObjectName("GraphSearch")
        self.search.setPlaceholderText("搜索文件……")
        self.search.setClearButtonEnabled(True)
        self._search_action = self.search.addAction(_search_icon(QColor("#8E8E96")), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self.searchChanged)
        self.filter_section.body_layout.addWidget(self.search)
        self._add_toggle(self.filter_section, "show_orphans", "孤立文件")
        layout.addWidget(self.filter_section)
        layout.addWidget(self._separator())

        # ---- 颜色组
        self.group_section = _Section("颜色组")
        self._group_container = QWidget()
        self._group_layout = QVBoxLayout(self._group_container)
        self._group_layout.setContentsMargins(0, 0, 0, 0)
        self._group_layout.setSpacing(4)
        self.group_section.body_layout.addWidget(self._group_container)
        self._group_hint = QLabel("点击颜色组可隐藏 / 显示")
        self._group_hint.setObjectName("GraphPanelHint")
        self.group_section.body_layout.addWidget(self._group_hint)
        layout.addWidget(self.group_section)
        layout.addWidget(self._separator())

        # ---- 外观
        self.appearance_section = _Section("外观", expanded=False)
        self._add_toggle(self.appearance_section, "show_labels", "显示标签")
        for key, label in self._SLIDERS["appearance"]:
            self._add_slider(self.appearance_section, key, label)
        layout.addWidget(self.appearance_section)
        layout.addWidget(self._separator())

        # ---- 力度
        self.forces_section = _Section("力度")
        for key, label in self._SLIDERS["forces"]:
            self._add_slider(self.forces_section, key, label)
        layout.addWidget(self.forces_section)
        layout.addStretch(1)
        for section in (self.filter_section, self.group_section, self.appearance_section, self.forces_section):
            section.toggled.connect(lambda _on: self.layoutChanged.emit())

    def content_height(self) -> int:
        """内容区理想高度，用于让面板贴合内容。"""
        content = self._scroll.widget()
        content.layout().activate()
        return content.sizeHint().height() + 2

    # ------------------------------------------------------------ 构件

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setObjectName("GraphPanelSeparator")
        line.setFixedHeight(1)
        return line

    def _add_toggle(self, section: _Section, key: str, label: str) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        text = QLabel(label)
        text.setObjectName("GraphPanelLabel")
        toggle = ToggleSwitch(getattr(self._settings, key))
        toggle.setFixedSize(30, 16)
        toggle.toggled.connect(lambda on, k=key: self._on_toggle(k, on))
        row.addWidget(text, 1)
        row.addWidget(toggle)
        section.body_layout.addLayout(row)
        self._toggles[key] = toggle

    def _add_slider(self, section: _Section, key: str, label: str) -> None:
        text = QLabel(label)
        text.setObjectName("GraphPanelLabel")
        slider = QSlider(Qt.Horizontal)
        slider.setObjectName("GraphSlider")
        slider.setRange(0, 100)
        slider.setValue(round(getattr(self._settings, key) * 100))
        slider.setCursor(Qt.PointingHandCursor)
        slider.setFixedHeight(20)
        slider.valueChanged.connect(lambda v, k=key: self._on_slider(k, v))
        section.body_layout.addWidget(text)
        section.body_layout.addWidget(slider)
        self._sliders[key] = slider

    def _on_toggle(self, key: str, on: bool) -> None:
        setattr(self._settings, key, on)
        self.settingsChanged.emit(key)

    def _on_slider(self, key: str, value: int) -> None:
        setattr(self._settings, key, value / 100.0)
        self.settingsChanged.emit(key)

    # ------------------------------------------------------------ 同步

    def sync_from_settings(self) -> None:
        """把 settings 写回控件（恢复默认时使用），不触发信号。"""
        for key, slider in self._sliders.items():
            slider.blockSignals(True)
            slider.setValue(round(getattr(self._settings, key) * 100))
            slider.blockSignals(False)
        for key, toggle in self._toggles.items():
            toggle.blockSignals(True)
            toggle.setChecked(getattr(self._settings, key))
            toggle.blockSignals(False)

    def set_groups(self, groups: list[tuple[str, QColor, int]], hidden: set[str]) -> None:
        """重建颜色组列表：(组名, 颜色, 节点数)。"""
        while self._group_layout.count():
            item = self._group_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._group_rows.clear()
        for name, color, count in groups:
            row = QPushButton()
            row.setObjectName("GraphGroupRow")
            row.setCheckable(True)
            row.setChecked(name not in hidden)
            row.setCursor(Qt.PointingHandCursor)
            row.setProperty("groupColor", color.name())
            row.setProperty("groupName", name)
            row.setProperty("groupCount", count)
            self._style_group_row(row)
            row.toggled.connect(lambda on, n=name, r=row: self._on_group(n, on, r))
            self._group_layout.addWidget(row)
            self._group_rows[name] = row
        self._group_hint.setVisible(bool(groups))

    def _style_group_row(self, row: QPushButton) -> None:
        name = row.property("groupName")
        count = row.property("groupCount")
        color = QColor(row.property("groupColor"))
        if not row.isChecked():
            color.setAlpha(60)
        row.setToolTip(f"{name} · {count} 篇笔记（点击隐藏 / 显示）")
        row.setIcon(_dot_icon(color, 10))
        row.setIconSize(QSize(10, 10))
        row.setText(f"  {name}  ({count})")

    def _on_group(self, name: str, on: bool, row: QPushButton) -> None:
        self._style_group_row(row)
        self.groupToggled.emit(name, on)

    def apply_theme(self, theme: dict[str, str]) -> None:
        self._theme = theme
        for toggle in self._toggles.values():
            toggle.set_colors(theme["accent"], theme["track"], theme["knob"])
        t = theme
        self.setStyleSheet(
            f"""
            #GraphPanel {{
                background-color: {t['panel-bg']};
                border: 1px solid {t['panel-border']};
                border-radius: 10px;
            }}
            #GraphPanel QScrollArea, #GraphPanelContent {{
                background: transparent;
            }}
            #GraphSectionHeader {{
                color: {t['panel-fg']};
                font-size: 13px;
                font-weight: 600;
                border: none;
                background: transparent;
                padding: 2px 0;
                text-align: left;
            }}
            #GraphPanelIcon {{
                color: {t['panel-muted']};
                border: none;
                background: transparent;
                font-size: 14px;
                padding: 0 4px;
            }}
            #GraphPanelIcon:hover {{ color: {t['panel-fg']}; }}
            #GraphPanelLabel {{
                color: {t['panel-fg']};
                font-size: 12px;
            }}
            #GraphPanelHint {{
                color: {t['panel-muted']};
                font-size: 11px;
            }}
            #GraphPanelSeparator {{
                background-color: {t['panel-border']};
                border: none;
            }}
            #GraphSearch {{
                background-color: {t['input-bg']};
                color: {t['panel-fg']};
                border: 1px solid {t['panel-border']};
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 12px;
            }}
            #GraphSearch:focus {{ border-color: {t['accent']}; }}
            #GraphGroupRow {{
                background-color: {t['input-bg']};
                color: {t['panel-fg']};
                border: 1px solid {t['panel-border']};
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 12px;
                text-align: left;
            }}
            #GraphGroupRow:!checked {{ color: {t['panel-muted']}; }}
            #GraphGroupRow:hover {{ border-color: {t['accent']}; }}
            #GraphSlider::groove:horizontal {{
                height: 4px;
                background: {t['track']};
                border-radius: 2px;
            }}
            #GraphSlider::sub-page:horizontal {{
                background: {t['accent']};
                border-radius: 2px;
            }}
            #GraphSlider::handle:horizontal {{
                background: {t['knob']};
                border: 1px solid {t['knob-border']};
                width: 12px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['track']};
                border-radius: 3px;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            """
        )
        for row in self._group_rows.values():
            self._style_group_row(row)
        self.search.removeAction(self._search_action)
        self._search_action = self.search.addAction(
            _search_icon(QColor(t["panel-muted"])), QLineEdit.LeadingPosition
        )


def _search_icon(color: QColor):
    """单色放大镜图标。"""
    from PySide6.QtGui import QIcon, QPixmap

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(color, 3.0, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QRectF(5, 5, 16, 16))
    p.drawLine(QPointF(19, 19), QPointF(27, 27))
    p.end()
    return QIcon(pixmap)


def _dot_icon(color: QColor, size: int):
    from PySide6.QtGui import QIcon, QPixmap

    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(0, 0, size * 2, size * 2)
    p.end()
    return QIcon(pixmap)


# ====================================================================== 视图


class GraphView(QGraphicsView):
    """笔记链接网络图。"""

    #: 用户选中了某个节点，参数为笔记路径
    nodeSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GraphView")
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._nodes: dict[str, NoteNode] = {}
        self._edges: list[tuple[str, str]] = []
        self._neighbors: dict[str, set[str]] = {}
        self._positions: dict[str, QPointF] = {}
        self._adjacency: dict[str, list[str]] = {}
        self._keep: list[str] = []
        self._max_degree = 1
        self._group_colors: dict[str, QColor] = {}
        self._hidden_groups: set[str] = set()
        self._search = ""
        self._hover: str | None = None
        self._user_zoomed = False
        self._theme = "dark"
        self._settings = GraphSettings()

        # 力度参数变化后防抖重排
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(220)
        self._relayout_timer.timeout.connect(self._relayout)
        self._anim: QVariantAnimation | None = None

        # 浮动面板与状态角标
        self.panel = GraphSettingsPanel(self._settings, self)
        self.panel.settingsChanged.connect(self._on_setting_changed)
        self.panel.searchChanged.connect(self._on_search)
        self.panel.groupToggled.connect(self._on_group_toggled)
        self.panel.resetRequested.connect(self.reset_settings)
        self.panel.closeRequested.connect(lambda: self.set_panel_visible(False))
        self.panel.layoutChanged.connect(lambda: QTimer.singleShot(0, self._place_overlays))

        self.panel_button = QToolButton(self)
        self.panel_button.setObjectName("GraphPanelToggle")
        self.panel_button.setText("⚙")
        self.panel_button.setToolTip("图谱设置")
        self.panel_button.setCursor(Qt.PointingHandCursor)
        self.panel_button.setFixedSize(32, 32)
        self.panel_button.clicked.connect(lambda: self.set_panel_visible(True))
        self.panel_button.hide()

        self.stats_label = QLabel(self)
        self.stats_label.setObjectName("GraphStatsBadge")
        self.stats_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._apply_theme_chrome()

    # ---------------------------------------------------------------- 主题

    def set_theme(self, theme: str) -> None:
        """切换主题配色。"""
        self._theme = theme if theme in GRAPH_THEMES else "dark"
        self._apply_theme_chrome()
        self._apply_colors()

    def _palette(self) -> dict[str, str]:
        return GRAPH_THEMES.get(self._theme, GRAPH_THEMES["dark"])

    def _apply_theme_chrome(self) -> None:
        t = self._palette()
        self.setBackgroundBrush(QColor(t["bg"]))
        self.panel.apply_theme(t)
        self.panel_button.setStyleSheet(
            f"""
            #GraphPanelToggle {{
                background-color: {t['panel-bg']};
                color: {t['panel-fg']};
                border: 1px solid {t['panel-border']};
                border-radius: 8px;
                font-size: 16px;
            }}
            #GraphPanelToggle:hover {{ border-color: {t['accent']}; }}
            """
        )
        self.stats_label.setStyleSheet(
            f"""
            #GraphStatsBadge {{
                color: {t['panel-muted']};
                background-color: {t['panel-bg']};
                border: 1px solid {t['panel-border']};
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            """
        )
        for node in self._nodes.values():
            node.set_accent(QColor(t["accent"]))
        self.viewport().update()

    # ---------------------------------------------------------------- 构建

    def show_graph(self, nodes: dict[str, list[str]], titles: dict[str, str] | None = None) -> int:
        """渲染图谱。

        :param nodes: ``笔记路径 -> [目标路径, ...]`` 邻接表
        :param titles: 路径到显示标题的映射，缺省用文件名
        :return: 实际绘制的节点数
        """
        titles = titles or {}
        if self._anim is not None:
            self._anim.stop()
        self._hover = None
        self._scene.clear()
        self._nodes.clear()
        self._edges = []
        self._neighbors = {}
        self._user_zoomed = False

        if not nodes:
            self._keep = []
            self._adjacency = {}
            self._positions = {}
            self._scene.setSceneRect(0, 0, 400, 300)
            self.panel.set_groups([], self._hidden_groups)
            self._update_stats()
            return 0

        # 统计每个节点的度数（入度 + 出度）
        degree: dict[str, int] = {path: 0 for path in nodes}
        adjacency: dict[str, list[str]] = {}
        for source, targets in nodes.items():
            if source not in degree:
                degree[source] = 0
            adjacency.setdefault(source, [])
            for target in targets:
                degree[source] += 1
                degree[target] = degree.get(target, 0) + 1
                adjacency.setdefault(target, []).append(source)

        keep = self._select_nodes(degree)
        keep_set = set(keep)
        self._keep = keep
        self._adjacency = adjacency

        self._positions = self._layout(keep, adjacency, **self._force_params())
        self._max_degree = max(1, max((degree[p] for p in keep), default=0))

        palette = self._palette()
        for path in keep:
            node = NoteNode(path, titles.get(path) or self._label(path), degree[path], 1.0)
            node.group = self._group_of(path)
            node.set_accent(QColor(palette["accent"]))
            node.set_hover_callback(self._on_hover)
            # 必须把布局结果写进节点，否则所有节点会叠在场景原点
            node.set_position(self._positions[path])
            self._nodes[path] = node
            self._neighbors[path] = set()
            self._scene.addItem(node)
        self._apply_sizes()

        for source, targets in adjacency.items():
            for target in targets:
                if source in keep_set and target in keep_set:
                    self._edges.append((source, target))
                    if source != target:
                        self._neighbors[source].add(target)
                        self._neighbors[target].add(source)

        self._assign_groups()
        self._apply_colors()
        self._apply_visibility()
        self._update_scene_rect()
        self._fit()
        self._update_stats()
        return len(keep)

    @staticmethod
    def _label(path: str) -> str:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        return name.removesuffix(".md")

    @staticmethod
    def _group_of(path: str) -> str:
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        return parts[0] if len(parts) > 1 else ROOT_GROUP

    @staticmethod
    def _select_nodes(degree: dict[str, int]) -> list[str]:
        """节点过多时只保留链接数最高的一部分。"""
        if len(degree) <= MAX_NODES:
            return list(degree)
        ordered = sorted(degree, key=lambda p: (-degree[p], p))
        return ordered[:MAX_NODES]

    def _force_params(self) -> dict[str, float]:
        s = self._settings
        return {
            "center": s.center_force,
            "repel": s.repel_force,
            "attract": s.link_force,
            "distance": s.link_distance,
        }

    @staticmethod
    def _layout(
        keep: list[str],
        adjacency: dict[str, list[str]],
        area: float = 1400.0,
        iterations: int = _MAX_ITERATIONS,
        *,
        center: float = 0.5,
        repel: float = 0.5,
        attract: float = 0.5,
        distance: float = 0.5,
    ) -> dict[str, QPointF]:
        """力导向布局（numpy 向量化）。

        每个节点同时受三种力：

        - **斥力** 与所有其它节点距离成反比，避免重叠
        - **引力** 只作用于有连接的节点，把相关笔记拉近
        - **向心力** 把所有节点拉向原点，让整张图收成圆盘、孤立节点不飘散

        四个参数取值 0~1，对应设置面板「力度」中的滑块。

        :return: 节点路径 -> 收敛后的坐标
        """
        count = len(keep)
        if count == 0:
            return {}

        iterations = max(80, min(iterations, 90000 // max(count, 1)))
        k = (16.0 + 64.0 * distance) * math.sqrt(area / 1400.0)
        repel_mult = 0.25 + 1.5 * repel
        attract_mult = 0.25 + 1.5 * attract
        gravity = 0.004 + 0.06 * center
        # 斥力只在局部生效：远处的节点交给向心力收拢，整张图会形成均匀的圆盘，
        # 孤立节点也不会被整团节点推到天边
        cutoff_sq = (6.0 * k) ** 2

        index = {path: i for i, path in enumerate(keep)}
        pairs = set()
        for a, targets in adjacency.items():
            ia = index.get(a)
            if ia is None:
                continue
            for b in targets:
                ib = index.get(b)
                if ib is None or ib == ia:
                    continue
                pairs.add((min(ia, ib), max(ia, ib)))
        edges = np.array(sorted(pairs), dtype=np.int64).reshape(-1, 2)

        # 黄金角螺旋起点，比纯随机更均匀且可复现
        i = np.arange(count, dtype=np.float64)
        angle = i * math.pi * (3 - math.sqrt(5))
        radius = k * np.sqrt(i) * 0.9
        pos = np.stack([radius * np.cos(angle), radius * np.sin(angle)], axis=1)

        temperature = k * max(2.0, math.sqrt(count) * 0.5)
        cooling = (temperature - 0.5) / (iterations + 1)
        eye = np.eye(count, dtype=bool)

        for _ in range(iterations):
            delta = pos[:, None, :] - pos[None, :, :]
            dist_sq = np.einsum("ijk,ijk->ij", delta, delta)
            dist_sq = np.maximum(dist_sq, 0.01)
            # 斥力 k²/d，方向 delta/d → 系数 k²/d²
            coef = (k * k * repel_mult) / dist_sq
            coef[eye] = 0.0
            coef[dist_sq > cutoff_sq] = 0.0
            disp = np.einsum("ij,ijk->ik", coef, delta)

            if len(edges):
                a, b = edges[:, 0], edges[:, 1]
                d = pos[a] - pos[b]
                dist = np.sqrt(np.maximum((d * d).sum(axis=1), 1e-4))
                # 弹簧引力：把相连节点拉向理想长度 k
                f = (attract_mult * 0.5 * (dist - k) / dist)[:, None] * d
                np.add.at(disp, a, -f)
                np.add.at(disp, b, f)

            disp -= pos * gravity

            length = np.sqrt((disp * disp).sum(axis=1))
            scale = np.where(length > 0.01, np.minimum(length, temperature) / np.maximum(length, 1e-9), 0.0)
            pos += disp * scale[:, None]
            temperature = max(temperature - cooling, 0.5)

        return {path: QPointF(float(pos[n, 0]), float(pos[n, 1])) for n, path in enumerate(keep)}

    # ---------------------------------------------------------------- 外观

    def _assign_groups(self) -> None:
        counts: dict[str, int] = {}
        for node in self._nodes.values():
            counts[node.group] = counts.get(node.group, 0) + 1
        ordered = sorted(counts, key=lambda g: (-counts[g], g))
        self._group_colors = {}
        if len(ordered) > 1:
            for n, group in enumerate(ordered[: len(GROUP_PALETTE)]):
                self._group_colors[group] = QColor(GROUP_PALETTE[n])
        self._hidden_groups &= set(counts)
        default = QColor(self._palette()["node"])
        self.panel.set_groups(
            [(g, self._group_colors.get(g, default), counts[g]) for g in ordered],
            self._hidden_groups,
        )

    def _apply_sizes(self) -> None:
        scale = 0.5 + 1.5 * self._settings.node_size
        for node in self._nodes.values():
            radius = (2.5 + 7.5 * math.sqrt(node.degree / self._max_degree)) * scale
            node.set_radius(radius)

    def _apply_colors(self) -> None:
        palette = self._palette()
        default = QColor(palette["node"])
        accent = QColor(palette["accent"])
        # 只有一个分组时没有颜色可区分，把枢纽节点用强调色点出来
        hub_cut = None
        if not self._group_colors and self._nodes:
            degrees = sorted((n.degree for n in self._nodes.values()), reverse=True)
            hub_cut = max(3, degrees[max(0, len(degrees) // 20 - 1)])
        for node in self._nodes.values():
            color = QColor(self._group_colors.get(node.group, default))
            if hub_cut is not None and node.degree >= hub_cut:
                color = QColor(accent)
            if node.degree == 0:
                color.setAlpha(150)
            node.set_color(color)
        self.viewport().update()

    def _apply_visibility(self) -> None:
        s = self._settings
        for node in self._nodes.values():
            visible = node.group not in self._hidden_groups and (s.show_orphans or node.degree > 0)
            node.setVisible(visible)
        self._apply_highlight()

    def _apply_highlight(self) -> None:
        """根据悬停与搜索状态决定哪些节点淡出。"""
        focus: set[str] | None = None
        if self._hover and self._hover in self._nodes:
            focus = {self._hover} | self._neighbors.get(self._hover, set())
        elif self._search:
            focus = {
                p for p, n in self._nodes.items()
                if self._search in n.title.lower() or self._search in p.lower()
            }
        for path, node in self._nodes.items():
            node.set_dim(focus is not None and path not in focus)
        self.viewport().update()

    def _update_scene_rect(self) -> None:
        if not self._nodes:
            return
        rect = self._items_rect()
        pad = max(rect.width(), rect.height(), 400.0)
        self._scene.setSceneRect(rect.adjusted(-pad, -pad, pad, pad))

    def _items_rect(self) -> QRectF:
        xs = [n.position().x() for n in self._nodes.values()]
        ys = [n.position().y() for n in self._nodes.values()]
        return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).adjusted(-20, -20, 20, 20)

    def _fit(self) -> None:
        if not self._nodes:
            return
        rect = self._items_rect()
        self.fitInView(rect.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)

    def _update_stats(self) -> None:
        self.stats_label.setText(f"{len(self._nodes)} 个节点 · {len(self._edges)} 条连线")
        self.stats_label.adjustSize()
        self._place_overlays()

    # ---------------------------------------------------------------- 设置

    def settings(self) -> GraphSettings:
        return self._settings

    def reset_settings(self) -> None:
        defaults = GraphSettings()
        for f in fields(GraphSettings):
            setattr(self._settings, f.name, getattr(defaults, f.name))
        self._hidden_groups.clear()
        self.panel.sync_from_settings()
        self.panel.search.clear()
        self._assign_groups()
        self._apply_sizes()
        self._apply_colors()
        self._apply_visibility()
        self._relayout_timer.start()

    def set_panel_visible(self, visible: bool) -> None:
        self.panel.setVisible(visible)
        self.panel_button.setVisible(not visible)
        self._place_overlays()

    def _on_setting_changed(self, key: str) -> None:
        if key in ("center_force", "repel_force", "link_force", "link_distance"):
            self._relayout_timer.start()
        elif key == "node_size":
            self._apply_sizes()
            self.viewport().update()
        elif key == "show_orphans":
            self._apply_visibility()
        else:
            self.viewport().update()

    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self._apply_highlight()

    def _on_group_toggled(self, name: str, on: bool) -> None:
        if on:
            self._hidden_groups.discard(name)
        else:
            self._hidden_groups.add(name)
        self._apply_visibility()

    def _on_hover(self, path: str | None) -> None:
        self._hover = path
        self._apply_highlight()

    def _relayout(self) -> None:
        """按新的力度参数重算布局，并平滑过渡过去。"""
        if not self._keep:
            return
        start = {p: QPointF(n.position()) for p, n in self._nodes.items()}
        target = self._layout(self._keep, self._adjacency, **self._force_params())
        self._positions = target
        if self._anim is not None:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(450)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def step(value) -> None:
            t = float(value)
            for path, node in self._nodes.items():
                a, b = start[path], target[path]
                node.set_position(QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t))
            self.viewport().update()

        def done() -> None:
            self._update_scene_rect()
            if not self._user_zoomed:
                self._fit()

        anim.valueChanged.connect(step)
        anim.finished.connect(done)
        self._anim = anim
        anim.start()

    # ---------------------------------------------------------------- 绘制

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """背景 + 连线（场景坐标，连线使用 cosmetic 笔宽，缩放时粗细不变）。"""
        t = self._palette()
        painter.fillRect(rect, QColor(t["bg"]))
        if not self._edges:
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        width = 0.4 + 2.6 * self._settings.link_width

        focus = None
        if self._hover and self._hover in self._nodes:
            focus = self._hover
        dim_all = focus is not None or bool(self._search)

        base = QColor(t["edge"])
        base.setAlpha(28 if dim_all else 70)
        normal: list[QLineF] = []
        highlighted: list[QLineF] = []
        tinted: dict[str, list[QLineF]] = {}
        for source, target in self._edges:
            a = self._nodes.get(source)
            b = self._nodes.get(target)
            if a is None or b is None or not a.isVisible() or not b.isVisible():
                continue
            line = QLineF(a.position(), b.position())
            if focus is not None and (source == focus or target == focus):
                highlighted.append(line)
            elif not dim_all and a.group in self._group_colors:
                tinted.setdefault(a.group, []).append(line)
            else:
                normal.append(line)

        pen = QPen(base, width)
        pen.setCosmetic(True)
        painter.setPen(pen)
        if normal:
            painter.drawLines(normal)
        # 连线微微带上源节点的组色，整体呈现 Obsidian 那种彩色毛线团的质感
        for group, lines in tinted.items():
            color = QColor(self._group_colors[group])
            color = _mix(color, base, 0.55)
            color.setAlpha(80)
            pen = QPen(color, width)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLines(lines)
        if highlighted:
            pen = QPen(QColor(t["accent"]), width + 0.8)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLines(highlighted)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """节点标签：随缩放渐显，悬停节点及其邻居始终显示。"""
        if not self._nodes or not self._settings.show_labels:
            return
        zoom = self.transform().m11()
        threshold = 0.3 + 1.7 * self._settings.text_fade
        base_alpha = max(0.0, min(1.0, (zoom - threshold) / 0.5))

        focus: set[str] = set()
        if self._hover and self._hover in self._nodes:
            focus = {self._hover} | self._neighbors.get(self._hover, set())

        if base_alpha <= 0.0 and not focus:
            return

        t = self._palette()
        painter.save()
        painter.resetTransform()
        font = QFont(self.font())
        font.setPixelSize(11)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        view_rect = self.viewport().rect().adjusted(-80, -40, 80, 40)
        for path, node in self._nodes.items():
            if not node.isVisible():
                continue
            if focus:
                if path not in focus:
                    continue
                alpha = 1.0
            else:
                if node.is_dim():
                    continue
                alpha = base_alpha
            pt = self.mapFromScene(node.position())
            if not view_rect.contains(pt):
                continue
            text = metrics.elidedText(node.title, Qt.ElideRight, 160)
            color = QColor(t["label"])
            color.setAlphaF(alpha)
            painter.setPen(color)
            y = pt.y() + node.radius() * zoom + 4
            w = metrics.horizontalAdvance(text)
            painter.drawText(QRectF(pt.x() - w / 2 - 2, y, w + 4, metrics.height()), Qt.AlignCenter, text)
        painter.restore()

    # ---------------------------------------------------------------- 交互

    def wheelEvent(self, event) -> None:
        """滚轮以鼠标为中心缩放。"""
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        zoom = self.transform().m11() * factor
        if 0.03 <= zoom <= 12.0:
            self.scale(factor, factor)
            self._user_zoomed = True
        event.accept()

    def mousePressEvent(self, event) -> None:
        """点击节点时上抛选择信号。"""
        item = self.itemAt(event.pos())
        if isinstance(item, NoteNode):
            self.nodeSelected.emit(item.path)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """双击空白处重新适配视图。"""
        if not isinstance(self.itemAt(event.pos()), NoteNode):
            self._user_zoomed = False
            self._fit()
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._place_overlays()
        if not self._user_zoomed:
            self._fit()

    def _place_overlays(self) -> None:
        margin = 12
        w, h = self.width(), self.height()
        self.panel.setFixedHeight(max(120, min(self.panel.content_height(), h - margin * 2 - 36)))
        self.panel.move(w - self.panel.width() - margin, margin)
        self.panel_button.move(w - self.panel_button.width() - margin, margin)
        self.stats_label.move(w - self.stats_label.width() - margin, h - self.stats_label.height() - margin)
        self.panel.raise_()
        self.panel_button.raise_()
        self.stats_label.raise_()

    # ---------------------------------------------------------------- 查询

    def node_count(self) -> int:
        """已绘制的节点数。"""
        return len(self._nodes)

    def node_positions(self) -> dict[str, QPointF]:
        """节点坐标，供测试与布局校验。"""
        return dict(self._positions)

    def edge_count(self) -> int:
        return len(self._edges)

    def node_for(self, path: str) -> NoteNode | None:
        """按路径取节点。"""
        return self._nodes.get(path)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    """按比例 t 把颜色 a 混向 b。"""
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )
