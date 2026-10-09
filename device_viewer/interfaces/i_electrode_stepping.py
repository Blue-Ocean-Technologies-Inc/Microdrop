# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The electrode cursor a device viewer layer may drive (#650, #783)."""

# Enthought library imports.
from traits.api import Interface


class IElectrodeStepping(Interface):
    """Move, grow, shrink, and split the actuated electrodes by direction.

    One per loaded device, shared by the arrow keys and every layer that
    steps electrodes, so the split session and the cursor are the same
    whichever input moved them last. ``direction`` is "up", "right",
    "down" or "left"; steps only act in the edit and draw modes.
    """

    def map_direction_for_device_rotation(self, direction):
        """Return the device-frame direction for on-screen ``direction``."""

    def get_active_electrode_ids(self):
        """Return the ids of the actuated electrodes, as a set."""

    def step_active_electrodes(self, direction):
        """Move the actuated electrodes one electrode towards ``direction``."""

    def extend_active_electrodes(self, direction):
        """Also actuate the frontier electrodes towards ``direction``."""

    def shrink_active_electrodes(self, direction):
        """Release the frontier electrodes towards ``direction``."""

    def split_step(self, direction):
        """Step a split session: the first call picks the axis."""

    def reset_split_state(self):
        """End the current split session."""
