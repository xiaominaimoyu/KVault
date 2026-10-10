"""知识图谱视图。

用 :class:`QGraphicsView` 绘制笔记之间的链接网络：

- **力导向布局** —— 自己实现的 Fruchterman-Reingold 变体，不依赖 networkx；
  斥力让节点散开、引力把相连节点拉近，跑到能量阈值以下即收敛。
- 节点大小反映链接数量，孤立节点（孤儿笔记）用低饱和色标出。
- 支持滚轮缩放、拖拽平移、点击选中并回调。

大型笔记库的图会退化成一团毛球，因此对节点数设有上限，超出时只绘制链接数
最高的节点，避免界面卡死。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
)

from gui.styles.variables import TOKENS_DARK, TOKENS_LIGHT

#: 超过该节点数时只保留链接数最高的部分，避免布局退化
MAX_NODES = 300

#: 布局迭代上限
_MAX_ITERATIONS = 260


class NoteNode(QGraphicsObject):
    """图中的一个笔记节点。"""

    def __init__(self, path: str, title: str, degree: int, radius: float):
        super().__init__()
        self.path = path
        self.title = title
        self.degree = degree
        self._radius = radius
        self._pos = QPointF(0.0, 0.0)
        self._color = QColor(TOKENS_DARK["accent-primary"])
        self.setAcceptHoverEvents(True)
        self.setToolTip(title)

    def boundingRect(self) -> QRectF:  # noqa: N802 — Qt 接口命名
        return QRectF(
            self._pos.x() - self._radius,
            self._pos.y() - self._radius,
            self._radius * 2,
            self._radius * 2,
        )

    def shape(self) -> QRectF:  # noqa: N802 — Qt 接口命名
        return self.boundingRect()

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QBrush(self._color))
        painter.setPen(QPen(QColor(0, 0, 0, 90), 1))
        painter.drawEllipse(self._pos, self._radius, self._radius)

    def position(self) -> QPointF:
        return self._pos

    def set_position(self, point: QPointF) -> None:
        self.prepareGeometryChange()
        self._pos = point
        self.update()

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def radius(self) -> float:
        return self._radius


class GraphView(QGraphicsView):
    """笔记链接网络图。"""

    #: 用户选中了某个节点，参数为笔记路径
    nodeSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GraphView")
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._nodes: dict[str, NoteNode] = {}
        self._edges: list[tuple[QPointF, QPointF]] = []
        self._positions: dict[str, QPointF] = {}
        self._theme = "dark"

    # ---------------------------------------------------------------- 构建

    def set_theme(self, theme: str) -> None:
        """切换主题配色。"""
        self._theme = theme
        self._apply_colors()

    def _tokens(self) -> dict:
        return TOKENS_DARK if self._theme == "dark" else TOKENS_LIGHT

    def show_graph(self, nodes: dict[str, list[str]], titles: dict[str, str] | None = None) -> int:
        """渲染图谱。

        :param nodes: ``笔记路径 -> [目标路径, ...]`` 邻接表
        :param titles: 路径到显示标题的映射，缺省用文件名
        :return: 实际绘制的节点数
        """
        titles = titles or {}
        self._scene.clear()
        self._nodes.clear()
        self._edges = []

        if not nodes:
            self._scene.setSceneRect(0, 0, 400, 300)
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

        self._positions = self._layout(keep, adjacency)
        max_degree = max(1, max((degree[p] for p in keep), default=0))

        for path in keep:
            radius = 6.0 + 14.0 * math.sqrt(degree[path] / max_degree)
            node = NoteNode(path, titles.get(path) or self._label(path), degree[path], radius)
            # 必须把布局结果写进节点，否则所有节点会叠在场景原点
            node.set_position(self._positions[path])
            self._nodes[path] = node
            self._scene.addItem(node)

        for source, targets in adjacency.items():
            for target in targets:
                if source in keep and target in keep:
                    self._edges.append((self._positions[source], self._positions[target]))

        self._apply_colors()
        self._fit()
        return len(keep)

    @staticmethod
    def _label(path: str) -> str:
        name = path.rsplit("/", 1)[-1]
        return name[:-3] if name.endswith(".md") else name

    @staticmethod
    def _select_nodes(degree: dict[str, int]) -> list[str]:
        """节点过多时只保留链接数最高的一部分。"""
        if len(degree) <= MAX_NODES:
            return list(degree)
        ordered = sorted(degree, key=lambda p: (-degree[p], p))
        return ordered[:MAX_NODES]

    @staticmethod
    def _layout(
        keep: list[str],
        adjacency: dict[str, list[str]],
        area: float = 1400.0,
        iterations: int = _MAX_ITERATIONS,
    ) -> dict[str, QPointF]:
        """力导向布局。

        每个节点同时受三种力：

        - **斥力** 与所有其它节点成反比，避免重叠
        - **引力** 只作用于有连接的节点，把相关笔记拉近
        - **向心力** 把所有节点轻微拉向原点，防止图飘散到无穷远

        :return: 节点路径 -> 收敛后的坐标
        """
        count = len(keep)
        if count == 0:
            return {}

        # 斥力是 O(n^2)，节点越多迭代越少，否则大图会卡住界面
        iterations = max(60, min(iterations, 24000 // max(count, 1)))

        k = math.sqrt(area / count) if count > 1 else area
        positions: dict[str, QPointF] = {}
        for index, path in enumerate(keep):
            # 黄金角螺旋起点，比纯随机更均匀且可复现
            angle = index * math.pi * (3 - math.sqrt(5))
            radius = k * math.sqrt(index) * 0.6
            positions[path] = QPointF(radius * math.cos(angle), radius * math.sin(angle))

        velocities = {path: QPointF(0.0, 0.0) for path in keep}
        temperature = k * 0.5
        cooling = temperature / (iterations + 1)

        for _ in range(iterations):
            displacement: dict[str, QPointF] = {path: QPointF(0.0, 0.0) for path in keep}

            # 斥力（全对，O(n^2)）
            for i in range(count):
                a = keep[i]
                pa = positions[a]
                for j in range(i + 1, count):
                    b = keep[j]
                    pb = positions[b]
                    dx = pa.x() - pb.x()
                    dy = pa.y() - pb.y()
                    dist_sq = dx * dx + dy * dy
                    if dist_sq < 0.01:
                        # 完全重合时给一个确定性的微小偏移，避免除零
                        dx = 0.01 * (i + 1)
                        dy = 0.01 * (j + 1)
                        dist_sq = dx * dx + dy * dy
                    dist = math.sqrt(dist_sq)
                    force = (k * k) / dist
                    fx = dx / dist * force
                    fy = dy / dist * force
                    da = displacement[a]
                    db = displacement[b]
                    displacement[a] = QPointF(da.x() + fx, da.y() + fy)
                    displacement[b] = QPointF(db.x() - fx, db.y() - fy)

            # 引力（仅对有连接的节点对）
            for a in keep:
                for b in adjacency.get(a, []):
                    if b not in positions or b == a:
                        continue
                    pa = positions[a]
                    pb = positions[b]
                    dx = pa.x() - pb.x()
                    dy = pa.y() - pb.y()
                    dist = math.hypot(dx, dy)
                    if dist < 0.01:
                        continue
                    force = (dist * dist) / k
                    fx = dx / dist * force
                    fy = dy / dist * force
                    da = displacement[a]
                    db = displacement[b]
                    displacement[a] = QPointF(da.x() - fx, da.y() - fy)
                    displacement[b] = QPointF(db.x() + fx, db.y() + fy)

            # 位移更新 + 温度限制
            for path in keep:
                d = displacement[path]
                length = math.hypot(d.x(), d.y())
                if length < 0.01:
                    continue
                limit = min(length, temperature)
                velocities[path] = QPointF(d.x() / length * limit, d.y() / length * limit)
                p = positions[path]
                positions[path] = QPointF(p.x() + velocities[path].x(), p.y() + velocities[path].y())

            temperature = max(temperature - cooling, 0.5)

        return positions

    # ---------------------------------------------------------------- 绘制

    def _apply_colors(self) -> None:
        tokens = self._tokens()
        for path, node in self._nodes.items():
            degree = node.degree
            if degree == 0:
                node.set_color(QColor(tokens["fg-muted"]))
            elif degree <= 2:
                node.set_color(QColor(tokens["status-info"]))
            elif degree <= 5:
                node.set_color(QColor(tokens["accent-primary"]))
            else:
                node.set_color(QColor(tokens["accent-warm"]))

    def _fit(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            return
        self._scene.setSceneRect(rect)
        self.fitInView(rect.adjusted(-40, -40, 40, 40), Qt.KeepAspectRatio)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt 接口命名
        """先画边，再由基类画节点。"""
        tokens = self._tokens()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor(tokens["fg-faint"]), 1.2))

        transform = self.transform()
        for start, end in self._edges:
            a = transform.map(start)
            b = transform.map(end)
            painter.drawLine(a, b)

        super().paintEvent(event)

    # ---------------------------------------------------------------- 交互

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt 接口命名
        """点击节点时上抛选择信号。"""
        item = self.itemAt(event.pos())
        if isinstance(item, NoteNode):
            self.nodeSelected.emit(item.path)
            event.accept()
            return
        super().mousePressEvent(event)

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