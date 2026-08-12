"""The virtual mouse: a floating, mouse-shaped widget with a
crosshair pointer tip hovering above it. Dragging the body aims the
tip precisely while the finger stays below the target — the classic
assistive offset. Tapping the left/right button zones synthesizes
real clicks at the tip; dragging the wheel strip synthesizes wheel
events there. Qt-event synthesis only, so it works on every widget
inside the application (and only there)."""
import time

import shiboken6
from PySide6.QtCore import QPoint, QPointF, QEvent, QRect, Qt
from PySide6.QtGui import (
    QColor, QContextMenuEvent, QMouseEvent, QPainter, QPen, QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

from microdrop_style.colors import GREY, PRIMARY_COLOR, WHITE

from .consts import (
    MOUSE_BODY_HEIGHT_PX, MOUSE_BODY_WIDTH_PX, MOUSE_TAP_SLOP_PX,
    MOUSE_TIP_GAP_PX, MOUSE_TIP_SIZE_PX, MOUSE_WHEEL_PX_PER_NOTCH,
    MOUSE_WHEEL_WIDTH_PX,
)

#: One wheel notch in QWheelEvent angle-delta units.
_WHEEL_NOTCH = 120

#: How far down the body the button zones reach (the split-line of a
#: real mouse), as a fraction of the body height.
_BUTTON_ZONE_FRACTION = 0.45


class _PointerTip(QWidget):
    """The crosshair the mouse aims with. Transparent to mouse
    events, so QApplication.widgetAt() at its centre sees the widget
    UNDER it, never the crosshair itself."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(MOUSE_TIP_SIZE_PX, MOUSE_TIP_SIZE_PX)

    def hotspot(self):
        """Where clicks land, in global coordinates."""
        return self.geometry().center()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(PRIMARY_COLOR), 2)
        painter.setPen(pen)
        middle = self.rect().center()
        painter.drawLine(middle.x(), 0, middle.x(), self.height())
        painter.drawLine(0, middle.y(), self.width(), middle.y())
        painter.drawEllipse(middle, 4, 4)


class VirtualMouse(QWidget):
    """The draggable mouse body; owns and positions the pointer tip."""

    #: Set by the manager: called when the user closes the widget
    #: from its own ✕, so the menu checkbox can follow.
    closed_by_user = None

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(MOUSE_BODY_WIDTH_PX, MOUSE_BODY_HEIGHT_PX)
        self._tip = _PointerTip()
        self._press_pos = None      # global, at press
        self._press_zone = None
        self._start_corner = None   # widget top-left at press
        self._wheel_sent = 0        # notches already sent this drag
        self._wheel_target = None   # resolved once per wheel gesture
        self._last_click = (0.0, None)  # (time, zone) for dbl-click
        #: Widget holding a latched left press (the Hold pill), or
        #: None. While set, dragging the body streams MouseMove
        #: events to it — a click-drag in slow motion.
        self._held_target = None

    # -- lifecycle ----------------------------------------------------
    def setVisible(self, visible):
        super().setVisible(visible)
        self._tip.setVisible(visible)
        if visible:
            self._place_tip()
            self._tip.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        if not event.spontaneous() and not self.property("placed"):
            self.setProperty("placed", True)
            area = self.screen().availableGeometry()
            self.move(area.center().x() - self.width() // 2,
                      area.bottom() - self.height() - 80)
            self._place_tip()

    def closeEvent(self, event):
        self._tip.hide()
        super().closeEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._place_tip()
        self._stream_held_move()

    def _place_tip(self):
        self._tip.move(
            self.x() + (self.width() - self._tip.width()) // 2,
            self.y() - MOUSE_TIP_GAP_PX - self._tip.height())

    # -- zones ---------------------------------------------------------
    def _zone_at(self, pos):
        """'left' / 'right' / 'wheel' / 'hold' / 'close' / 'body' for
        a point in widget coordinates."""
        if self._close_rect().contains(pos):
            return "close"
        if self._hold_rect().contains(pos):
            return "hold"
        button_zone = self.height() * _BUTTON_ZONE_FRACTION
        wheel_left = (self.width() - MOUSE_WHEEL_WIDTH_PX) // 2
        if pos.y() <= button_zone:
            if wheel_left <= pos.x() <= wheel_left + MOUSE_WHEEL_WIDTH_PX:
                return "wheel"
            return "left" if pos.x() < wheel_left else "right"
        return "body"

    def _close_rect(self):
        return QRect(self.width() - 22, self.height() - 22, 18, 18)

    def _hold_rect(self):
        return QRect(4, self.height() - 24, 44, 20)

    # -- interaction ----------------------------------------------------
    def mousePressEvent(self, event):
        self._press_pos = event.globalPosition().toPoint()
        self._press_zone = self._zone_at(event.position().toPoint())
        self._start_corner = self.frameGeometry().topLeft()
        self._wheel_sent = 0
        self._wheel_target = None

    def mouseMoveEvent(self, event):
        if self._press_pos is None:
            return
        delta = event.globalPosition().toPoint() - self._press_pos
        if self._press_zone == "wheel":
            notches = -delta.y() // MOUSE_WHEEL_PX_PER_NOTCH
            if notches != self._wheel_sent:
                self._send_wheel(notches - self._wheel_sent)
                self._wheel_sent = notches
            return
        if (delta.manhattanLength() > MOUSE_TAP_SLOP_PX
                or self._press_zone == "body"):
            self.move(self._start_corner + delta)

    def mouseReleaseEvent(self, event):
        pressed, zone = self._press_pos, self._press_zone
        self._press_pos = self._press_zone = None
        if pressed is None or zone in ("wheel", "body"):
            return
        travelled = (event.globalPosition().toPoint()
                     - pressed).manhattanLength()
        if travelled > MOUSE_TAP_SLOP_PX:
            return                  # it was a drag, not a tap
        if zone == "close":
            self._release_hold()
            self.hide()
            self._tip.hide()
            if self.closed_by_user is not None:
                self.closed_by_user()
            return
        if zone == "hold":
            self._toggle_hold()
            return
        if zone == "left" and self._held_target is not None:
            # A left tap while holding IS the release click.
            self._release_hold()
            return
        self._send_click(Qt.MouseButton.LeftButton if zone == "left"
                         else Qt.MouseButton.RightButton, zone)

    # -- synthesis -------------------------------------------------------
    def _is_ours(self, widget):
        top = widget.window()
        return top is self or top is self._tip

    def _widget_under_tip(self, global_pos):
        """The application widget under the tip, or None. The direct
        probe works where the platform passes hit tests through the
        mouse-transparent tip window; where it does not, the tip is
        hidden for the one probe and restored."""
        target = QApplication.widgetAt(global_pos)
        if target is not None and not self._is_ours(target):
            return target
        self._tip.hide()
        try:
            target = QApplication.widgetAt(global_pos)
        finally:
            self._tip.show()
        if target is None or self._is_ours(target):
            return None
        return target

    def _target(self):
        """(widget, local QPointF, global QPointF) under the tip, or
        None — resolved fresh so a widget destroyed mid-gesture is
        never dereferenced."""
        global_pos = self._tip.hotspot()
        target = self._widget_under_tip(global_pos)
        if target is None:
            return None
        local = target.mapFromGlobal(global_pos)
        return target, QPointF(local), QPointF(global_pos)

    def _propagate(self, target, event_factory):
        """Send an event up the parent chain until a widget accepts
        it. Qt walks this chain itself only for SPONTANEOUS events;
        a synthesized sendEvent stops dead at the leaf (a QLabel
        inside a scroll area would swallow every wheel notch)."""
        global_pos = self._tip.hotspot()
        while target is not None:
            event = event_factory(
                QPointF(target.mapFromGlobal(global_pos)))
            QApplication.sendEvent(target, event)
            if event.isAccepted():
                return
            target = target.parentWidget()

    def _send_click(self, button, zone):
        resolved = self._target()
        if resolved is None:
            return
        target, local, global_pos = resolved
        now = time.monotonic()
        last_time, last_zone = self._last_click
        double = (zone == last_zone and (now - last_time) * 1000
                  <= QApplication.doubleClickInterval())
        self._last_click = (0.0, None) if double else (now, zone)
        # Qt only synthesizes DblClick from native events, so two
        # quick taps are promoted here instead.
        press = (QEvent.Type.MouseButtonDblClick if double
                 else QEvent.Type.MouseButtonPress)
        for event_type, buttons in ((press, button),
                                    (QEvent.Type.MouseButtonRelease,
                                     Qt.MouseButton.NoButton)):
            QApplication.sendEvent(target, QMouseEvent(
                event_type, local, local, global_pos, button, buttons,
                Qt.KeyboardModifier.NoModifier))
        if button == Qt.MouseButton.RightButton:
            # A context menu is its own event, raised by the window
            # system after a real right click — synthesized here and
            # walked up the chain to whoever offers one.
            self._propagate(target, lambda local_pos:
                            QContextMenuEvent(
                                QContextMenuEvent.Reason.Mouse,
                                local_pos.toPoint(),
                                self._tip.hotspot()))

    # -- the Hold latch -----------------------------------------------
    def _toggle_hold(self):
        if self._held_target is not None:
            self._release_hold()
            return
        resolved = self._target()
        if resolved is None:
            return
        target, local, global_pos = resolved
        QApplication.sendEvent(target, QMouseEvent(
            QEvent.Type.MouseButtonPress, local, local, global_pos,
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        self._held_target = target
        self.update()

    def _release_hold(self):
        target, self._held_target = self._held_target, None
        self.update()
        if target is None or not shiboken6.isValid(target):
            return
        global_pos = QPointF(self._tip.hotspot())
        local = QPointF(target.mapFromGlobal(self._tip.hotspot()))
        QApplication.sendEvent(target, QMouseEvent(
            QEvent.Type.MouseButtonRelease, local, local, global_pos,
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))

    def _stream_held_move(self):
        """While holding, aiming IS dragging: every body move sends a
        MouseMove (left button down) to the held widget, mapped to
        the tip — outside its bounds too, exactly as a real grab
        delivers them."""
        target = self._held_target
        if target is None:
            return
        if not shiboken6.isValid(target):
            self._held_target = None
            return
        global_pos = QPointF(self._tip.hotspot())
        local = QPointF(target.mapFromGlobal(self._tip.hotspot()))
        QApplication.sendEvent(target, QMouseEvent(
            QEvent.Type.MouseMove, local, local, global_pos,
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))

    def _send_wheel(self, notches):
        # Resolved once per gesture (the tip is not moving while the
        # strip is dragged) so the hide-probe fallback cannot flicker
        # the crosshair mid-scroll; validity re-checked per notch in
        # case the target was destroyed under us.
        if (self._wheel_target is None
                or not shiboken6.isValid(self._wheel_target)):
            resolved = self._target()
            if resolved is None:
                return
            self._wheel_target = resolved[0]
        global_pos = QPointF(self._tip.hotspot())
        self._propagate(self._wheel_target, lambda local_pos:
                        QWheelEvent(
                            local_pos, global_pos, QPoint(),
                            QPoint(0, notches * _WHEEL_NOTCH),
                            Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False))

    # -- painting ---------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        body = self.rect().adjusted(2, 2, -2, -2)
        painter.setPen(QPen(QColor(GREY["dark"]), 2))
        painter.setBrush(QColor(GREY["light"]))
        radius = body.width() // 2 - 4
        painter.drawRoundedRect(body, radius, radius // 2)
        split_y = int(self.height() * _BUTTON_ZONE_FRACTION)
        wheel_left = (self.width() - MOUSE_WHEEL_WIDTH_PX) // 2
        # The button split line and the wheel.
        painter.drawLine(body.left(), split_y, body.right(), split_y)
        painter.drawLine(wheel_left, body.top(), wheel_left, split_y)
        painter.drawLine(wheel_left + MOUSE_WHEEL_WIDTH_PX, body.top(),
                         wheel_left + MOUSE_WHEEL_WIDTH_PX, split_y)
        painter.setBrush(QColor(PRIMARY_COLOR))
        painter.drawRoundedRect(
            wheel_left + 4, body.top() + 12,
            MOUSE_WHEEL_WIDTH_PX - 8, split_y - 24, 6, 6)
        # L / R labels and the close ✕.
        painter.setPen(QPen(QColor(GREY["dark"])))
        left_zone = QRect(body.left(), body.top(), wheel_left, split_y)
        right_zone = QRect(wheel_left + MOUSE_WHEEL_WIDTH_PX,
                           body.top(),
                           body.right() - wheel_left
                           - MOUSE_WHEEL_WIDTH_PX, split_y)
        painter.drawText(left_zone, Qt.AlignCenter, "L")
        painter.drawText(right_zone, Qt.AlignCenter, "R")
        painter.drawText(self._close_rect(), Qt.AlignCenter, "✕")
        # The Hold pill: lit while a left press is latched.
        held = self._held_target is not None
        painter.setBrush(QColor(PRIMARY_COLOR) if held
                         else QColor(GREY["lighter"]))
        painter.setPen(QPen(QColor(GREY["dark"]), 1))
        painter.drawRoundedRect(self._hold_rect(), 8, 8)
        painter.setPen(QPen(QColor(WHITE if held else GREY["dark"])))
        painter.drawText(self._hold_rect(), Qt.AlignCenter, "hold")
        painter.setPen(QPen(QColor(WHITE)))
        painter.drawText(
            QRect(body.left(), split_y, body.width(),
                  body.bottom() - split_y),
            Qt.AlignCenter, "drag\nto aim")
