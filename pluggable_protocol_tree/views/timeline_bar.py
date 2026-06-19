"""TimelineBar — a video-style seek strip for the pluggable protocol tree.

Pure view: it paints a step track (one cell per navigable step) with the
current step highlighted, and — only while a protocol is running and the
current step has more than one phase — a secondary phase track beneath
it. Clicking either track emits an intent
signal; the dock-pane controller translates that into a status-controller
seek. The widget holds no engine references and never seeks itself.

Mirrors NavigationBar's conventions: hugs its height (Expanding/Fixed),
re-applies theme colours on colorSchemeChanged (deferred one event-loop
tick, since is_dark_mode() can be briefly stale at signal time).
"""

from pyface.qt.QtCore import Qt, QRect, QTimer, Signal
from pyface.qt.QtGui import QColor, QPainter, QPen
from pyface.qt.QtWidgets import QApplication, QSizePolicy, QWidget

from microdrop_style.colors import GREY, SECONDARY_SHADE
from microdrop_style.helpers import is_dark_mode

# Layout geometry (px). The widget is a fixed-height strip; the step track
# sits on top, the phase track (shown only for multi-phase current steps)
# directly below it.
SIDE_MARGIN = 8
BAR_HEIGHT = 34
STEP_TRACK_TOP = 6
STEP_TRACK_BOTTOM = 18
PHASE_TRACK_TOP = 21
PHASE_TRACK_BOTTOM = 29

# Translucent categorical tints used to band steps by their containing group,
# so grouped steps are identifiable at a glance. Cycled in group order; steps
# not in any group get no tint.
GROUP_PALETTE = ("#4F9DDE", "#E0A23B", "#5FBF77", "#C56BD6", "#E06C75", "#46B5A8")
GROUP_TINT_ALPHA = 60


class TimelineBar(QWidget):
    step_seek_requested = Signal(int)
    phase_seek_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(BAR_HEIGHT)
        self.setMouseTracking(True)

        self.step_count = 0
        self._step_labels = []
        self._step_index = -1
        self._phase_index = 0
        self._phase_total = 0
        self._running = False
        self._cell_colors = []

        # Relative-drag state: a press anchors at the current playhead, and a
        # drag moves it by the number of cells the pointer travels -- so
        # dragging left/right nudges the position rather than jumping to the
        # cell under the cursor. A press with no drag is a plain click (jump).
        self._drag_track = None
        self._drag_press_x = 0
        self._drag_anchor_index = 0
        self._drag_moved = False
        self._drag_last_target = None

        QApplication.styleHints().colorSchemeChanged.connect(
            self._on_color_scheme_changed,
        )

    # --- push API (driven by the dock-pane controller) ---------------

    def rebuild(self, step_labels, group_keys=None):
        self._step_labels = list(step_labels)
        self.step_count = len(self._step_labels)
        self._cell_colors = self._compute_cell_colors(group_keys)
        self.update()

    def _compute_cell_colors(self, group_keys):
        """Map each step to a group tint colour (or None). Distinct group keys
        get successive palette colours in order of first appearance; steps with
        a None key (not in a group) get no tint."""
        if not group_keys:
            return [None] * self.step_count
        order = {}
        out = []
        for key in group_keys:
            if key is None:
                out.append(None)
                continue
            if key not in order:
                order[key] = len(order)
            out.append(GROUP_PALETTE[order[key] % len(GROUP_PALETTE)])
        return out

    def set_position(self, step_index, step_total, phase_index, phase_total):
        # step_total is accepted for API symmetry with the status bar, but the
        # tick count comes from rebuild()'s label list; trust step_count.
        self._step_index = step_index
        self._phase_index = phase_index
        self._phase_total = phase_total
        self.setToolTip(self._current_label())
        self.update()

    def set_running(self, running):
        self._running = bool(running)
        self.update()

    # --- geometry / hit testing --------------------------------------

    def _usable_width(self):
        return max(1, self.width() - 2 * SIDE_MARGIN)

    def _step_track_rect(self):
        return QRect(SIDE_MARGIN, STEP_TRACK_TOP,
                     self._usable_width(), STEP_TRACK_BOTTOM - STEP_TRACK_TOP)

    def _phase_track_rect(self):
        return QRect(SIDE_MARGIN, PHASE_TRACK_TOP,
                     self._usable_width(), PHASE_TRACK_BOTTOM - PHASE_TRACK_TOP)

    def _phase_track_visible(self):
        # Phase scrubbing only makes sense during a run (incl. paused); when
        # idle the phase track is hidden even on a multi-phase step.
        return self._running and self._phase_total > 1

    def _index_at_x(self, x, count):
        if count <= 0:
            return 0
        seg = self._usable_width() / count
        idx = int((x - SIDE_MARGIN) / seg)
        return max(0, min(count - 1, idx))

    def _step_index_at_x(self, x):
        return self._index_at_x(x, self.step_count)

    def _phase_index_at_x(self, x):
        return self._index_at_x(x, self._phase_total)

    def _seek_at_point(self, point):
        if self._phase_track_visible() and self._phase_track_rect().contains(point):
            self.phase_seek_requested.emit(self._phase_index_at_x(point.x()))
        elif self._step_track_rect().contains(point):
            self.step_seek_requested.emit(self._step_index_at_x(point.x()))

    # --- mouse ------------------------------------------------------

    def _event_point(self, event):
        # PySide6: QMouseEvent.position() returns QPointF; older shims use pos().
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._begin_drag(self._event_point(event))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and self._drag_track is not None:
            self._drag_update(self._event_point(event))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_track is not None:
            if not self._drag_moved:
                # A press with no drag is a plain click: jump to that cell.
                self._seek_at_point(self._event_point(event))
            self._drag_track = None
        super().mouseReleaseEvent(event)

    def _begin_drag(self, point):
        # Anchor at the *current* playhead so a drag nudges from where the
        # position is, not from where the cursor landed.
        if self._phase_track_visible() and self._phase_track_rect().contains(point):
            self._drag_track = "phase"
            self._drag_anchor_index = self._phase_index
        elif self._step_track_rect().contains(point):
            self._drag_track = "step"
            self._drag_anchor_index = self._step_index
        else:
            self._drag_track = None
            return
        self._drag_press_x = point.x()
        self._drag_moved = False
        self._drag_last_target = None

    def _drag_update(self, point):
        count = self._phase_total if self._drag_track == "phase" else self.step_count
        if count <= 0:
            return
        seg = self._usable_width() / count
        delta = int(round((point.x() - self._drag_press_x) / seg))
        if delta != 0:
            self._drag_moved = True
        anchor = self._drag_anchor_index if self._drag_anchor_index >= 0 else 0
        target = max(0, min(count - 1, anchor + delta))
        if target == self._drag_last_target:
            return
        self._drag_last_target = target
        if self._drag_track == "phase":
            self.phase_seek_requested.emit(target)
        else:
            self.step_seek_requested.emit(target)

    # --- labels / theme ---------------------------------------------

    def _current_label(self):
        if 0 <= self._step_index < len(self._step_labels):
            return self._step_labels[self._step_index]
        return ""

    def _on_color_scheme_changed(self, *_):
        QTimer.singleShot(0, self.update)

    def _colors(self):
        if is_dark_mode():
            return dict(track=GREY["dark"], tick=GREY["lighter"],
                        head=SECONDARY_SHADE[300], running_head=SECONDARY_SHADE[100])
        return dict(track=GREY["light"], tick=GREY["dark"],
                    head=SECONDARY_SHADE[700], running_head=SECONDARY_SHADE[900])

    # --- paint ------------------------------------------------------

    def _paint_track(self, painter, rect, count, position, colors, cell_colors=None):
        # Video-timeline look: a track bar divided into one cell per item by
        # thin separators, with the current item drawn as a filled, outlined
        # box (the "you are here" cell) rather than a single tick.
        seg = self._usable_width() / max(1, count)
        # Group tint bands (step track only): shade each cell by its group so
        # grouped steps are identifiable at a glance.
        if cell_colors:
            for i in range(count):
                hexc = cell_colors[i] if i < len(cell_colors) else None
                if hexc is None:
                    continue
                left = int(SIDE_MARGIN + i * seg)
                right = int(SIDE_MARGIN + (i + 1) * seg)
                tint = QColor(hexc)
                tint.setAlpha(GROUP_TINT_ALPHA)
                painter.fillRect(
                    QRect(left, rect.top(), max(1, right - left), rect.height()),
                    tint)
        painter.setPen(QPen(QColor(colors["track"]), 2))
        mid_y = rect.center().y()
        painter.drawLine(rect.left(), mid_y, rect.right(), mid_y)
        painter.setPen(QPen(QColor(colors["tick"]), 1))
        for i in range(count + 1):
            x = int(SIDE_MARGIN + i * seg)
            painter.drawLine(x, rect.top(), x, rect.bottom())
        if 0 <= position < count:
            left = int(SIDE_MARGIN + position * seg)
            right = int(SIDE_MARGIN + (position + 1) * seg)
            head_color = colors["running_head"] if self._running else colors["head"]
            fill = QColor(head_color)
            fill.setAlpha(90)
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(head_color), 2))
            painter.drawRoundedRect(
                QRect(left, rect.top(), max(1, right - left), rect.height()), 3, 3)
            painter.setBrush(Qt.NoBrush)

    def paintEvent(self, event):
        if self.step_count <= 0:
            return
        colors = self._colors()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_track(painter, self._step_track_rect(),
                          self.step_count, self._step_index, colors,
                          cell_colors=self._cell_colors)
        if self._phase_track_visible():
            self._paint_track(painter, self._phase_track_rect(),
                              self._phase_total, self._phase_index, colors)
        painter.end()
