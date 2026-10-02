# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A graphics view that fits its scene, zooms and pans the way the device
viewer does, for any canvas that wants the same navigation."""

# Enthought library imports.
from pyface.qt.QtCore import QEvent, Qt, Signal
from pyface.qt.QtGui import QPainter
from pyface.qt.QtWidgets import QGraphicsView

#: Zoom factor per Ctrl+wheel notch or Ctrl+=/- press.
ZOOM_STEP = 1.25


class ZoomableGraphicsView(QGraphicsView):
    """Fit the scene on resize until the user takes over the framing; zoom
    with Ctrl+wheel, Ctrl+= / Ctrl+- or a two-finger pinch; Space toggles
    drag-panning.

    ``auto_fit`` and ``auto_fit_margin_scale`` (the fraction of the view the
    fitted scene fills) are keyword arguments, as is ``zoom_step``.
    """

    #: Emitted whenever the visible scene region changes — resize or either
    #: scrollbar moving — so canvas-anchored overlays know to reposition.
    viewport_changed = Signal()

    def __init__(
        self,
        *args,
        auto_fit=True,
        auto_fit_margin_scale=1.0,
        zoom_step=ZOOM_STEP,
        **kwargs,
    ):
        self.auto_fit = auto_fit
        self.auto_fit_margin_scale = auto_fit_margin_scale
        self.zoom_step = zoom_step

        super().__init__(*args, **kwargs)

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)

        # Repaint only the changed items' bounding rects: with
        # FullViewportUpdate, any change (a video frame, one electrode
        # toggling) re-rasterized the ENTIRE scene per update.
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)

        # Two-finger pinch zoom on touchscreens. Touch events must be
        # accepted on the viewport for the gesture framework to see them.
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)
        self._pinch_saved_interactive = None

        self.horizontalScrollBar().valueChanged.connect(self._emit_viewport_changed)
        self.verticalScrollBar().valueChanged.connect(self._emit_viewport_changed)

    def _emit_viewport_changed(self, _value):
        self.viewport_changed.emit()

    # ------------------------------------------------------------------ #
    # Framing                                                              #
    # ------------------------------------------------------------------ #
    def resizeEvent(self, event):
        if self.auto_fit:
            self.fit_to_scene_rect()

        super().resizeEvent(event)
        self.viewport_changed.emit()

    def fit_to_scene_rect(self):
        if self.scene():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        # scale down to leave margin
        self.scale(self.auto_fit_margin_scale, self.auto_fit_margin_scale)

    def zoom_in(self, scale=None):
        """Zoom in by ``scale`` (default ``zoom_step``); the user now owns
        the framing, so resizes stop refitting."""
        self.auto_fit = False
        scale = scale or self.zoom_step

        self.scale(scale, scale)

    def zoom_out(self, scale=None):
        """Zoom out by ``scale`` (default ``zoom_step``)."""
        scale = scale or self.zoom_step

        self.scale(1 / scale, 1 / scale)

    def set_pan_mode(self, enabled):
        """Drag to pan, with item interaction (clicks, hovers) suspended."""
        self.setInteractive(not enabled)

        if enabled:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def is_pan_mode(self):
        return self.dragMode() == QGraphicsView.DragMode.ScrollHandDrag

    # ------------------------------------------------------------------ #
    # Input                                                                #
    # ------------------------------------------------------------------ #
    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()

            else:
                self.zoom_out()

            event.accept()
            return

        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Key_Plus is the numpad's, Key_Equal the main keyboard's '+'.
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoom_in()
                return

            if event.key() == Qt.Key.Key_Minus:
                self.zoom_out()
                return

        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.set_pan_mode(not self.is_pan_mode())
            return

        super().keyPressEvent(event)

    def viewportEvent(self, event):
        if event.type() == QEvent.Type.Gesture:
            pinch = event.gesture(Qt.GestureType.PinchGesture)

            if pinch is not None:
                self._handle_pinch_gesture(pinch)
                return True

        return super().viewportEvent(event)

    def _handle_pinch_gesture(self, pinch):
        """Zoom around the fingers' midpoint. The first finger's synthesized
        mouse events must not keep driving item interaction while pinching,
        so scene interactivity is suspended for the gesture."""

        if pinch.state() == Qt.GestureState.GestureStarted:
            # The user is taking manual control of the framing.
            self.auto_fit = False
            self._pinch_saved_interactive = self.isInteractive()
            self.setInteractive(False)

        factor = pinch.scaleFactor()

        if factor != 1.0:
            # NoAnchor so the explicit scale-then-translate below is the only
            # thing repositioning the scene under the gesture's center.
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

            center = self.viewport().mapFromGlobal(pinch.centerPoint().toPoint())
            before = self.mapToScene(center)
            self.scale(factor, factor)
            delta = self.mapToScene(center) - before
            self.translate(delta.x(), delta.y())

            self.setTransformationAnchor(anchor)

        if pinch.state() in (
            Qt.GestureState.GestureFinished,
            Qt.GestureState.GestureCanceled,
        ):
            if self._pinch_saved_interactive is not None:
                self.setInteractive(self._pinch_saved_interactive)
                self._pinch_saved_interactive = None
