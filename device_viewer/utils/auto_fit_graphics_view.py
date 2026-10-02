# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.qt.QtCore import Signal
from pyface.qt.QtWidgets import QGraphicsView

# Microdrop package imports.
from device_viewer.consts import AUTO_FIT_MARGIN_SCALE
from device_viewer.views.electrode_view.electrode_scene import ElectrodeScene

# Microdrop utils imports.
from microdrop_utils.zoomable_graphics_view import ZoomableGraphicsView


class AutoFitGraphicsView(ZoomableGraphicsView):
    """The device view: the shared zoom/pan/fit view, with its key and wheel
    bindings owned by the electrode interaction service instead — it zooms
    by the preferences' sensitivity, toggles pan through the model's mode
    and repositions the zone overlays."""

    display_state_signal = Signal(str)

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_fit_margin_scale", AUTO_FIT_MARGIN_SCALE / 100)

        super().__init__(*args, **kwargs)

    def _interaction_service(self):
        """The scene's interaction service, while item interaction is off
        (panning) and the scene is an ElectrodeScene; None otherwise."""
        scene = self.scene()

        if self.isInteractive() or not isinstance(scene, ElectrodeScene):
            return None

        return getattr(scene, "interaction_service", None)

    def keyPressEvent(self, event):
        service = self._interaction_service()

        if service is not None:
            service.handle_key_press_event(event)
            return

        # The scene's interaction service handles the keys when interactive.
        QGraphicsView.keyPressEvent(self, event)

    def wheelEvent(self, event):
        service = self._interaction_service()

        if service is not None:
            service.handle_wheel_event(event)
            return

        QGraphicsView.wheelEvent(self, event)
