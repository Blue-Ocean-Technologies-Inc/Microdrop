# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from template_status_and_controls.base_controller import BaseStatusController


class ControlsController(BaseStatusController):
    """OpenDrop controls controller.

    All logic (realtime-mode toggle, message queueing, debounced setattr)
    is inherited from BaseStatusController. OpenDrop has no additional
    hardware parameters to control from the UI.
    """
