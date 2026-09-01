# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from pyface.qt.QtCore import Qt, Signal
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
