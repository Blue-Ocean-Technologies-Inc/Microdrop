# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The input behaviour behind the modes a layer adds (#650)."""

# Enthought library imports.
from traits.api import Interface


class IInteractionHandler(Interface):
    """Behaviour for the modes a layer contributes.

    The base calls it when ``model.mode`` enters or leaves one of the owning
    layer's modes, so a layer sets up and clears its gesture state there
    instead of in the base's mode-change code. Pointer and key dispatch join
    this interface with the first layer that draws (zones), as an additive
    contract change.
    """

    def on_enter(self, mode, previous_mode):
        """Start ``mode``; ``previous_mode`` is the mode being left."""

    def on_exit(self, mode, next_mode):
        """Leave ``mode`` for ``next_mode``: drop gesture state, overlays."""
