"""Node-graph canvas: step slabs inside group frames, decision/AND-OR
shapes, terminal Stop/Finish nodes, and obstacle-avoiding routed edges.

Look and interaction follow the ``claude/protocol-controls-branching-xuhkrc``
branch's flow view: dark canvas, slim boxes, edges that wrap around
intervening boxes (``route_edge_path``), snap-to-node with a cyan glow, a
"＋ New step" ghost when a drag is released over blank space, rubber-band
multi-select with group/ungroup, middle-mouse pan and Ctrl+wheel zoom.

On top of that, this file adds:

  * **Group frames** — a group renders as a container outline enclosing
    its member items (Miro-frame style). Dragging the title bar moves the
    whole subtree; the ▾ toggle collapses the group to a single chip.
    While collapsed, edges to interior steps re-aim at the chip and
    edges wholly inside it disappear.
  * **Terminal nodes** — always-present ⏹ Stop and ▦ Finish nodes.
    Explicit abort/finish routes draw as real edges to them, and ports
    dragged onto them set those routes.
  * **Default-route glyphs** — an outcome that keeps its provider
    default shows a small glyph after its label (↻ retry-self, → next,
    ⏹ abort, ▦ finish) so unrouted behaviour is visible without hovering.
  * **Run trail & toasts** — the edge the executor just followed flashes
    hot and recent edges stay warm; silent auto-answers and group repeat
    passes pop a short toast next to the responsible shape.

All mutations go through the window (``commit_*``/``delete_selected``)
which snapshots for undo and rebuilds the scene from the model; node
drags do NOT rebuild — edges re-route live and positions persist on the
model objects (move-undo is staged on press and committed on release).
"""

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPainterPathStroker,
    QPen, QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem,
    QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsView,
)

from .model import ABORT, END, NEXT, SELF

# --- layout / style constants (palette from the xuhkrc flow view) ---

NODE_W = 190
NODE_H = 36
DEC_W = 190
DEC_HEADER_H = 22
DEC_PORTS_H = 30
OP_W = 64
OP_H = 36
TERM_W = 110
TERM_H = 30
PORT_R = 6
PLUS_R = 9
SNAP_MARGIN = 22
NEW_STEP_DRAG_THRESHOLD = 50.0
FRAME_PAD = 16
FRAME_TITLE_H = 24

BG_COLOR = QColor("#111827")
STEP_FILL = QColor("#2d3748")
GROUP_FILL = QColor("#1f3a5f")
FRAME_FILL = QColor(31, 58, 95, 60)
FRAME_BORDER = QColor("#3b5b8a")
DEC_FILL = QColor("#252036")
OP_FILL = QColor("#3b2f4f")
TERM_STOP_FILL = QColor("#4a1d1d")
TERM_END_FILL = QColor("#1d3a2a")
NODE_TEXT = QColor("#e5e7eb")
DIM_TEXT = QColor("#8b95a7")
NODE_BORDER = QColor("#94a3b8")
GLOW_BORDER = QColor("#22d3ee")      # cyan — "release here" affordance
ACTIVE_BORDER = QColor("#3b82f6")    # running step
DECIDING_BORDER = QColor("#f59e0b")  # prompt showing
RECENT_BORDER = QColor(59, 130, 246, 120)   # just-executed trail
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

#: Glyph shown after an outcome label when it keeps its provider default.
SENTINEL_GLYPHS = {SELF: "↻", NEXT: "→", ABORT: "⏹", END: "▦"}

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
    """Base for all box shapes: anchors, snap zone, glow, live re-route.
    Anchors are computed from ``rect()`` (which may not start at the
    item origin — group frames keep a scene-coordinate rect)."""

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
        self.setAcceptHoverEvents(True)

    def _hover_eligible(self):
        return True

    def hoverEnterEvent(self, event):
        if self._hover_eligible() and self._scene_ref is not None:
            self._scene_ref.set_hover_item(self, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self._scene_ref is not None:
            self._scene_ref.set_hover_item(self, False)
        super().hoverLeaveEvent(event)

    def center(self):
        return self.mapToScene(self.rect().center())

    def right_anchor(self):
        r = self.rect()
        return self.mapToScene(QPointF(r.right(), r.center().y()))

    def left_anchor(self):
        r = self.rect()
        return self.mapToScene(QPointF(r.left(), r.center().y()))

    def top_anchor(self):
        r = self.rect()
        return self.mapToScene(QPointF(r.center().x(), r.top()))

    def bottom_anchor(self):
        r = self.rect()
        return self.mapToScene(QPointF(r.center().x(), r.bottom()))

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
        """Run-state border (active/deciding/recent); None restores base."""
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
                        "or an AND/OR operator")
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
    """One leaf step: a compact slab — order + name only. Parameters
    live in the table, not on the node."""

    def __init__(self, scene_ref, row, order_label):
        super().__init__(NODE_W, NODE_H, scene_ref, STEP_FILL)
        self.row = row
        self.setPos(*row.pos)
        self.setZValue(1)

        title = f"{order_label} · {row.name}"
        if row.repetitions > 1:
            title += f"  ×{row.repetitions}"
        text = QGraphicsSimpleTextItem(title, self)
        text.setBrush(QBrush(NODE_TEXT))
        f = QFont()
        f.setPointSizeF(9.0)
        text.setFont(f)
        # Elide long names to the slab width.
        while (text.boundingRect().width() > NODE_W - 24
               and len(text.text()) > 4):
            text.setText(text.text()[:-2].rstrip() + "…")
        text.setPos(10, (NODE_H - text.boundingRect().height()) / 2)
        self.setToolTip(row.name)

        self.done_port = PortItem(self, "done", QPointF(1, 0), FLOW_COLOR)
        self.done_port.setPos(NODE_W, NODE_H / 2)
        self.done_port.setToolTip(
            "On completion → drag to a step, a group frame, ⏹/▦, or "
            "blank space (new step)")
        self.plus = PlusButtonItem(self)
        self.plus.setPos(NODE_W / 2, NODE_H + PLUS_R + 3)

    def mouseDoubleClickEvent(self, event):
        self._scene_ref.window.rename_row(self.row.id)
        event.accept()

    def contextMenuEvent(self, event):
        self._scene_ref.window.row_menu(self.row.id, event.screenPos())
        event.accept()


class GroupFrameItem(_AnchoredRectItem):
    """A group. Expanded: a container outline fitted around its member
    items — drag the title band to move the whole subtree, click ▾ to
    collapse. Collapsed: a single movable chip standing in for every
    interior item."""

    CHIP_W = 250

    def __init__(self, scene_ref, row):
        self.row = row
        self.collapsed = row.collapsed
        super().__init__(self.CHIP_W if row.collapsed else NODE_W, NODE_H,
                         scene_ref,
                         GROUP_FILL if self.collapsed else FRAME_FILL,
                         movable=self.collapsed)
        self._base_pen = (QPen(NODE_BORDER, 1.2) if self.collapsed
                          else QPen(FRAME_BORDER, 1.2, Qt.DashLine))
        self.setPen(self._base_pen)
        self.setZValue(1 if self.collapsed else -4)
        # Filled at rebuild: items a title-band drag moves / fit uses.
        self.move_items = []
        self.fit_items = []
        self._dragging = False
        self._drag_last = None
        if self.collapsed:
            self.setPos(*row.pos)

    def _hover_eligible(self):
        # Expanded frames cover a large area — hover-lighting their
        # edges constantly would be noise; chips behave like nodes.
        return self.collapsed

    # -- text helpers ---------------------------------------------------

    def _title(self):
        toggle = "▸" if self.collapsed else "▾"
        title = f"{toggle}  ▣ {self.row.name}"
        if self.row.repetitions > 1:
            title += f"  ×{self.row.repetitions}"
        if self.collapsed:
            n = sum(1 for r in _subtree(self.row) if not r.is_group)
            title += f"  ({n} steps)"
        return title

    def _toggle_rect(self):
        r = self.rect()
        return QRectF(r.left() + 4, r.top() + 3, 22, FRAME_TITLE_H - 4)

    def _title_rect(self):
        r = self.rect()
        return QRectF(r.left(), r.top(), r.width(), FRAME_TITLE_H)

    # -- geometry -------------------------------------------------------

    def fit(self):
        """Expanded frames: wrap the member items (scene coords)."""
        if self.collapsed or not self.fit_items:
            return
        union = None
        for item in self.fit_items:
            r = item.sceneBoundingRect()
            union = r if union is None else union.united(r)
        rect = union.adjusted(-FRAME_PAD, -FRAME_PAD - FRAME_TITLE_H,
                              FRAME_PAD, FRAME_PAD)
        self.prepareGeometryChange()
        self.setPos(0, 0)
        self.setRect(rect)
        self.row.pos = (rect.left(), rect.top())

    # -- paint ----------------------------------------------------------

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        pen = self.pen()
        if self.isSelected() and pen.color() not in (
                GLOW_BORDER, ACTIVE_BORDER, DECIDING_BORDER):
            pen = QPen(DRAG_COLOR, 2.0)
        painter.setPen(pen)
        painter.setBrush(self.brush())
        painter.drawRoundedRect(r, 6, 6)
        if not self.collapsed:
            band = QPen(FRAME_BORDER, 0.8)
            painter.setPen(band)
            painter.drawLine(
                QPointF(r.left(), r.top() + FRAME_TITLE_H),
                QPointF(r.right(), r.top() + FRAME_TITLE_H))
        painter.setPen(QPen(NODE_TEXT))
        f = QFont()
        f.setPointSizeF(9.0)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(
            QRectF(r.left() + 8, r.top(),
                   r.width() - 16, FRAME_TITLE_H if not self.collapsed
                   else r.height()),
            Qt.AlignVCenter | Qt.AlignLeft, self._title())

    # -- interaction ----------------------------------------------------

    def mousePressEvent(self, event):
        if self._toggle_rect().contains(event.pos()):
            self._scene_ref.window.toggle_group_collapse(self.row.id)
            event.accept()
            return
        if self.collapsed:
            super().mousePressEvent(event)     # normal chip move
            return
        if self._title_rect().contains(event.pos()):
            self._dragging = True
            self._drag_last = event.scenePos()
            self.setSelected(True)
            event.accept()
            return
        event.ignore()   # interior clicks fall through (rubber band etc.)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_last
            self._drag_last = event.scenePos()
            for item in self.move_items:
                item.setPos(item.pos() + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._scene_ref.window.rename_row(self.row.id)
        event.accept()

    def contextMenuEvent(self, event):
        self._scene_ref.window.row_menu(self.row.id, event.screenPos())
        event.accept()


class DecisionShapeItem(_AnchoredRectItem):
    """A placed decision: title bar + one colored port per outcome.
    Outcomes that keep their provider default show a glyph after the
    label (↻ retry · → next · ⏹ abort · ▦ finish)."""

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
            label_text = dnode.label_for(outcome)
            if outcome.id not in dnode.routes:
                default = spec.default_routes.get(outcome.id, NEXT)
                glyph = SENTINEL_GLYPHS.get(default, "↦")
                label_text += f" {glyph}"
            label = QGraphicsSimpleTextItem(label_text, self)
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
                f"{self.dnode.label_for(outcome)} → "
                f"{protocol.describe_target(target)} "
                f"({origin})\nDrag to a step/group (route), an AND/OR "
                f"shape (feed), another decision of this step (resolve "
                f"serially), ⏹/▦ (abort/finish), or blank space "
                f"(new step).")

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
            f"chosen in the same round. Drag to a step/group or ⏹/▦.")
        # Inert combiners (no inputs or no target) are called out.
        if not opnode.inputs or opnode.target is None:
            self._base_pen = QPen(color, 1.4, Qt.DashLine)
            self.setPen(self._base_pen)
            why = ("no inputs" if not opnode.inputs else "no target")
            warn = QGraphicsSimpleTextItem(f"⚠ unwired ({why})", self)
            warn.setBrush(QBrush(QColor("#fbbf24")))
            wf = QFont()
            wf.setPointSizeF(7.0)
            warn.setFont(wf)
            warn.setPos(0, OP_H + 3)

    def contextMenuEvent(self, event):
        self._scene_ref.window.op_menu(self.opnode.id, event.screenPos())
        event.accept()


class TerminalNodeItem(_AnchoredRectItem):
    """Always-present ⏹ Stop / ▦ Finish node — a visible drop target for
    abort/finish routes."""

    def __init__(self, scene_ref, kind, pos):
        fill = TERM_STOP_FILL if kind == "stop" else TERM_END_FILL
        super().__init__(TERM_W, TERM_H, scene_ref, fill)
        self.kind = kind
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setPos(*pos)
        self.setZValue(1)
        label = "⏹ Stop" if kind == "stop" else "▦ Finish"
        text = QGraphicsSimpleTextItem(label, self)
        text.setBrush(QBrush(NODE_TEXT))
        f = QFont()
        f.setPointSizeF(8.5)
        f.setBold(True)
        text.setFont(f)
        text.setPos(10, (TERM_H - text.boundingRect().height()) / 2)
        self.setToolTip(
            "Drop a port here to route it to "
            + ("abort protocol" if kind == "stop" else "finish protocol"))


class EdgeItem(QGraphicsPathItem):
    """A routed connection. kind:
    "flow" (done→row) · "outcome" (decision→row/terminal) · "chain"
    (decision→sibling decision) · "feed" (outcome→op) · "op"
    (op→row/terminal) · "spine" (implicit next, dashed) · "tether"
    (step→its decision shape, dotted, decorative).

    ``heat``: 0 normal, 1 recently traversed (warm), 2 just traversed
    (hot) — the run trail."""

    def __init__(self, scene_ref, kind, src_item, dst_item, color,
                 label="", src_port=None, payload=None):
        super().__init__()
        self._scene_ref = scene_ref
        self.kind = kind
        self.src_item = src_item
        self.dst_item = dst_item
        self.src_port = src_port          # PortItem for port-anchored edges
        self.payload = payload            # model refs for deletion/flash
        self._color = color
        self._arrow = QPolygonF()
        self._heat = 0
        self._hover = False

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

    def set_heat(self, level):
        if self._heat != level:
            self._heat = level
            self.update()

    def set_hover(self, on):
        if self._hover != on:
            self._hover = on
            self.update()

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
            if self.kind == "spine":
                self._set_arrow(end, end - start)
            else:
                self._arrow = QPolygonF()
            return

        rects = self._scene_ref.obstacle_rects(
            exclude={self.src_item, self.dst_item})
        use_port = (self.src_port is not None
                    and self.src_port.owner is self.src_item)
        if use_port:
            start_pt = self.src_port.scenePos()
            if self.src_item is self.dst_item:
                # Self-loop: out the port, back into the top edge.
                r = self.src_item.rect()
                end = self.src_item.mapToScene(
                    QPointF(r.right() - 18, r.top()))
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

        angle_point = path.pointAtPercent(0.97)
        self._set_arrow(end, end - angle_point)
        if self._label is not None:
            self._label.setPos(self._label_point(path))

    def _label_point(self, path):
        """Pick a label spot along the path that isn't buried under a
        node box (sampled), preferring the midpoint."""
        rects = self._scene_ref.obstacle_rects()
        for t in (0.5, 0.35, 0.65, 0.25, 0.75, 0.15):
            p = path.pointAtPercent(t)
            probe = QRectF(p.x(), p.y() - 16, 46, 16)
            if not any(r.intersects(probe) for r in rects):
                return p + QPointF(6, -14)
        return path.pointAtPercent(0.5) + QPointF(6, -14)

    def _set_arrow(self, end, direction):
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
        elif self._heat == 2:
            pen.setColor(self._color.lighter(165))
            pen.setWidthF(3.4)
        elif self._heat == 1:
            pen.setWidthF(2.6)
        elif self._hover:
            pen.setColor(self._color.lighter(135))
            pen.setWidthF(pen.widthF() + 1.0)
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


class ToastItem(QGraphicsRectItem):
    """Short-lived note pinned next to a shape (auto answers, group
    passes)."""

    def __init__(self, text):
        super().__init__()
        label = QGraphicsSimpleTextItem(text, self)
        label.setBrush(QBrush(QColor("#111827")))
        f = QFont()
        f.setPointSizeF(8.0)
        f.setBold(True)
        label.setFont(f)
        br = label.boundingRect()
        self.setRect(-6, -4, br.width() + 12, br.height() + 8)
        label.setPos(0, 0)
        self.setBrush(QBrush(QColor("#fbbf24")))
        self.setPen(QPen(Qt.NoPen))
        self.setZValue(30)


def _subtree(row):
    yield row
    if row.is_group:
        for child in row.children:
            yield from _subtree(child)


class FlowchartScene(QGraphicsScene):
    """Owns the items; commits mutations through the window."""

    def __init__(self, window, protocol):
        super().__init__()
        self.window = window
        self.protocol = protocol
        self.row_items = {}       # step row_id -> StepNodeItem
        self.frame_items = {}     # group row_id -> GroupFrameItem
        self.dec_items = {}       # decision_node_id -> DecisionShapeItem
        self.op_items = {}        # op_node_id -> OpNodeItem
        self.terminal_items = {}  # "stop"/"end" -> TerminalNodeItem
        self.edges = []
        self._building = False
        self._move_dirty = False
        self._trail = []
        self._toasts = []
        self._drag_port = None
        self._drag_line = None
        self._drag_glow = None
        self._drag_start = None
        self._drag_ghost = None
        self.setBackgroundBrush(QBrush(BG_COLOR))

    # -- display resolution (collapsed groups) ---------------------------

    def display_for(self, row_id):
        """The item standing in for a row: the outermost collapsed
        ancestor's chip, else the row's own item/frame."""
        for g in self.protocol.group_chain_of(row_id):
            if g.collapsed:
                return self.frame_items.get(g.id)
        row = self.protocol.row_by_id(row_id)
        if row is not None and row.is_group:
            return self.frame_items.get(row_id)
        return self.row_items.get(row_id)

    def _display_for_decision(self, dn):
        return self.dec_items.get(dn.id) or self.display_for(dn.step_id)

    # -- build -----------------------------------------------------------

    def rebuild(self):
        self._cancel_edge_drag()
        self.clearSelection()
        self.clear()                      # deletes all items
        self.row_items = {}
        self.frame_items = {}
        self.dec_items = {}
        self.op_items = {}
        self.terminal_items = {}
        self.edges = []
        self._trail = []
        self._toasts = []
        proto = self.protocol

        leaves = proto.leaves()
        leaf_no = {leaf.id: str(i + 1) for i, leaf in enumerate(leaves)}
        self._building = True
        try:
            def build(rows, hidden):
                for row in rows:
                    if row.is_group:
                        if not hidden:
                            frame = GroupFrameItem(self, row)
                            self.addItem(frame)
                            self.frame_items[row.id] = frame
                        build(row.children, hidden or row.collapsed)
                    elif not hidden:
                        item = StepNodeItem(self, row,
                                            leaf_no.get(row.id, "?"))
                        self.addItem(item)
                        self.row_items[row.id] = item
            build(proto.rows, False)

            for dn in proto.decision_nodes:
                spec = proto.spec_by_id(dn.decision_id)
                step = proto.row_by_id(dn.step_id)
                if (spec is None or step is None
                        or dn.step_id not in self.row_items):
                    continue    # spec gone, or step hidden in a chip
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

            self._assign_frame_members()
            self._fit_frames()
            self._place_terminals()
            self._build_edges(leaves)
        finally:
            self._building = False
        for e in self.edges:
            e.update_path()
        for item in self.dec_items.values():
            item.refresh_port_tooltips(proto)
        rect = self.itemsBoundingRect().adjusted(-150, -150, 150, 150)
        self.setSceneRect(rect)

    def _assign_frame_members(self):
        proto = self.protocol
        for gid, frame in self.frame_items.items():
            if frame.collapsed:
                frame.move_items = []
                frame.fit_items = []
                continue
            group = proto.row_by_id(gid)
            subtree_ids = {r.id for r in _subtree(group)} - {gid}
            step_ids = {r.id for r in _subtree(group)
                        if not r.is_group}
            moves, fits = [], []
            for rid in subtree_ids:
                item = self.row_items.get(rid)
                if item is not None:
                    moves.append(item)
                    fits.append(item)
                chip = self.frame_items.get(rid)
                if chip is not None and chip.collapsed:
                    moves.append(chip)
                    fits.append(chip)
                elif chip is not None:
                    fits.append(chip)   # nested frame: geometry only
            for dn in proto.decision_nodes:
                if dn.step_id in step_ids and dn.id in self.dec_items:
                    moves.append(self.dec_items[dn.id])
                    fits.append(self.dec_items[dn.id])
            for op in proto.op_nodes:
                dns = [proto.decision_node_by_id(i[0])
                       for i in op.inputs]
                owner_steps = {d.step_id for d in dns if d is not None}
                if owner_steps and owner_steps <= step_ids \
                        and op.id in self.op_items:
                    moves.append(self.op_items[op.id])
                    fits.append(self.op_items[op.id])
            frame.move_items = moves
            frame.fit_items = fits

    def _fit_frames(self):
        """Innermost frames first so outer frames wrap the inner rects."""
        frames = [(len(self.protocol.group_chain_of(gid)), f)
                  for gid, f in self.frame_items.items()]
        for _depth, frame in sorted(frames, key=lambda t: -t[0]):
            frame.fit()

    def _place_terminals(self):
        proto = self.protocol
        visible = (list(self.row_items.values())
                   + list(self.frame_items.values())
                   + list(self.dec_items.values())
                   + list(self.op_items.values()))
        if visible:
            right = max(i.sceneBoundingRect().right() for i in visible)
            top = min(i.sceneBoundingRect().top() for i in visible)
        else:
            right, top = 200, 40
        for k, kind in enumerate(("end", "stop")):
            pos = proto.terminal_pos.get(kind)
            if pos is None:
                pos = (right + 90, top + 20 + k * 56)
            item = TerminalNodeItem(self, kind, pos)
            self.addItem(item)
            self.terminal_items[kind] = item

    def _terminal_for(self, sentinel):
        if sentinel == ABORT:
            return self.terminal_items.get("stop")
        if sentinel == END:
            return self.terminal_items.get("end")
        return None

    def _build_edges(self, leaves):
        proto = self.protocol
        disp = self.display_for

        # Implicit fall-through spine between consecutive leaves.
        for a, b in zip(leaves, leaves[1:]):
            if a.next_target == NEXT:
                sa, sb = disp(a.id), disp(b.id)
                if sa is not None and sb is not None and sa is not sb:
                    self._add(EdgeItem(self, "spine", sa, sb, SPINE_COLOR,
                                       payload=("next", a.id)))
        # Explicit completion routes.
        for leaf in leaves:
            if leaf.next_target == NEXT:
                continue
            src = disp(leaf.id)
            dst = (self._terminal_for(leaf.next_target)
                   or disp(leaf.next_target))
            if src is None or dst is None or src is dst:
                continue
            port = (src.done_port if isinstance(src, StepNodeItem)
                    else None)
            self._add(EdgeItem(self, "flow", src, dst, FLOW_COLOR,
                               label="done", src_port=port,
                               payload=("flow", leaf.id)))
        # Tethers + outcome/chain edges from decision shapes.
        for dn in proto.decision_nodes:
            dec_item = self.dec_items.get(dn.id)
            src = self._display_for_decision(dn)
            if src is None:
                continue
            step_item = self.row_items.get(dn.step_id)
            if dec_item is not None and step_item is not None:
                self._add(EdgeItem(self, "tether", step_item, dec_item,
                                   TETHER_COLOR))
            spec = proto.spec_by_id(dn.decision_id)
            if spec is None:
                continue
            for outcome in spec.outcomes:
                target = dn.routes.get(outcome.id)
                if not target or target == SELF:
                    continue
                color = KIND_COLORS.get(outcome.kind,
                                        KIND_COLORS["neutral"])
                port = dec_item.ports.get(outcome.id) if dec_item else None
                kind = "outcome"
                label = dn.label_for(outcome)
                dst = self._terminal_for(target)
                if dst is None:
                    tdn = proto.decision_node_by_id(target)
                    if tdn is not None:
                        dst = self._display_for_decision(tdn)
                        kind = "chain"
                        label = f"{label} → then"
                    else:
                        dst = disp(target)
                if dst is None or dst is src:
                    continue
                self._add(EdgeItem(self, kind, src, dst, color,
                                   label=label, src_port=port,
                                   payload=("outcome", dn.id, outcome.id)))
        # Outcome → op feeds and op → target routes.
        for op in proto.op_nodes:
            op_item = self.op_items.get(op.id)
            if op_item is None:
                continue
            for dn_id, oid in op.inputs:
                dn = proto.decision_node_by_id(dn_id)
                if dn is None:
                    continue
                src = self._display_for_decision(dn)
                dec_item = self.dec_items.get(dn_id)
                spec = proto.spec_by_id(dn.decision_id)
                if src is None or spec is None or src is op_item:
                    continue
                outcome = spec.outcome_by_id(oid)
                color = KIND_COLORS.get(outcome.kind,
                                        KIND_COLORS["neutral"])
                port = dec_item.ports.get(oid) if dec_item else None
                self._add(EdgeItem(self, "feed", src, op_item, color,
                                   label=dn.label_for(outcome),
                                   src_port=port,
                                   payload=("feed", op.id, dn_id, oid)))
            if op.target is not None:
                dst = (self._terminal_for(op.target)
                       or disp(op.target))
                if dst is not None and dst is not op_item:
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
        pools = (list(self.row_items.values())
                 + list(self.dec_items.values())
                 + list(self.op_items.values())
                 + [f for f in self.frame_items.values() if f.collapsed]
                 + list(self.terminal_items.values()))
        for item in pools:
            if item in exclude:
                continue
            rects.append(item.scene_rect().adjusted(
                -EDGE_CLEARANCE, -EDGE_CLEARANCE,
                EDGE_CLEARANCE, EDGE_CLEARANCE))
        return rects

    def on_item_moved(self, item):
        if self._building:
            return
        pos = (item.scenePos().x(), item.scenePos().y())
        if isinstance(item, StepNodeItem):
            item.row.pos = pos
        elif isinstance(item, DecisionShapeItem):
            item.dnode.pos = pos
        elif isinstance(item, OpNodeItem):
            item.opnode.pos = pos
        elif isinstance(item, GroupFrameItem) and item.collapsed:
            item.row.pos = pos
        elif isinstance(item, TerminalNodeItem):
            self.protocol.terminal_pos[item.kind] = pos
        self._move_dirty = True
        self._fit_frames()
        for e in self.edges:
            e.update_path()

    # -- run-state visuals -----------------------------------------------

    _STATE_PENS = {
        "active": (ACTIVE_BORDER, 2.6),
        "deciding": (DECIDING_BORDER, 2.6),
        "recent": (RECENT_BORDER, 2.2),
    }

    def set_row_state(self, row_id, state):
        item = self.display_for(row_id)
        if item is None:
            return
        spec = self._STATE_PENS.get(state)
        item.set_state_pen(QPen(*spec) if spec else None)

    def set_decision_state(self, dn_id, on):
        item = self.dec_items.get(dn_id)
        if item is not None:
            item.set_state_pen(QPen(DECIDING_BORDER, 2.6) if on else None)

    def clear_run_states(self):
        for item in (list(self.row_items.values())
                     + list(self.frame_items.values())
                     + list(self.dec_items.values())):
            item.set_state_pen(None)
        self.clear_trail()

    # -- run trail / toasts ----------------------------------------------

    def flash_route(self, key):
        key = tuple(key)
        edge = next((e for e in self.edges if e.payload == key), None)
        if edge is None:
            return
        if edge in self._trail:
            self._trail.remove(edge)
        self._trail.insert(0, edge)
        edge.set_heat(2)
        for older in self._trail[1:]:
            older.set_heat(1)
        while len(self._trail) > 6:
            self._trail.pop().set_heat(0)

    def clear_trail(self):
        for e in self._trail:
            e.set_heat(0)
        self._trail = []

    def toast(self, target_id, text):
        item = (self.dec_items.get(target_id)
                or self.op_items.get(target_id)
                or self.display_for(target_id))
        if item is None:
            return
        t = ToastItem(text)
        self.addItem(t)
        r = item.sceneBoundingRect()
        t.setPos(r.right() + 8, r.top() - 12 - 14 * sum(
            1 for x in self._toasts if x.scene() is self))
        self._toasts.append(t)
        QTimer.singleShot(2200, lambda: self._remove_toast(t))

    def _remove_toast(self, t):
        if t in self._toasts:
            self._toasts.remove(t)
            if t.scene() is self:
                self.removeItem(t)

    def set_hover_item(self, item, on):
        """Light up the edges touching a hovered node/shape."""
        for e in self.edges:
            if e.src_item is item or e.dst_item is item:
                e.set_hover(on)

    def highlight_decision(self, dn_id, on):
        item = self.dec_items.get(dn_id)
        if item is not None:
            item.set_glow(on)
        for e in self.edges:
            if (e.payload and len(e.payload) >= 2
                    and e.payload[0] in ("outcome", "chain", "feed")
                    and e.payload[1] == dn_id):
                e.set_heat(2 if on else 0)

    # -- selection helpers -----------------------------------------------

    def selected_row_ids(self):
        """Selected rows, with rows dropped when an ancestor group is
        also selected (a rubber band over a frame grabs both — the
        frame stands for its subtree)."""
        ids = []
        for i in self.selectedItems():
            if isinstance(i, (StepNodeItem, GroupFrameItem)):
                ids.append(i.row.id)
        picked = set(ids)
        return [rid for rid in ids
                if not any(g.id in picked
                           for g in self.protocol.group_chain_of(rid))]

    # -- port dragging ---------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            for item in self.items(event.scenePos()):
                if isinstance(item, PlusButtonItem):
                    self.window.open_shape_palette(
                        item.node.row.id, event.screenPos(),
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
            # Any other press may start a node/frame move: stage an undo
            # snapshot; the release commits it only if something moved.
            self._move_dirty = False
            self.window.stage_move_undo()
        super().mousePressEvent(event)

    def _snap_target_at(self, scene_pos):
        """Nearest valid drop target. Small shapes win over frames; an
        expanded frame's interior (not covered by a child) targets the
        group."""
        port = self._drag_port
        src_owner = port.owner
        candidates = []
        pools = [self.row_items.values(),
                 [f for f in self.frame_items.values() if f.collapsed],
                 self.terminal_items.values()]
        if port.role == "outcome":
            pools.append(self.op_items.values())
            pools.append(self.dec_items.values())
        for pool in pools:
            for item in pool:
                if item is src_owner:
                    continue
                if item.snap_rect().contains(scene_pos):
                    c = item.center()
                    d2 = ((c.x() - scene_pos.x()) ** 2
                          + (c.y() - scene_pos.y()) ** 2)
                    candidates.append((d2, item))
        if candidates:
            return min(candidates, key=lambda pair: pair[0])[1]
        # Fallback: expanded frame interiors, innermost (smallest) first.
        frames = [f for f in self.frame_items.values()
                  if not f.collapsed and f is not src_owner
                  and f.scene_rect().contains(scene_pos)]
        if frames:
            return min(frames, key=lambda f: (f.rect().width()
                                              * f.rect().height()))
        return None

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
        # Snap the preview onto compact targets; for an expanded frame
        # keep the free end under the cursor (its side anchor could be
        # far away and would make the preview jump).
        snap_to = target
        if isinstance(target, GroupFrameItem) and not target.collapsed:
            snap_to = None
        _s, _e, path = route_edge_path(
            anchor, snap_to, scene_pos, rects,
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
        if self._move_dirty:
            self._move_dirty = False
            self.window.commit_move_undo()
        else:
            self.window.discard_move_undo()

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

    def mouseDoubleClickEvent(self, event):
        if not self.items(event.scenePos()):
            self.window.add_step_at(
                (event.scenePos().x(), event.scenePos().y()))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

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
        self.on_resized = None    # callback for overlay placement

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.on_resized is not None:
            self.on_resized()

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
