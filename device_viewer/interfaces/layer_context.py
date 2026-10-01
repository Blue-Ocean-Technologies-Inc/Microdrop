# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""What the device viewer hands every layer it attaches (#650)."""

# Enthought library imports.
from apptools.preferences.api import IPreferences
from pyface.undo.api import ICommandStack
from traits.api import HasTraits, Instance


class LayerContext(HasTraits):
    """The parts of a live device viewer pane a layer may use.

    One per pane, shared by every layer on it. Qt types are named by string
    so importing the contract never imports Qt.
    """

    #: The pane's main model (``DeviceViewMainModel``): electrodes, mode,
    #: alpha table, step state.
    model = Instance(HasTraits)

    #: The scene the electrodes are drawn in; layers add their items here.
    scene = Instance("pyface.qt.QtWidgets.QGraphicsScene")

    #: The view showing ``scene``; overlays and timers parent to it.
    device_view = Instance("pyface.qt.QtWidgets.QGraphicsView")

    #: The pane's undo history. Push self-contained commands that carry
    #: their own before/after state; the base clears it on device load.
    undo_stack = Instance(ICommandStack)

    #: The application preferences root, for a layer's own helper.
    preferences = Instance(IPreferences)

    #: The window's status bar; None until the task creates it after the
    #: pane, so a layer observes this trait rather than reading it once.
    status_bar_manager = Instance("pyface.action.api.StatusBarManager")

    #: The electrode cursor shared by arrow keys and the gamepad. Rebuilt
    #: for every device and replaced here before ``on_device_loaded``.
    stepping = Instance(HasTraits)
