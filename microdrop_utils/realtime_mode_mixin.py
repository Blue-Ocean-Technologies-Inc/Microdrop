# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A hardware backend's realtime mode, mirrored into the app globals.

Every backend controller mixes this in, which makes the backend that applies
the mode the only writer of ``REALTIME_MODE_KEY``: a listener that starts late
reads the mode the hardware actually has.
"""

# Enthought library imports.
from traits.api import Bool, ComparisonMode, HasTraits, observe

# Microdrop package imports.
from dropbot_controller.consts import REALTIME_MODE_KEY
from microdrop_application.helpers import get_microdrop_redis_globals_manager

app_globals = get_microdrop_redis_globals_manager()


class RealtimeModeMixin(HasTraits):
    """Hold a backend's realtime mode and mirror it into REALTIME_MODE_KEY."""

    #: True while the device applies electrode actuations (HV output on).
    #: Every assignment notifies, even an unchanged value, so applying a mode
    #: rewrites the key: a value an earlier session left in a persistent Redis
    #: is overwritten when the plugin starts, and a stale one on the next apply.
    realtime_mode = Bool(False, comparison_mode=ComparisonMode.none)

    @observe("realtime_mode")
    def _write_realtime_mode_key(self, event):
        app_globals[REALTIME_MODE_KEY] = event.new
