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

        QApplication.styleHints().colorSchemeChanged.connect(
            self._on_color_scheme_changed,
        )

    # --- push API (driven by the dock-pane controller) ---------------

    def rebuild(self, step_labels):
        self._step_labels = list(step_labels)
        self.step_count = len(self._step_labels)
        self.update()

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
            self._seek_at_point(self._event_point(event))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Scrub: while the left button is held, keep emitting as the pointer
        # crosses ticks. Qt coalesces move events, so this is not per-pixel.
        if event.buttons() & Qt.LeftButton:
            self._seek_at_point(self._event_point(event))
        super().mouseMoveEvent(event)

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

    def _paint_track(self, painter, rect, count, position, colors):
        # Video-timeline look: a track bar divided into one cell per item by
        # thin separators, with the current item drawn as a filled, outlined
        # box (the "you are here" cell) rather than a single tick.
        seg = self._usable_width() / max(1, count)
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
                          self.step_count, self._step_index, colors)
        if self._phase_track_visible():
            self._paint_track(painter, self._phase_track_rect(),
                              self._phase_total, self._phase_index, colors)
        painter.end()
