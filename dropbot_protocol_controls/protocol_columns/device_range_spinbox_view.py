# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Int spinbox column view bounded by the active device's range.

The column is built once and shared by every device, so its bounds are
read from app_globals on each access instead of fixed at construction:
the cell editor, the step-pattern bounds and the bulk-set dialog all read
``low`` / ``high`` and follow whichever backend last wrote the range.
"""

# Enthought library imports.
from traits.api import Int, Property, Str, Tuple

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView

app_globals = get_microdrop_redis_globals_manager()


class DeviceRangeIntSpinBoxColumnView(IntSpinBoxColumnView):
    """Int spinbox whose bounds are the ``[low, high]`` range in app_globals."""

    #: app_globals key holding the active device's ``[low, high]`` range.
    range_key = Str()

    #: Bounds used until a backend has written ``range_key``.
    fallback_range = Tuple(Int, Int)

    #: Unit shown after values in the out-of-range tooltip.
    unit = Str()

    #: Spinbox minimum, read from app_globals on every access.
    low = Property(Int)

    #: Spinbox maximum, read from app_globals on every access.
    high = Property(Int)

    def _get_low(self):
        return self._device_range()[0]

    def _get_high(self):
        return self._device_range()[1]

    def get_tooltip(self, row):
        """Flag a loaded value the active device cannot apply."""

        if isinstance(row, GroupRow):
            return None

        value = self.model.get_value(row)
        low, high = self._device_range()

        if value is None or low <= value <= high:
            return None

        return (
            f"{value} {self.unit} is outside {low}–{high} {self.unit}, "
            f"the connected device's range."
        )

    def _device_range(self):
        low, high = app_globals.get(self.range_key, self.fallback_range)

        return int(low), int(high)
