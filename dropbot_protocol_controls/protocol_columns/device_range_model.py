# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Int column model bounded by the active device's range.

The column is built once and shared by every device, so the range is read
from app_globals on each use instead of fixed at construction: it follows
whichever backend last wrote it.
"""

# Enthought library imports.
from traits.api import DefaultValue, Int, Str, Tuple

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from pluggable_protocol_tree.models.column import BaseColumnModel

app_globals = get_microdrop_redis_globals_manager()


class DeviceRangeIntColumnModel(BaseColumnModel):
    """Int setpoint whose bounds are the ``[low, high]`` range in app_globals."""

    #: app_globals key holding the active device's ``[low, high]`` range.
    range_key = Str()

    #: Range used until a backend has written ``range_key``.
    fallback_range = Tuple(Int, Int)

    def device_range(self):
        """Return the active device's ``(low, high)``."""
        low, high = app_globals.get(self.range_key, self.fallback_range)

        return int(low), int(high)

    def trait_for_row(self):
        """Return an Int whose default is ``default_value`` in the device range.

        The default is computed when a row first reads it, so a new step
        follows the device connected now rather than the one connected when
        the protocol was opened; a row loaded from a file gets its stored
        value instead.
        """
        trait = Int(desc=self.col_name)
        trait.default_value_type = DefaultValue.callable_and_args
        trait.default_value = (self._default_in_device_range, (), None)

        return trait

    def _default_in_device_range(self):
        low, high = self.device_range()

        return min(max(int(self.default_value), low), high)
