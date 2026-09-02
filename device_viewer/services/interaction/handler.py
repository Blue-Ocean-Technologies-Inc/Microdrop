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
from pyface.qt.QtWidgets import QGraphicsView
from traits.api import HasTraits, Instance

# Microdrop package imports.
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer

# Local imports.
from ...preferences import DeviceViewerPreferences
from ..electrode_stepping_service import ElectrodeSteppingService
from .pointer_state import PointerState


class InteractionHandler(HasTraits):
    """Scene input handling for one family of device-view modes.

    The interaction service routes each scene event to the handler
    registered for ``model.mode``; what is the same in every mode (hover,
    right-click bookkeeping, zoom and rotate shortcuts, the tooltip toggle)
    stays in the service. A handler keeps only its own scratch state and
    reads the shared state through ``pointer`` and ``stepping``. Every hook
    is optional; the base does nothing.
    """

    #: Mode values this handler serves; a class constant, set by each subclass.
    modes = ()

    #: Device view Model
    model = Instance(DeviceViewMainModel)

    #: The current electrode layer view
    electrode_view_layer = Instance(ElectrodeLayer)

    #: The current device view
    device_view = Instance(QGraphicsView)

    #: The preferences for the current device view
    device_viewer_preferences = Instance(DeviceViewerPreferences)

    #: Mouse-button state shared with the service and the other handlers
    pointer = Instance(PointerState)

    #: Electrode cursor actions shared with the keyboard and the gamepad
    stepping = Instance(ElectrodeSteppingService)

    def on_enter(self, mode, previous_mode):
        """React to ``model.mode`` becoming ``mode``, one of ``modes``."""

    def on_exit(self, mode, next_mode):
        """React to ``model.mode`` leaving ``mode``, one of ``modes``."""

    def mouse_press(self, event, electrode_view):
        """Left-button press; ``electrode_view`` is the electrode under it."""

    def mouse_move(self, event, electrode_view):
        """Pointer motion; button state is in ``pointer``."""

    def mouse_release(self, event, electrode_view):
        """Left-button release; ``electrode_view`` is the electrode under it."""

    def key_press(self, event):
        """Return True when the key was consumed, else the service shortcuts run."""
        return False

    def populate_context_menu(self, menu, event):
        """Add this mode's actions to ``menu``.

        Return True to replace the default electrode actions; the tooltip
        toggle is appended by the service either way.
        """
        return False
