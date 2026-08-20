"""Node-graph canvas: compact step slabs, decision/AND shapes, and
obstacle-avoiding routed edges.

Look and interaction follow the ``claude/protocol-controls-branching-xuhkrc``
branch's flow view (``pluggable_protocol_tree/views/flow_graph_dialog.py``):
dark canvas, slim node boxes, edges that wrap around intervening boxes
(``route_edge_path``), snap-to-node with a cyan glow, a "＋ New step" ghost
when a drag is released over blank space, rubber-band multi-select with
group/ungroup, middle-mouse pan and Ctrl+wheel zoom.

What's new on top of it — the shape palette model:

  * Step nodes are minimal (execution order + name); parameters live in
    the table, not on the node.
  * Every step carries a small ＋ plug button (Miro-style). Clicking it
    opens a palette of shapes: one decision per contributing column (only
    those not already placed for that step) and an AND operator.
  * A placed decision is its own shape, tethered to its step by a faint
    dotted line, with one colored port per outcome. Outcome ports drag to
    steps/groups (route that answer), to an AND shape (feed the
    combiner), or to blank space (mint a new step, pre-routed).
  * An AND shape fires when all its input outcomes were chosen in the
    step's round; its out-port drags to the combined target.

All mutations go through the window (``commit_*``/``delete_items``) which
rebuilds the scene from the model; node drags do NOT rebuild — edges
re-route live and positions persist on the model objects.
"""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker,
    QPen, QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsView,
)

# --- layout / style constants (palette from the xuhkrc flow view) ---

NODE_W = 190
NODE_H = 36
DEC_W = 190
DEC_HEADER_H = 22
DEC_PORTS_H = 30
OP_W = 64
OP_H = 36
PORT_R = 6
PLUS_R = 9
SNAP_MARGIN = 22
NEW_STEP_DRAG_THRESHOLD = 50.0

BG_COLOR = QColor("#111827")
STEP_FILL = QColor("#2d3748")
GROUP_FILL = QColor("#1f3a5f")
DEC_FILL = QColor("#252036")
OP_FILL = QColor("#3b2f4f")
NODE_TEXT = QColor("#e5e7eb")
DIM_TEXT = QColor("#8b95a7")
NODE_BORDER = QColor("#94a3b8")
GLOW_BORDER = QColor("#22d3ee")      # cyan — "release here" affordance
ACTIVE_BORDER = QColor("#3b82f6")    # running step
DECIDING_BORDER = QColor("#f59e0b")  # prompt showing
DRAG_COLOR = QColor("#60a5fa")
SPINE_COLOR = QColor(150, 150, 150, 120)
TETHER_COLOR = QColor(139, 149, 167, 90)

KIND_COLORS = {
    "positive": QColor("#10b981"),
    "negative": QColor("#f59e0b"),
    "danger": QColor("#ef4444"),
    "neutral": QColor("#94a3b8"),
}
FLOW_COLOR = QColor("#3b82f6")
OP_COLORS = {"and": QColor("#8b5cf6"), "or": QColor("#14b8a6")}

# --- obstacle-avoiding edge routing (ported from flow_graph_dialog) ---

EDGE_CLEARANCE = 10.0
LANE_CLEARANCE = 36.0
_LANE_RETRY_STEP = 44.0
_LANE_RETRIES = 8


def _curve_between(start, end, start_dir=None):
    """Cubic between two free points. ``start_dir`` (unit QPointF) forces
    the exit tangent (ports on a shape's bottom edge leave downward);
    default is horizontal-tangent both ends."""
    path = QPainterPath(start)
    dx = max(40.0, min(160.0, abs(end.x() - start.x()) / 2 + 30.0))
    sign_out = 1.0 if end.x() >= start.x() else -1.0
    if start_dir is None:
        c1 = QPointF(start.x() + dx * sign_out, start.y())
    else:
        c1 = start + QPointF(start_dir.x() * dx, start_dir.y() * dx)
    c2 = QPointF(end.x() - dx * sign_out, end.y())
    path.cubicTo(c1, c2, end)
    return path


def path_is_clear(path, rects, samples=48):
    if not rects:
        return True
    for i in range(samples + 1):
        p = path.pointAtPercent(i / samples)
        for r in rects:
            if r.contains(p):
                return False
    return True


def _lane_candidate(side, source, target, end_point, rects):
    """One wrap-around cubic through a clear lane on ``side``. Returns
    (start, end, path) or None."""
    if side == "right":
        s = source.right_anchor()
        e = target.right_anchor() if target else end_point
    elif side == "left":
        s = source.left_anchor()
        e = target.left_anchor() if target else end_point
    elif side == "bottom":
        s = source.bottom_anchor()
        e = target.bottom_anchor() if target else end_point
    else:
        s = source.top_anchor()
        e = target.top_anchor() if target else end_point

    horizontal_lane = side in ("right", "left")
    if horizontal_lane:
        span_lo, span_hi = sorted((s.y(), e.y()))
        relevant = [r for r in rects
                    if r.bottom() >= span_lo - EDGE_CLEARANCE
                    and r.top() <= span_hi + EDGE_CLEARANCE]
        if side == "right":
            lane = max([r.right() for r in relevant] + [s.x(), e.x()]) \
                + LANE_CLEARANCE
            step = _LANE_RETRY_STEP
        else:
            lane = min([r.left() for r in relevant] + [s.x(), e.x()]) \
                - LANE_CLEARANCE
            step = -_LANE_RETRY_STEP
    else:
        span_lo, span_hi = sorted((s.x(), e.x()))
        relevant = [r for r in rects
                    if r.right() >= span_lo - EDGE_CLEARANCE
                    and r.left() <= span_hi + EDGE_CLEARANCE]
        if side == "bottom":
            lane = max([r.bottom() for r in relevant] + [s.y(), e.y()]) \
                + LANE_CLEARANCE
            step = _LANE_RETRY_STEP
        else:
            lane = min([r.top() for r in relevant] + [s.y(), e.y()]) \
                - LANE_CLEARANCE
            step = -_LANE_RETRY_STEP

    # The cubic sags toward its control points without reaching them, so
    # verify by sampling and push the lane further out until it passes.
    for _ in range(_LANE_RETRIES):
        path = QPainterPath(s)
        if horizontal_lane:
            c1, c2 = QPointF(lane, s.y()), QPointF(lane, e.y())
        else:
            c1, c2 = QPointF(s.x(), lane), QPointF(e.x(), lane)
        path.cubicTo(c1, c2, e)
        if path_is_clear(path, rects):
            return s, e, path
        lane += step
    return None


def route_edge_path(source, target, end_point, rects, start_dir=None):
    """Route from ``source`` (an anchored item or _PointAnchor) to
    ``target`` (or a free ``end_point``). Direct curve when clear, else
    the shortest verified wrap-around lane, else direct as last resort.
    Returns (start, end, path)."""
    ref = target.center() if target is not None else end_point
    start = source.side_anchor_toward(ref)
    end = (target.side_anchor_toward(source.center())
           if target is not None else end_point)
    direct = _curve_between(start, end, start_dir)
    if path_is_clear(direct, rects):
        return start, end, direct

    candidates = []
    for side in ("right", "left", "bottom", "top"):
        routed = _lane_candidate(side, source, target, end_point, rects)
        if routed is not None:
            candidates.append(routed)
    if candidates:
        return min(candidates, key=lambda c: c[2].length())
    return start, end, direct


class _PointAnchor:
    """Anchor adapter for edges that start at a specific port point."""

    def __init__(self, point):
        self._p = point

    def center(self):
        return self._p

    def side_anchor_toward(self, _):
        return self._p

    right_anchor = left_anchor = top_anchor = bottom_anchor = center


class _AnchoredRectItem(QGraphicsRectItem):
    """Base for all box shapes: anchors, snap zone, glow, live re-route."""

    def __init__(self, w, h, scene_ref, fill, movable=True):
        super().__init__(0, 0, w, h)
        self._scene_ref = scene_ref
        self._base_pen = QPen(NODE_BORDER, 1.2)
        self._state_pen = None
        self.setBrush(QBrush(fill))
        self.setPen(self._base_pen)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        if movable:
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)

    def _w(self):
        return self.rect().width()

    def _h(self):
        return self.rect().height()

    def center(self):
        return self.mapToScene(QPointF(self._w() / 2, self._h() / 2))

    def right_anchor(self):
        return self.mapToScene(QPointF(self._w(), self._h() / 2))

    def left_anchor(self):
        return self.mapToScene(QPointF(0, self._h() / 2))

    def top_anchor(self):
        return self.mapToScene(QPointF(self._w() / 2, 0))

    def bottom_anchor(self):
        return self.mapToScene(QPointF(self._w() / 2, self._h()))

    def side_anchor_toward(self, point):
        return (self.right_anchor() if point.x() >= self.center().x()
                else self.left_anchor())

    def snap_rect(self):
        r = self.mapRectToScene(self.rect())
        return r.adjusted(-SNAP_MARGIN, -SNAP_MARGIN,
                          SNAP_MARGIN, SNAP_MARGIN)

    def scene_rect(self):
        return self.mapRectToScene(self.rect())

    def set_glow(self, on):
        self.setPen(QPen(GLOW_BORDER, 2.6) if on
                    else (self._state_pen or self._base_pen))

    def set_state_pen(self, pen):
        """Run-state border (active/deciding); None restores base."""
        self._state_pen = pen
        self.setPen(pen or self._base_pen)

    def paint(self, painter, option, widget=None):
        # Selection tint instead of Qt's marching-ants rect.
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = self.pen()
        if self.isSelected() and pen.color() not in (
                GLOW_BORDER, ACTIVE_BORDER, DECIDING_BORDER):
            pen = QPen(DRAG_COLOR, 2.0)
        painter.setPen(pen)
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), 5, 5)

    def itemChange(self, change, value):
        if (change == QGraphicsItem.ItemScenePositionHasChanged
                and self._scene_ref is not None):
            self._scene_ref.on_item_moved(self)
        return super().itemChange(change, value)


class PortItem(QGraphicsEllipseItem):
    """Drag handle. role: "done" | "outcome" | "opout"."""

    def __init__(self, owner, role, out_dir, color, outcome_id=None):
        super().__init__(-PORT_R, -PORT_R, 2 * PORT_R, 2 * PORT_R, owner)
        self.owner = owner
        self.role = role
        self.out_dir = out_dir
        self.outcome_id = outcome_id
        self.setBrush(QBrush(color))
        self.setPen(QPen(Qt.NoPen))
        self.setAcceptHoverEvents(True)
        self.setZValue(3)

    def hoverEnterEvent(self, event):
        self.setScale(1.35)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setScale(1.0)
        super().hoverLeaveEvent(event)


class PlusButtonItem(QGraphicsEllipseItem):
    """The Miro-style ＋ plug on a step — opens the shape palette."""

    def __init__(self, node):
        super().__init__(-PLUS_R, -PLUS_R, 2 * PLUS_R, 2 * PLUS_R, node)
        self.node = node
        self.setBrush(QBrush(QColor("#374151")))
        self.setPen(QPen(QColor("#4b5563"), 1.0))
        self.setAcceptHoverEvents(True)
        self.setZValue(3)
        self.setToolTip("Add a shape: decisions from this step's columns, "
                        "or an AND operator")
        text = QGraphicsSimpleTextItem("＋", self)
        text.setBrush(QBrush(QColor("#cbd5e1")))
        f = QFont()
        f.setPointSizeF(9)
        text.setFont(f)
        br = text.boundingRect()
        text.setPos(-br.width() / 2, -br.height() / 2)

    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(DRAG_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(QColor("#374151")))
        super().hoverLeaveEvent(event)


class StepNodeItem(_AnchoredRectItem):
    """One row (step or group): a compact slab — order + name only.
    Parameters live in the table, not on the node."""

    def __init__(self, scene_ref, row, order_label):
        super().__init__(NODE_W, NODE_H, scene_ref,
                         GROUP_FILL if row.is_group else STEP_FILL)
        self.row = row
        self.setPos(*row.pos)
        self.setZValue(1)

        title = (f"▣ {row.name}" if row.is_group
                 else f"{order_label} · {row.name}")
        text = QGraphicsSimpleTextItem(title, self)
        text.setBrush(QBrush(NODE_TEXT))
        f = QFont()
        f.setPointSizeF(9.0)
        if row.is_group:
            f.setBold(True)
        text.setFont(f)
        text.setPos(10, (NODE_H - text.boundingRect().height()) / 2)

        # Done-port (completion route) on the right edge — steps only.
        self.done_port = None
        self.plus = None
        if not row.is_group:
            self.done_port = PortItem(self, "done", QPointF(1, 0),
                                      FLOW_COLOR)
            self.done_port.setPos(NODE_W, NODE_H / 2)
            self.done_port.setToolTip(
                "On completion → drag to a step/group to reroute; drop on "
                "blank space to add a step")
            self.plus = PlusButtonItem(self)
            self.plus.setPos(NODE_W / 2, NODE_H + PLUS_R + 3)

    def mouseDoubleClickEvent(self, event):
        self._scene_ref.window.rename_row(self.row.id)
        event.accept()

    def contextMenuEvent(self, event):
        self._scene_ref.window.row_menu(self.row.id, event.screenPos())
        event.accept()


class DecisionShapeItem(_AnchoredRectItem):
    """A placed decision: title bar + one colored port per outcome."""

    def __init__(self, scene_ref, dnode, spec, active, badge):
        super().__init__(DEC_W, DEC_HEADER_H + DEC_PORTS_H, scene_ref,
                         DEC_FILL)
        self.dnode = dnode
        self.spec = spec
        self.setPos(*dnode.pos)
        self.setZValue(1)
        pen = QPen(NODE_BORDER, 1.2, Qt.SolidLine)
        if not active:
            pen.setStyle(Qt.DotLine)
        self._base_pen = pen
        self.setPen(pen)

        title = f"⬥ {spec.title}"
        if badge:
            title += f"  {badge}"
        if not active:
            title += "  (off)"
        text = QGraphicsSimpleTextItem(title, self)
        text.setBrush(QBrush(NODE_TEXT if active else DIM_TEXT))
        f = QFont()
        f.setPointSizeF(8.0)
        f.setBold(True)
        text.setFont(f)
        text.setPos(8, 5)

        self.ports = {}
        n = len(spec.outcomes)
        for k, outcome in enumerate(spec.outcomes):
            x = DEC_W * (k + 1) / (n + 1)
            color = KIND_COLORS.get(outcome.kind, KIND_COLORS["neutral"])
            label = QGraphicsSimpleTextItem(outcome.label, self)
            label.setBrush(QBrush(color if active else DIM_TEXT))
            lf = QFont()
            lf.setPointSizeF(7.0)
            label.setFont(lf)
            br = label.boundingRect()
            label.setPos(x - br.width() / 2, DEC_HEADER_H + 2)
            port = PortItem(self, "outcome", QPointF(0, 1), color,
                            outcome_id=outcome.id)
            port.setPos(x, DEC_HEADER_H + DEC_PORTS_H - 4)
            self.ports[outcome.id] = port

    def refresh_port_tooltips(self, protocol):
        for outcome in self.spec.outcomes:
            target = self.dnode.routes.get(
                outcome.id,
                self.spec.default_routes.get(outcome.id))
            origin = ("custom" if outcome.id in self.dnode.routes
                      else "default")
            self.ports[outcome.id].setToolTip(
                f"{outcome.label} → {protocol.describe_target(target)} "
                f"({origin})\nDrag to a step/group (route), an AND/OR "
                f"shape (feed), another decision of this step (resolve "
                f"serially), or blank space (new step).")

    def contextMenuEvent(self, event):
        self._scene_ref.window.decision_menu(self.dnode.id,
                                             event.screenPos())
        event.accept()


class OpNodeItem(_AnchoredRectItem):
    """A logic combiner shape (AND / OR)."""

    def __init__(self, scene_ref, opnode):
        super().__init__(OP_W, OP_H, scene_ref, OP_FILL)
        self.opnode = opnode
        self.setPos(*opnode.pos)
        self.setZValue(1)
        color = OP_COLORS.get(opnode.kind, OP_COLORS["and"])
        self._base_pen = QPen(color, 1.4)
        self.setPen(self._base_pen)

        text = QGraphicsSimpleTextItem(opnode.kind.upper(), self)
        text.setBrush(QBrush(NODE_TEXT))
        f = QFont()
        f.setPointSizeF(9.0)
        f.setBold(True)
        text.setFont(f)
        br = text.boundingRect()
        text.setPos((OP_W - br.width()) / 2, (OP_H - br.height()) / 2)

        self.out_port = PortItem(self, "opout", QPointF(1, 0), color)
        self.out_port.setPos(OP_W, OP_H / 2)
        quant = "ALL" if opnode.kind == "and" else "ANY"
        self.out_port.setToolTip(
            f"Combined route: fires when {quant} connected outcome(s) are "
            f"chosen in the same round. Drag to a step/group.")

    def contextMenuEvent(self, event):
        self._scene_ref.window.op_menu(self.opnode.id, event.screenPos())
        event.accept()


class EdgeItem(QGraphicsPathItem):
    """A routed connection. kind:
    "flow" (done→row) · "outcome" (decision→row) · "feed" (outcome→AND) ·
    "op" (AND→row) · "spine" (implicit next, dashed) · "tether"
    (step→its decision shape, dotted, decorative)."""

    def __init__(self, scene_ref, kind, src_item, dst_item, color,
                 label="", src_port=None, payload=None):
        super().__init__()
        self._scene_ref = scene_ref
        self.kind = kind
        self.src_item = src_item
        self.dst_item = dst_item
        self.src_port = src_port          # PortItem for port-anchored edges
        self.payload = payload            # model refs for deletion
        self._color = color
        self._arrow = QPolygonF()

        width = 1.8
        style = Qt.SolidLine
        if kind == "spine":
            width, style = 1.0, Qt.DashLine
        elif kind == "tether":
            width, style = 1.0, Qt.DotLine
        elif kind == "chain":
            style = Qt.DashLine
        self.setPen(QPen(color, width, style))
        self.setZValue(-1 if kind not in ("spine", "tether") else -3)
        if kind in ("flow", "outcome", "feed", "op", "chain"):
            self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        self._label = None
        if label:
            self._label = QGraphicsSimpleTextItem(label, self)
            f = QFont()
            f.setPointSizeF(7.5)
            self._label.setFont(f)
            self._label.setBrush(QBrush(color))
        self.update_path()

    def update_path(self):
        if self.kind in ("spine", "tether"):
            start = self.src_item.side_anchor_toward(self.dst_item.center())
            end = self.dst_item.side_anchor_toward(self.src_item.center())
            if self.kind == "tether":
                start = self.src_item.bottom_anchor()
                end = self.dst_item.top_anchor()
            path = QPainterPath(start)
            path.lineTo(end)
            self.prepareGeometryChange()
            self.setPath(path)
            self._arrow = QPolygonF()
            return

        rects = self._scene_ref.obstacle_rects(
            exclude={self.src_item, self.dst_item})
        if self.src_port is not None:
            start_pt = self.src_port.scenePos()
            if self.src_item is self.dst_item:
                # Self-loop: out the port, back into the top edge.
                end = self.src_item.mapToScene(
                    QPointF(self.src_item.rect().width() - 18, 0))
                path = QPainterPath(start_pt)
                c1 = start_pt + QPointF(90, 60)
                c2 = end + QPointF(90, -60)
                path.cubicTo(c1, c2, end)
            else:
                anchor = _PointAnchor(start_pt)
                _s, end, path = route_edge_path(
                    anchor, self.dst_item, None, rects,
                    start_dir=self.src_port.out_dir)
        else:
            _s, end, path = route_edge_path(
                self.src_item, self.dst_item, None, rects)
        self.prepareGeometryChange()
        self.setPath(path)

        # Arrowhead along the final direction.
        angle_point = path.pointAtPercent(0.97)
        direction = end - angle_point
        length = max(1e-6,
                     (direction.x() ** 2 + direction.y() ** 2) ** 0.5)
        ux, uy = direction.x() / length, direction.y() / length
        size = 8.0
        base = end - QPointF(ux * size, uy * size)
        normal = QPointF(-uy, ux)
        self._arrow = QPolygonF([
            end,
            base + QPointF(normal.x() * size * 0.5,
                           normal.y() * size * 0.5),
            base - QPointF(normal.x() * size * 0.5,
                           normal.y() * size * 0.5),
        ])
        if self._label is not None:
            mid = path.pointAtPercent(0.5)
            self._label.setPos(mid + QPointF(6, -14))

    def boundingRect(self):
        return super().boundingRect().united(
            self._arrow.boundingRect()).adjusted(-6, -6, 6, 6)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(14.0)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(self.pen())
        if self.isSelected():
            pen.setColor(GLOW_BORDER)
            pen.setWidthF(2.6)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())
        if not self._arrow.isEmpty():
            painter.setBrush(QBrush(pen.color()))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(self._arrow)

    def contextMenuEvent(self, event):
        if self.kind in ("flow", "outcome", "feed", "op", "chain"):
            self._scene_ref.window.edge_menu(self, event.screenPos())
            event.accept()
        else:
            event.ignore()


class FlowchartScene(QGraphicsScene):
    """Owns the items; commits mutations through the window."""

    def __init__(self, window, protocol):
        super().__init__()
        self.window = window
        self.protocol = protocol
        self.row_items = {}       # row_id -> StepNodeItem
        self.dec_items = {}       # decision_node_id -> DecisionShapeItem
        self.op_items = {}        # op_node_id -> OpNodeItem
        self.edges = []
        self._building = False
        self._drag_port = None
        self._drag_line = None
        self._drag_glow = None
        self._drag_start = None
        self._drag_ghost = None
        self.setBackgroundBrush(QBrush(BG_COLOR))

    # -- build -----------------------------------------------------------

    def rebuild(self):
        self._cancel_edge_drag()
        self.clearSelection()
        self.clear()
        self.row_items = {}
        self.dec_items = {}
        self.op_items = {}
        self.edges = []
        proto = self.protocol

        leaves = proto.leaves()
        leaf_no = {leaf.id: str(i + 1) for i, leaf in enumerate(leaves)}
        self._building = True
        try:
            for row, _depth in proto.iter_rows():
                item = StepNodeItem(self, row, leaf_no.get(row.id, ""))
                self.addItem(item)
                self.row_items[row.id] = item

            for dn in proto.decision_nodes:
                spec = proto.spec_by_id(dn.decision_id)
                step = proto.row_by_id(dn.step_id)
                if spec is None or step is None:
                    continue
                handler = next(
                    (c.handler for c in proto.columns
                     if c.model.col_id == spec.provider_col_id), None)
                active = (handler.is_decision_active(spec, step)
                          if handler else True)
                badge = ""
                if dn.mode == "auto":
                    badge = "[auto]"
                elif dn.mode == "auto_first" and dn.auto_after is not None:
                    badge = f"[auto ×{dn.auto_after} → ask]"
                elif dn.auto_after is not None:
                    badge = f"[ask ×{dn.auto_after} → auto]"
                item = DecisionShapeItem(self, dn, spec, active, badge)
                self.addItem(item)
                self.dec_items[dn.id] = item

            for op in proto.op_nodes:
                item = OpNodeItem(self, op)
                self.addItem(item)
                self.op_items[op.id] = item

            self._build_edges(leaves)
        finally:
            self._building = False
        for e in self.edges:
            e.update_path()
        for item in self.dec_items.values():
            item.refresh_port_tooltips(proto)
        rect = self.itemsBoundingRect().adjusted(-150, -150, 150, 150)
        self.setSceneRect(rect)

    def _build_edges(self, leaves):
        proto = self.protocol
        from .model import NEXT

        # Implicit fall-through spine between consecutive leaves.
        for a, b in zip(leaves, leaves[1:]):
            if a.next_target == NEXT:
                self._add(EdgeItem(self, "spine", self.row_items[a.id],
                                   self.row_items[b.id], SPINE_COLOR))
        # Explicit completion routes.
        for leaf in leaves:
            if leaf.next_target != NEXT:
                dst = self.row_items.get(leaf.next_target)
                if dst is not None:
                    self._add(EdgeItem(
                        self, "flow", self.row_items[leaf.id], dst,
                        FLOW_COLOR, label="done",
                        src_port=self.row_items[leaf.id].done_port,
                        payload=("flow", leaf.id)))
        # Tethers + outcome/feed edges from decision shapes.
        feeds = {(dn_id, oid)
                 for op in proto.op_nodes for dn_id, oid in op.inputs}
        for dn in proto.decision_nodes:
            dec_item = self.dec_items.get(dn.id)
            step_item = self.row_items.get(dn.step_id)
            if dec_item is None:
                continue
            if step_item is not None:
                self._add(EdgeItem(self, "tether", step_item, dec_item,
                                   TETHER_COLOR))
            for outcome in dec_item.spec.outcomes:
                target = dn.routes.get(outcome.id)
                if not target:
                    continue
                color = KIND_COLORS.get(outcome.kind,
                                        KIND_COLORS["neutral"])
                dst = self.row_items.get(target)
                if dst is not None:
                    self._add(EdgeItem(
                        self, "outcome", dec_item, dst, color,
                        label=outcome.label,
                        src_port=dec_item.ports[outcome.id],
                        payload=("outcome", dn.id, outcome.id)))
                    continue
                # Chain: outcome routed to a sibling decision shape —
                # "then resolve that decision" (serial resolution).
                chain_dst = self.dec_items.get(target)
                if chain_dst is not None:
                    self._add(EdgeItem(
                        self, "chain", dec_item, chain_dst, color,
                        label=f"{outcome.label} → then",
                        src_port=dec_item.ports[outcome.id],
                        payload=("outcome", dn.id, outcome.id)))
        # Outcome → AND feeds and AND → target routes.
        for op in proto.op_nodes:
            op_item = self.op_items.get(op.id)
            if op_item is None:
                continue
            for dn_id, oid in op.inputs:
                dec_item = self.dec_items.get(dn_id)
                if dec_item is None or oid not in dec_item.ports:
                    continue
                outcome = dec_item.spec.outcome_by_id(oid)
                color = KIND_COLORS.get(outcome.kind,
                                        KIND_COLORS["neutral"])
                self._add(EdgeItem(
                    self, "feed", dec_item, op_item, color,
                    label=outcome.label,
                    src_port=dec_item.ports[oid],
                    payload=("feed", op.id, dn_id, oid)))
            if op.target is not None:
                dst = self.row_items.get(op.target)
                if dst is not None:
                    self._add(EdgeItem(
                        self, "op", op_item, dst,
                        OP_COLORS.get(op.kind, OP_COLORS["and"]),
                        label=op.kind.upper(),
                        src_port=op_item.out_port,
                        payload=("op", op.id)))

    def _add(self, edge):
        self.addItem(edge)
        self.edges.append(edge)

    # -- routing helpers -------------------------------------------------

    def obstacle_rects(self, exclude=()):
        rects = []
        for item in (list(self.row_items.values())
                     + list(self.dec_items.values())
                     + list(self.op_items.values())):
            if item in exclude:
                continue
            rects.append(item.scene_rect().adjusted(
                -EDGE_CLEARANCE, -EDGE_CLEARANCE,
                EDGE_CLEARANCE, EDGE_CLEARANCE))
        return rects

    def on_item_moved(self, item):
        if self._building:
            return
        # Persist position on the model object.
        pos = (item.pos().x(), item.pos().y())
        if isinstance(item, StepNodeItem):
            item.row.pos = pos
        elif isinstance(item, DecisionShapeItem):
            item.dnode.pos = pos
        elif isinstance(item, OpNodeItem):
            item.opnode.pos = pos
        # Every edge: the moved box may block/clear routes between others.
        for e in self.edges:
            e.update_path()

    # -- run-state visuals -----------------------------------------------

    def set_row_state(self, row_id, state):
        item = self.row_items.get(row_id)
        if item is None:
            return
        pen = {"active": QPen(ACTIVE_BORDER, 2.6),
               "deciding": QPen(DECIDING_BORDER, 2.6)}.get(state)
        item.set_state_pen(pen)

    def set_decision_state(self, dn_id, on):
        item = self.dec_items.get(dn_id)
        if item is not None:
            item.set_state_pen(QPen(DECIDING_BORDER, 2.6) if on else None)

    def clear_run_states(self):
        for item in list(self.row_items.values()) \
                + list(self.dec_items.values()):
            item.set_state_pen(None)

    # -- selection helpers -----------------------------------------------

    def selected_row_ids(self):
        return [i.row.id for i in self.selectedItems()
                if isinstance(i, StepNodeItem)]

    # -- port dragging ---------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            for item in self.items(event.scenePos()):
                if isinstance(item, PlusButtonItem):
                    self.window.open_shape_palette(
                        item.node.row.id,
                        event.screenPos() if hasattr(event, "screenPos")
                        else None,
                        item.mapToScene(QPointF(0, 0)))
                    event.accept()
                    return
                if isinstance(item, PortItem):
                    self._drag_port = item
                    self._drag_start = item.scenePos()
                    self._drag_line = QGraphicsPathItem()
                    self._drag_line.setPen(
                        QPen(DRAG_COLOR, 1.8, Qt.DashLine))
                    self._drag_line.setZValue(15)
                    self.addItem(self._drag_line)
                    self._update_drag(event.scenePos())
                    event.accept()
                    return
        super().mousePressEvent(event)

    def _snap_target_at(self, scene_pos):
        """Nearest valid drop target whose snap zone contains the point."""
        port = self._drag_port
        src_owner = port.owner
        candidates = []
        pools = [self.row_items.values()]
        if port.role == "outcome":
            pools.append(self.op_items.values())
            pools.append(self.dec_items.values())   # chain targets
        for pool in pools:
            for item in pool:
                # A done-port can't target its own step (retries belong to
                # decision outcomes); an outcome port CAN target its
                # owning step's node — that's the retry loop.
                if item is src_owner:
                    continue
                if item.snap_rect().contains(scene_pos):
                    c = item.center()
                    d2 = ((c.x() - scene_pos.x()) ** 2
                          + (c.y() - scene_pos.y()) ** 2)
                    candidates.append((d2, item))
        if not candidates:
            return None
        return min(candidates, key=lambda pair: pair[0])[1]

    def _update_drag(self, scene_pos):
        target = self._snap_target_at(scene_pos)
        if target is not self._drag_glow:
            if self._drag_glow is not None:
                self._drag_glow.set_glow(False)
            self._drag_glow = target
            if target is not None:
                target.set_glow(True)
        far_enough = ((scene_pos - self._drag_start).manhattanLength()
                      > NEW_STEP_DRAG_THRESHOLD)
        if target is None and far_enough:
            self._show_ghost(scene_pos)
        else:
            self._hide_ghost()
        anchor = _PointAnchor(self._drag_port.scenePos())
        rects = self.obstacle_rects(
            exclude={self._drag_port.owner, target}
            if target else {self._drag_port.owner})
        _s, _e, path = route_edge_path(
            anchor, target, scene_pos, rects,
            start_dir=self._drag_port.out_dir)
        self._drag_line.setPath(path)

    def _show_ghost(self, scene_pos):
        if self._drag_ghost is None:
            ghost = QGraphicsRectItem(0, 0, NODE_W, NODE_H)
            ghost.setPen(QPen(DRAG_COLOR, 1.4, Qt.DashLine))
            ghost.setBrush(QBrush(QColor(96, 165, 250, 28)))
            ghost.setZValue(14)
            text = QGraphicsSimpleTextItem("＋ New step", ghost)
            text.setBrush(QBrush(DRAG_COLOR))
            f = QFont()
            f.setPointSizeF(9.0)
            text.setFont(f)
            text.setPos(10, (NODE_H - text.boundingRect().height()) / 2)
            self.addItem(ghost)
            self._drag_ghost = ghost
        self._drag_ghost.setPos(scene_pos - QPointF(0, NODE_H / 2))
        self._drag_ghost.show()

    def _hide_ghost(self):
        if self._drag_ghost is not None:
            self._drag_ghost.hide()

    def _cancel_edge_drag(self):
        if self._drag_glow is not None:
            self._drag_glow.set_glow(False)
            self._drag_glow = None
        if self._drag_line is not None:
            self.removeItem(self._drag_line)
            self._drag_line = None
        if self._drag_ghost is not None:
            self.removeItem(self._drag_ghost)
            self._drag_ghost = None
        self._drag_port = None
        self._drag_start = None

    def mouseMoveEvent(self, event):
        if self._drag_port is not None and self._drag_line is not None:
            self._update_drag(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_port is not None:
            port = self._drag_port
            target = self._drag_glow
            ghost_armed = (self._drag_ghost is not None
                           and self._drag_ghost.isVisible())
            ghost_pos = (self._drag_ghost.pos() if ghost_armed else None)
            self._cancel_edge_drag()
            if target is not None:
                self.window.commit_port_drop(port, target)
            elif ghost_armed:
                self.window.commit_port_drop_on_blank(
                    port, (ghost_pos.x(), ghost_pos.y()))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self._drag_port is not None:
            self._cancel_edge_drag()
            event.accept()
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.window.delete_selected()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        if self.items(event.scenePos()):
            super().contextMenuEvent(event)
            return
        self.window.blank_menu(event.screenPos())
        event.accept()


class FlowchartView(QGraphicsView):
    """Rubber-band selection on blank space (Miro-style), middle-mouse
    pan, Ctrl+wheel zoom — same feel as the xuhkrc flow view."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing
                            | QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self._pan_last = None

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            current = self.transform().m11()
            if 0.15 < current * factor < 4.0:
                self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._pan_last = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_last is not None:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and self._pan_last is not None:
            self._pan_last = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def fit_all(self):
        rect = self.scene().itemsBoundingRect().adjusted(-60, -60, 60, 60)
        if not rect.isEmpty():
            self.fitInView(rect, Qt.KeepAspectRatio)
            if self.transform().m11() > 1.0:
                self.setTransform(self.transform().scale(
                    1 / self.transform().m11(),
                    1 / self.transform().m11()))
