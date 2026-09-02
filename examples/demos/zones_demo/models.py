# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Qt-free traits model for the electrode zones demo window: just the harness
state around the shipped ``ZoneLayerManager`` (see device_viewer.models.zones),
which the embedded sidebar edits directly.
"""

from traits.api import Button, DelegatesTo, Enum, Event, HasTraits, Instance

from device_viewer.consts import ZONE_DRAW_MODE, ZONE_SELECT_MODE
from device_viewer.models.zones import ZoneLayerManager

from .consts import PAN_MODE


class ZonesDemoModel(HasTraits):
    """UI state for the demo window around the shipped zone manager."""

    #: The shipped model; the sidebar edits it directly.
    manager = Instance(ZoneLayerManager, ())

    #: Mirrors of the manager's undo/redo availability: "manager.can_undo"
    #: doesn't re-evaluate a sidebar Item's ``enabled_when`` live (nested
    #: TraitsUI paths don't track), so the demo's own undo/redo buttons bind
    #: to these top-level traits instead.
    can_undo = DelegatesTo("manager")
    can_redo = DelegatesTo("manager")

    #: Canvas tool: pan, or one of the manager's zone modes. Kept in step
    #: with ``manager.mode`` by the controller ("" <-> pan).
    mode = Enum(PAN_MODE, ZONE_DRAW_MODE, ZONE_SELECT_MODE)

    #: Fired by the canvas on Escape; the controller cancels the current
    #: interaction (pending selection first, then the region selection).
    escape_pressed = Event()

    load_svg_button = Button("Load device SVG…")
    undo_button = Button("Undo")
    redo_button = Button("Redo")
