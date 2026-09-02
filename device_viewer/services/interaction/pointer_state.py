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
from traits.api import Bool, HasTraits, Str


class PointerState(HasTraits):
    """Mouse-button state and the electrode the pointer last touched.

    One instance per loaded device, shared by the interaction service, the
    mode handlers, and the stepping service, so every input agrees on which
    buttons are down and where the electrode cursor is.
    """

    #: Left button is down.
    left_pressed = Bool(False)

    #: Right button is down.
    right_pressed = Bool(False)

    #: More than one electrode was visited while the left button was down.
    is_drag = Bool(False)

    #: The electrode last clicked or dragged over; a keyboard or gamepad step
    #: moves from here when nothing is actuated.
    last_electrode_id_visited = Str(allow_none=True)
