# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from pyface.qt.QtCore import QEvent, Qt, Signal
from pyface.qt.QtGui import QPainter
from pyface.qt.QtWidgets import QGraphicsView

from device_viewer.consts import AUTO_FIT_MARGIN_SCALE
from device_viewer.views.electrode_view.electrode_scene import ElectrodeScene

from logger.logger_service import get_logger

logger = get_logger(__name__)


class AutoFitGraphicsView(QGraphicsView):
    """
    A QGraphicsView with a method to fit to scene size.
    """

    display_state_signal = Signal(str)

    def __init__(self, *args, **kwargs):

        # check initial auto fit value
        self.auto_fit = kwargs.pop("auto_fit", True)
        self.auto_fit_margin_scale = kwargs.pop(
            "auto_fit_margin_scale", AUTO_FIT_MARGIN_SCALE
        )

        super().__init__(*args, **kwargs)

        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        # Repaint only the changed items' bounding rects: with
        # FullViewportUpdate, any change (a video frame, one electrode
        # toggling) re-rasterized the ENTIRE scene — every electrode path
        # and label — per update.
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)

        # Two-finger pinch zoom on touchscreens. Touch events must be
        # accepted on the viewport for the gesture framework to see them.
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)
        self._pinch_saved_interactive = None

    def resizeEvent(self, event):
        if self.auto_fit:
            self.fit_to_scene_rect()

        super().resizeEvent(event)

    def fit_to_scene_rect(self):
        if self.scene():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

        # scale down to leave margin
        self.scale(self.auto_fit_margin_scale, self.auto_fit_margin_scale)

    def keyPressEvent(self, event):

        # forward all the key press events to the interaction service if
        # interaction disabled:
        scene = self.scene()

        if not self.isInteractive():
            if isinstance(scene, ElectrodeScene):
                if hasattr(scene, "interaction_service"):
                    scene.interaction_service.handle_key_press_event(event)
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
        mouse events must not keep driving electrode/route interaction while
        pinching, so scene interactivity is suspended for the gesture."""
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

    def wheelEvent(self, event):
        # forward all the wheel events to the interaction service if
        # interaction disabled:
        scene = self.scene()

        if not self.isInteractive():
            if isinstance(scene, ElectrodeScene):
                if hasattr(scene, "interaction_service"):
                    scene.interaction_service.handle_wheel_event(event)
                    return

        super().wheelEvent(event)
