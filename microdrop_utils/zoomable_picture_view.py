# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A picture preview that zooms and pans the way image viewers do.

Ctrl + wheel, a pinch (touchscreen gesture, or a touchpad's native zoom or
Ctrl + wheel), ``+`` / ``-`` zoom; the wheel scrolls (Shift + wheel
sideways), a left drag and the arrow keys pan; ``0`` fits the picture to
the view, ``1`` shows its actual pixels, a double-click toggles the two.
The zoom maths is in ``picture_zoom``.

``dismiss_requested`` is emitted on Esc, and on a lone click (no drag, no
second click within the double-click interval) while the whole picture
shows, so a click still dismisses a preview nobody has zoomed."""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets

# Microdrop style imports.
from microdrop_style.colour_roles import DARK, LIGHT, TEXT, WINDOW
from microdrop_style.palette_helpers import css, is_dark, style_chip, with_alpha
from microdrop_style.typography import CHIP, role_font

# Microdrop utils imports.
from microdrop_utils.picture_zoom import (
    clamped_zoom,
    double_click_zoom,
    fit_zoom,
    is_crisp,
    is_same_zoom,
    stepped_zoom,
    zoom_percent,
)

_KEY = QtCore.Qt.Key
_TRANSFORM = QtCore.Qt.TransformationMode
_LEFT = QtCore.Qt.MouseButton.LeftButton

#: Pixels the view moves per wheel notch, and per arrow key press.
WHEEL_SCROLL_PIXELS = 60
ARROW_PAN_PIXELS = 48

#: The zoom readout: how long it stays, then fades, and its room above the
#: view's bottom edge (ms, ms, px).
READOUT_HOLD_MS = 900
READOUT_FADE_MS = 300
READOUT_MARGIN = 16

_ARROWS = {
    _KEY.Key_Left: (-1, 0),
    _KEY.Key_Right: (1, 0),
    _KEY.Key_Up: (0, -1),
    _KEY.Key_Down: (0, 1),
}
_ZOOM_KEYS = (_KEY.Key_Plus, _KEY.Key_Equal, _KEY.Key_Minus, _KEY.Key_0, _KEY.Key_1)
_OWN_KEYS = (*_ZOOM_KEYS, *_ARROWS, _KEY.Key_Escape)


class ZoomablePictureView(QtWidgets.QGraphicsView):
    """``pixmap`` at fit, zoomable from fit up to ``picture_zoom.MAX_ZOOM``
    times its actual pixels."""

    #: Esc, or a lone click while the whole picture shows.
    dismiss_requested = QtCore.Signal()

    def __init__(self, pixmap, parent=None):
        super().__init__(parent)

        self._item = QtWidgets.QGraphicsPixmapItem()
        self._zoom = 1.0
        self._at_fit = True

        # A left press not yet released, and whether it became a drag, a
        # pinch or a double-click, which never dismiss.
        self._press_position = None
        self._click_spoiled = False

        self._dismiss_timer = QtCore.QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(
            QtGui.QGuiApplication.styleHints().mouseDoubleClickInterval()
        )
        self._dismiss_timer.timeout.connect(self._dismiss_if_fit)

        self.setScene(QtWidgets.QGraphicsScene(self))
        self.scene().addItem(self._item)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)

        for policy in (
            self.setHorizontalScrollBarPolicy,
            self.setVerticalScrollBarPolicy,
        ):
            policy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.viewport().setAttribute(QtCore.Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self.viewport().grabGesture(QtCore.Qt.GestureType.PinchGesture)

        self._readout = _ZoomReadout(self)
        self.set_pixmap(pixmap)

    def set_pixmap(self, pixmap):
        """Show ``pixmap``, fitted to the view."""
        self._item.setPixmap(pixmap)
        self.scene().setSceneRect(self._item.boundingRect())
        self._zoom_to(self._fit(), announce=False)

    # ------------------------------------------------------------------ #
    # Zoom                                                               #
    # ------------------------------------------------------------------ #
    def _fit(self):
        """The zoom that shows the whole picture in the view."""
        pixmap = self._item.pixmap()
        ratio = self.devicePixelRatioF()

        return fit_zoom(
            pixmap.width(),
            pixmap.height(),
            self.viewport().width() * ratio,
            self.viewport().height() * ratio,
        )

    def _zoom_to(self, zoom, anchor=None, announce=True):
        """Show the picture at ``zoom``, the picture point under ``anchor``
        (a viewport position; its centre by default) staying under it."""

        if anchor is None:
            anchor = QtCore.QPointF(self.viewport().rect().center())

        fit = self._fit()
        anchor = anchor.toPoint()
        picture_point = self.mapToScene(anchor)

        self._zoom = clamped_zoom(zoom, fit)
        self._at_fit = is_same_zoom(self._zoom, fit)

        scale = (
            self._zoom * self._item.pixmap().devicePixelRatio()
        ) / self.devicePixelRatioF()
        self.setTransform(QtGui.QTransform.fromScale(scale, scale))

        moved = self.mapFromScene(picture_point) - anchor
        self._scroll_by(moved.x(), moved.y())

        self._item.setTransformationMode(
            _TRANSFORM.FastTransformation
            if is_crisp(self._zoom)
            else _TRANSFORM.SmoothTransformation
        )

        # Something to pan only once zoomed past fit.
        self.setDragMode(
            QtWidgets.QGraphicsView.DragMode.NoDrag
            if self._at_fit
            else QtWidgets.QGraphicsView.DragMode.ScrollHandDrag
        )

        if announce:
            self._readout.show_text(zoom_percent(self._zoom))

    def _step(self, steps, anchor=None):
        self._zoom_to(stepped_zoom(self._zoom, steps, self._fit()), anchor)

    def _scale_by(self, factor, anchor):
        """Zoom by a pinch's ``factor``; a pinch never dismisses."""
        self._click_spoiled = True
        self._zoom_to(self._zoom * factor, anchor)

    def _scroll_by(self, dx, dy):
        for bar, delta in (
            (self.horizontalScrollBar(), dx),
            (self.verticalScrollBar(), dy),
        ):
            bar.setValue(bar.value() + round(delta))

    def resizeEvent(self, event):
        # The resize anchor keeps the visible centre; at fit, it stays fit.
        super().resizeEvent(event)

        if self._at_fit or self._zoom < self._fit():
            self._zoom_to(self._fit(), announce=False)

        self._readout.place()

    # ------------------------------------------------------------------ #
    # Input                                                              #
    # ------------------------------------------------------------------ #
    def wheelEvent(self, event):
        angle = event.angleDelta()

        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            # Fractional steps: a touchpad pinch arrives as small deltas.
            if angle.y():
                self._step(angle.y() / 120, event.position())

            event.accept()

            return

        pixels = event.pixelDelta()

        if pixels.isNull():
            dx = angle.x() * WHEEL_SCROLL_PIXELS / 120
            dy = angle.y() * WHEEL_SCROLL_PIXELS / 120

        else:
            dx, dy = pixels.x(), pixels.y()

        if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier and not dx:
            dx, dy = dy, 0

        self._scroll_by(-dx, -dy)
        event.accept()

    def viewportEvent(self, event):
        kind = event.type()

        if kind == QtCore.QEvent.Type.Gesture:
            pinch = event.gesture(QtCore.Qt.GestureType.PinchGesture)

            if pinch is not None:
                centre = self.viewport().mapFromGlobal(pinch.centerPoint().toPoint())
                self._scale_by(pinch.scaleFactor(), QtCore.QPointF(centre))

                return True

        if (
            kind == QtCore.QEvent.Type.NativeGesture
            and event.gestureType() == QtCore.Qt.NativeGestureType.ZoomNativeGesture
        ):
            self._scale_by(1 + event.value(), event.position())

            return True

        return super().viewportEvent(event)

    def event(self, event):
        # The view's keys win over application shortcuts while it has focus.
        if (
            event.type() == QtCore.QEvent.Type.ShortcutOverride
            and event.key() in _OWN_KEYS
        ):
            event.accept()

            return True

        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()

        if key in (_KEY.Key_Plus, _KEY.Key_Equal):
            self._step(1)

        elif key == _KEY.Key_Minus:
            self._step(-1)

        elif key == _KEY.Key_0:
            self._zoom_to(self._fit())

        elif key == _KEY.Key_1:
            self._zoom_to(1.0)

        elif key in _ARROWS:
            dx, dy = _ARROWS[key]
            self._scroll_by(dx * ARROW_PAN_PIXELS, dy * ARROW_PAN_PIXELS)

        elif key == _KEY.Key_Escape:
            self.dismiss_requested.emit()

        else:
            super().keyPressEvent(event)

            return

        event.accept()

    def mousePressEvent(self, event):

        if event.button() == _LEFT:
            self._press_position = event.position()
            self._click_spoiled = False

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):

        if self._press_position is not None:
            moved = (event.position() - self._press_position).manhattanLength()
            self._click_spoiled |= moved >= QtWidgets.QApplication.startDragDistance()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        if event.button() != _LEFT or self._press_position is None:
            return

        self._press_position = None

        # Dismiss only once no second click follows.
        if not self._click_spoiled and self._at_fit:
            self._dismiss_timer.start()

    def mouseDoubleClickEvent(self, event):

        if event.button() != _LEFT:
            super().mouseDoubleClickEvent(event)

            return

        self._dismiss_timer.stop()
        self._press_position = event.position()
        self._click_spoiled = True
        self._zoom_to(double_click_zoom(self._zoom, self._fit()), event.position())
        event.accept()

    def _dismiss_if_fit(self):

        if self._at_fit:
            self.dismiss_requested.emit()


class _ZoomReadout(QtWidgets.QLabel):
    """A small "150 %" chip at the view's bottom centre that fades out a
    moment after it is shown."""

    def __init__(self, parent):
        super().__init__(parent)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFont(role_font(CHIP))
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self._opacity = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)

        self._fade = QtCore.QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(READOUT_FADE_MS)
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self.hide)

        self._hold = QtCore.QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(READOUT_HOLD_MS)
        self._hold.timeout.connect(self._fade.start)

        self.hide()

    def show_text(self, text):
        """Show ``text`` at full opacity, styled for the current theme."""
        theme = DARK if is_dark(self.palette()) else LIGHT
        background = with_alpha(QtGui.QColor(WINDOW[theme]), 0.88)

        style_chip(self, f"background: {css(background)}; color: {TEXT[theme]};")
        self.setText(text)

        self._fade.stop()
        self._opacity.setOpacity(1.0)
        self.place()
        self.show()
        self.raise_()
        self._hold.start()

    def place(self):
        """Bottom centre of the view."""
        view = self.parentWidget()

        self.adjustSize()
        self.move(
            (view.width() - self.width()) // 2,
            view.height() - self.height() - READOUT_MARGIN,
        )
