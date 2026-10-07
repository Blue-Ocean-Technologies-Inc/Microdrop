# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The one question heavy analysis work asks before it starts during a
protocol run, shared by the ROI and AI controllers."""

# Enthought library imports.
from pyface.api import YES

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import confirm

# Local imports.
from .consts import PROTOCOL_RUNNING_CONFIRM_MESSAGE


def proceed_despite_protocol(analysis_model):
    """True unless a protocol is running and the user, asked, declines
    to start work that can stall the app and delay its captures."""
    if not analysis_model.protocol_running:
        return True

    return confirm(message=PROTOCOL_RUNNING_CONFIRM_MESSAGE) == YES
