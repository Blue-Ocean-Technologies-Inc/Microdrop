"""Node-graph canvas: steps as nodes, decisions as port strips, routes as
draggable edges.

Graphics View idioms follow the two canvases already in the app —
``device_viewer/views/video_viewer/video_canvas.py`` (AnchorUnderMouse
zoom, drag pan) and ``device_viewer/views/electrode_view/electrode_scene.py``
(hit-testing items in scene mouse handlers; QGraphicsItems are not QObjects,
so the scene talks to the window by direct calls, not signals).

Visual language:
  * node = one protocol step: header (name), body (column values, i.e. the
    "table row"), then one strip per decision its columns can pose, with a
    colored port per outcome.
  * grey dashed edge = implicit fall-through to the next step in table order
    (not selectable — it's the default, not user data).
  * solid dark edge from the ▸ done-port = user-drawn completion route.
  * colored edge from an outcome port = user-drawn decision route
    (green continue / orange retry / red abort).
  * unrouted outcomes keep their provider defaults — shown in the port
    tooltips, drawn as nothing.

Drag from a done-port or outcome port and drop on any node to (re)route.
Delete a selected edge to fall back to the default. Right-click a node for
rename/delete and per-decision prompt/auto configuration.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker,
    QPen, QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsObject, QGraphicsPathItem,
    QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView,
)

from .model import NEXT

NODE_W = 200
HEADER_H = 26
LINE_H = 16
STRIP_TITLE_H = 15
STRIP_PORTS_H = 24
PAD = 7
PORT_R = 5.5

KIND_COLORS = {
    "positive": "#2e7d32",
    "negative": "#ef6c00",
    "danger": "#c62828",
    "neutral": "#546e7a",
    "flow": "#37474f",
    "flow_default": "#9aa7b0",
}
STATE_BORDER = {
    "idle": "#607d8b",
    "active": "#1976d2",
    "deciding": "#ef6c00",
}


class PortItem(QGraphicsEllipseItem):
    """A connection endpoint. role: "in" | "done" | "outcome"."""

    def __init__(self, node, role, out_dir, color, decision_id=None,
                 outcome_id=None):
        super().__init__(-PORT_R, -PORT_R, 2 * PORT_R, 2 * PORT_R, node)
        self.node = node
        self.role = role
        self.out_dir = out_dir            # QPointF unit vector for edge exit
        self.decision_id = decision_id
        self.outcome_id = outcome_id
        self.base_color = QColor(color)
        self.setBrush(QBrush(self.base_color))
        self.setPen(QPen(QColor("#ffffff"), 1.5))
        self.setAcceptHoverEvents(True)
        self.setZValue(3)

    def hoverEnterEvent(self, event):
        self.setScale(1.35)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setScale(1.0)
        super().hoverLeaveEvent(event)

    def key(self):
        if self.role == "outcome":
            return ("outcome", self.decision_id, self.outcome_id)
        return (self.role,)


class EdgeItem(QGraphicsPathItem):
    """Cubic-bezier edge with an arrowhead and optional label.

    kind: "flow" | "flow_default" | an outcome kind ("positive"/...).
    ``user`` edges are selectable and deletable; the implicit fall-through
    edge is not.
    """

    def __init__(self, scene, src_step_id, src_key, dst_step_id, kind,
                 user, label=""):
        super().__init__()
        self._scene = scene
        self.src_step_id = src_step_id
        self.src_key = src_key            # port key tuple on the source node
        self.dst_step_id = dst_step_id
        self.kind = kind
        self.user = user
        self._arrow = QPolygonF()
        color = QColor(KIND_COLORS.get(kind, KIND_COLORS["neutral"]))
        self._color = color
        pen = QPen(color, 2.0)
        if kind == "flow_default":
            pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        self.setZValue(-1)
        if user:
            self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self._label = None
        if label:
            self._label = QGraphicsSimpleTextItem(label, self)
            f = QFont()
            f.setPointSizeF(7.5)
            self._label.setFont(f)
            self._label.setBrush(QBrush(color))

    def update_path(self):
        src = self._scene.port(self.src_step_id, self.src_key)
        dst = self._scene.port(self.dst_step_id, ("in",))
        if src is None or dst is None:
            return
        p1 = src.scenePos()
        p2 = dst.scenePos()
        d1 = src.out_dir
        span = max(abs(p2.x() - p1.x()), abs(p2.y() - p1.y()))
        reach = min(150.0, max(50.0, span * 0.5))
        # Self-loops need extra swing to be visible.
        if self.src_step_id == self.dst_step_id:
            reach = 120.0
        c1 = p1 + QPointF(d1.x() * reach, d1.y() * reach)
        c2 = p2 + QPointF(-reach, 0)      # in-ports always face left
        path = QPainterPath(p1)
        path.cubicTo(c1, c2, p2)

        # Arrowhead along the incoming tangent.
        tangent = p2 - c2
        length = (tangent.x() ** 2 + tangent.y() ** 2) ** 0.5 or 1.0
        ux, uy = tangent.x() / length, tangent.y() / length
        size = 9.0
        base = p2 - QPointF(ux * size, uy * size)
        normal = QPointF(-uy, ux)
        self.prepareGeometryChange()
        self._arrow = QPolygonF([
            p2,
            base + QPointF(normal.x() * size * 0.45, normal.y() * size * 0.45),
            base - QPointF(normal.x() * size * 0.45, normal.y() * size * 0.45),
        ])
        self.setPath(path)
        if self._label is not None:
            at = path.pointAtPercent(0.35)
            self._label.setPos(at + QPointF(4, -14))

    def boundingRect(self):
        return super().boundingRect().united(
            self._arrow.boundingRect()).adjusted(-6, -6, 6, 6)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(12)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self.pen())
        if self.isSelected():
            pen.setColor(QColor("#1976d2"))
            pen.setWidthF(3.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())
        painter.setBrush(QBrush(pen.color()))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(self._arrow)


class StepNodeItem(QGraphicsObject):
    """One step. Movable; owns its ports; paints name + column values +
    decision strips."""

    def __init__(self, scene, step, columns):
        super().__init__()
        self._scene = scene
        self.step = step
        self.columns = columns
        # [(handler, spec)] in provider-priority order — same for every node.
        self.decisions = []
        for col in sorted(columns, key=lambda c: (c.handler.priority,
                                                  c.model.col_id)):
            for spec in col.handler.decision_specs():
                self.decisions.append((col.handler, spec))

        self.state = "idle"
        self._height = (HEADER_H + PAD + len(columns) * LINE_H + PAD
                        + len(self.decisions) * (STRIP_TITLE_H + STRIP_PORTS_H)
                        + (PAD if self.decisions else 0))

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(1)
        self.setPos(*step.pos)

        self.ports = {}
        self._add_port(PortItem(self, "in", QPointF(-1, 0), "#78909c"),
                       QPointF(0, HEADER_H / 2))
        self._add_port(PortItem(self, "done", QPointF(1, 0),
                                KIND_COLORS["flow"]),
                       QPointF(NODE_W, HEADER_H / 2))
        y = HEADER_H + PAD + len(columns) * LINE_H + PAD
        for handler, spec in self.decisions:
            ports_y = y + STRIP_TITLE_H + STRIP_PORTS_H / 2
            n = len(spec.outcomes)
            for k, outcome in enumerate(spec.outcomes):
                x = NODE_W * (k + 1) / (n + 1)
                self._add_port(
                    PortItem(self, "outcome", QPointF(0, 1),
                             KIND_COLORS.get(outcome.kind, "#546e7a"),
                             decision_id=spec.id, outcome_id=outcome.id),
                    QPointF(x, ports_y + STRIP_PORTS_H / 2 - 4))
            y += STRIP_TITLE_H + STRIP_PORTS_H
        self.refresh_tooltips()

    def _add_port(self, port, pos):
        port.setPos(pos)
        self.ports[port.key()] = port

    # -- model-facing helpers -------------------------------------------

    def refresh_tooltips(self):
        proto = self._scene.protocol
        step = self.step
        self.ports[("done",)].setToolTip(
            f"On completion → {proto.describe_target(step.next_target)}\n"
            f"Drag onto a step to reroute.")
        self.ports[("in",)].setToolTip("Route steps and outcomes here.")
        for handler, spec in self.decisions:
            cfg = step.decision_cfgs.get(spec.id)
            for outcome in spec.outcomes:
                target = spec.default_routes.get(outcome.id, NEXT)
                origin = "default"
                if cfg and outcome.id in cfg.routes:
                    target = cfg.routes[outcome.id]
                    origin = "custom"
                self.ports[("outcome", spec.id, outcome.id)].setToolTip(
                    f"{spec.title}: {outcome.label} → "
                    f"{proto.describe_target(target)} ({origin})\n"
                    f"Drag onto a step to reroute.")

    def set_state(self, state):
        if self.state != state:
            self.state = state
            self.update()

    # -- geometry / paint -----------------------------------------------

    def boundingRect(self):
        return QRectF(-PORT_R, -PORT_R, NODE_W + 2 * PORT_R,
                      self._height + 2 * PORT_R)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, NODE_W, self._height)

        border = QColor(STATE_BORDER[self.state])
        if self.isSelected() and self.state == "idle":
            border = QColor("#1976d2")
        width = 2.5 if self.state != "idle" else (2.0 if self.isSelected()
                                                  else 1.2)
        painter.setPen(QPen(border, width))
        fill = QColor("#ffffff")
        if self.state == "active":
            fill = QColor("#e8f1fb")
        elif self.state == "deciding":
            fill = QColor("#fdf1e3")
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(rect, 6, 6)

        # Header
        painter.setPen(QPen(QColor("#263238")))
        f = QFont()
        f.setPointSizeF(9.5)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(QRectF(PAD + 2, 0, NODE_W - 2 * PAD, HEADER_H),
                         Qt.AlignVCenter | Qt.AlignLeft, self.step.name)
        painter.setPen(QPen(QColor("#cfd8dc"), 1))
        painter.drawLine(QPointF(0, HEADER_H), QPointF(NODE_W, HEADER_H))

        # Column values (the "table row" for this step)
        f = QFont()
        f.setPointSizeF(8)
        painter.setFont(f)
        y = HEADER_H + PAD
        for col in self.columns:
            painter.setPen(QPen(QColor("#78909c")))
            painter.drawText(QRectF(PAD + 2, y, NODE_W * 0.55, LINE_H),
                             Qt.AlignVCenter | Qt.AlignLeft,
                             col.model.col_name)
            painter.setPen(QPen(QColor("#263238")))
            painter.drawText(QRectF(NODE_W * 0.5, y,
                                    NODE_W * 0.5 - PAD, LINE_H),
                             Qt.AlignVCenter | Qt.AlignRight,
                             col.model.format_display(self.step))
            y += LINE_H
        y += PAD

        # Decision strips
        for handler, spec in self.decisions:
            active = handler.is_decision_active(spec, self.step)
            painter.setPen(QPen(QColor("#cfd8dc"), 1))
            painter.drawLine(QPointF(0, y), QPointF(NODE_W, y))
            title_color = "#37474f" if active else "#b0bec5"
            painter.setPen(QPen(QColor(title_color)))
            f2 = QFont()
            f2.setPointSizeF(7.5)
            f2.setBold(True)
            painter.setFont(f2)
            cfg = self.step.decision_cfgs.get(spec.id)
            mode = ""
            if cfg is not None:
                if cfg.mode == "auto":
                    mode = "   [auto]"
                elif cfg.auto_after is not None:
                    mode = f"   [auto after {cfg.auto_after}]"
            painter.drawText(
                QRectF(PAD + 2, y, NODE_W - 2 * PAD, STRIP_TITLE_H),
                Qt.AlignVCenter | Qt.AlignLeft,
                f"⬥ {spec.title}{mode}" + ("" if active else "  (off)"))
            # Outcome labels above their ports
            f3 = QFont()
            f3.setPointSizeF(7)
            painter.setFont(f3)
            n = len(spec.outcomes)
            for k, outcome in enumerate(spec.outcomes):
                x = NODE_W * (k + 1) / (n + 1)
                color = (KIND_COLORS.get(outcome.kind, "#546e7a")
                         if active else "#b0bec5")
                painter.setPen(QPen(QColor(color)))
                painter.drawText(
                    QRectF(x - 34, y + STRIP_TITLE_H - 2, 68, 12),
                    Qt.AlignHCenter | Qt.AlignTop, outcome.label)
            y += STRIP_TITLE_H + STRIP_PORTS_H

    # -- interaction ----------------------------------------------------

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.step.pos = (self.pos().x(), self.pos().y())
            self._scene.update_edges_for(self.step.id)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        self._scene.window.rename_step(self.step.id)
        event.accept()

    def contextMenuEvent(self, event):
        self._scene.window.node_menu(self.step.id, event.screenPos())
        event.accept()


class FlowchartScene(QGraphicsScene):
    """Owns nodes + edges; rebuilt from the Protocol after model changes.
    Port-to-node connection drags are handled here (mouse handlers), the
    resulting model mutation goes through ``window.commit_route``."""

    def __init__(self, window, protocol):
        super().__init__()
        self.window = window
        self.protocol = protocol
        self.node_by_id = {}
        self.edges = []
        self._drag_port = None
        self._drag_path = None
        self.setBackgroundBrush(QBrush(QColor("#f4f6f8")))

    # -- lookup ----------------------------------------------------------

    def port(self, step_id, key):
        node = self.node_by_id.get(step_id)
        return node.ports.get(tuple(key)) if node else None

    # -- (re)build from model -------------------------------------------

    def rebuild(self):
        self.clearSelection()
        self.clear()                      # deletes all items
        self.node_by_id = {}
        self.edges = []
        for step in self.protocol.steps:
            node = StepNodeItem(self, step, self.protocol.columns)
            self.addItem(node)
            self.node_by_id[step.id] = node

        steps = self.protocol.steps
        for i, step in enumerate(steps):
            # Completion route
            if step.next_target == NEXT:
                if i + 1 < len(steps):
                    self._add_edge(EdgeItem(self, step.id, ("done",),
                                            steps[i + 1].id, "flow_default",
                                            user=False))
            else:
                dst = self.protocol.step_by_id(step.next_target)
                if dst is not None:
                    self._add_edge(EdgeItem(self, step.id, ("done",),
                                            dst.id, "flow", user=True))
            # Decision routes (only user-drawn ones are edges; defaults
            # live in tooltips)
            node = self.node_by_id[step.id]
            for handler, spec in node.decisions:
                cfg = step.decision_cfgs.get(spec.id)
                if not cfg:
                    continue
                for outcome in spec.outcomes:
                    target = cfg.routes.get(outcome.id)
                    if target and self.protocol.step_by_id(target):
                        self._add_edge(EdgeItem(
                            self, step.id, ("outcome", spec.id, outcome.id),
                            target, outcome.kind, user=True,
                            label=outcome.label))
        rect = self.itemsBoundingRect().adjusted(-120, -120, 120, 120)
        self.setSceneRect(rect)

    def _add_edge(self, edge):
        self.addItem(edge)
        edge.update_path()
        self.edges.append(edge)

    def update_edges_for(self, step_id):
        for e in self.edges:
            if e.src_step_id == step_id or e.dst_step_id == step_id:
                e.update_path()

    def refresh_nodes(self):
        for node in self.node_by_id.values():
            node.refresh_tooltips()
            node.update()

    # -- run-state visuals ----------------------------------------------

    def set_step_state(self, step_id, state):
        node = self.node_by_id.get(step_id)
        if node:
            node.set_state(state)

    def clear_step_states(self):
        for node in self.node_by_id.values():
            node.set_state("idle")

    # -- connection dragging --------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.scenePos(),
                               self.views()[0].transform()
                               if self.views() else None)
            if isinstance(item, PortItem) and item.role in ("done", "outcome"):
                self._drag_port = item
                self._drag_path = QGraphicsPathItem()
                pen = QPen(QColor("#1976d2"), 2, Qt.DashLine)
                self._drag_path.setPen(pen)
                self._drag_path.setZValue(5)
                self.addItem(self._drag_path)
                self._update_drag(event.scenePos())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_port is not None:
            self._update_drag(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_port is not None:
            src = self._drag_port
            self.removeItem(self._drag_path)
            self._drag_port = None
            self._drag_path = None
            target = self._node_at(event.scenePos())
            if target is not None:
                self.window.commit_route(src, target.step.id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _update_drag(self, scene_pos):
        p1 = self._drag_port.scenePos()
        d1 = self._drag_port.out_dir
        reach = 80.0
        path = QPainterPath(p1)
        path.cubicTo(p1 + QPointF(d1.x() * reach, d1.y() * reach),
                     scene_pos + QPointF(-reach, 0), scene_pos)
        self._drag_path.setPath(path)

    def _node_at(self, scene_pos):
        for item in self.items(scene_pos):
            if isinstance(item, StepNodeItem):
                return item
            if isinstance(item, PortItem):
                return item.node
        return None

    # -- deletion --------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            edges = [e for e in self.selectedItems()
                     if isinstance(e, EdgeItem) and e.user]
            nodes = [n for n in self.selectedItems()
                     if isinstance(n, StepNodeItem)]
            if edges or nodes:
                self.window.delete_items(edges, [n.step.id for n in nodes])
                event.accept()
                return
        super().keyPressEvent(event)


class FlowchartView(QGraphicsView):
    """Zoom-under-mouse wheel, middle-button pan, rubber-band select —
    the same feel as the device viewer's canvases."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing
                            | QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self._panning = False
        self._pan_start = None

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current = self.transform().m11()
        if 0.2 < current * factor < 4.0:
            self.scale(factor, factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def fit_all(self):
        rect = self.scene().itemsBoundingRect().adjusted(-60, -60, 60, 60)
        if not rect.isEmpty():
            self.fitInView(rect, Qt.KeepAspectRatio)
            # Don't zoom tiny scenes in past 1:1.
            if self.transform().m11() > 1.0:
                self.setTransform(self.transform().scale(
                    1 / self.transform().m11(), 1 / self.transform().m11()))
