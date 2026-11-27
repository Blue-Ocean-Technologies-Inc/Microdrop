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

The bounds come from the column's ``DeviceRangeIntColumnModel`` on each
access, so the cell editor, the step-pattern bounds and the bulk-set dialog
all follow whichever backend last wrote the range.
"""

# Enthought library imports.
from traits.api import Int, Property, Str

# Microdrop package imports.
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView


class DeviceRangeIntSpinBoxColumnView(IntSpinBoxColumnView):
    """Int spinbox bounded by its ``DeviceRangeIntColumnModel``'s range."""

    #: Unit shown after values in the out-of-range tooltip.
    unit = Str()

    #: Spinbox minimum, read from the model's device range on every access.
    low = Property(Int)

    #: Spinbox maximum, read from the model's device range on every access.
    high = Property(Int)

    def _get_low(self):
        return self.model.device_range()[0]

    def _get_high(self):
        return self.model.device_range()[1]

    def get_tooltip(self, row):
        """Flag a loaded value the active device cannot apply."""

        if isinstance(row, GroupRow):
            return None

        value = self.model.get_value(row)
        low, high = self.model.device_range()

        if value is None or low <= value <= high:
            return None

        return (
            f"{value} {self.unit} is outside {low}–{high} {self.unit}, "
            f"the connected device's range."
        )
