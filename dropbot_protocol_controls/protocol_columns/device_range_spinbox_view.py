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
all follow whichever backend last wrote the range. A loaded value outside
the range is flagged in the tooltip and survives an unedited commit.
"""

# Enthought library imports.
from traits.api import Int, Property, Str

# Microdrop package imports.
from pluggable_protocol_tree.models.row import GroupRow
from pluggable_protocol_tree.views.columns.spinbox import IntSpinBoxColumnView

#: Qt dynamic property holding a clamped value the user has not edited yet.
_UNEDITED_VALUE_PROPERTY = "unedited_out_of_range_value"


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

    def create_editor(self, parent, context):
        """Return the spinbox, forgetting its loaded value once edited.

        Typing counts as an edit even when it leaves the value unchanged:
        typing the bound a loaded value was clamped to fires no
        ``valueChanged``, yet the user means that bound.
        """
        editor = super().create_editor(parent, context)

        def forget_unedited_value():
            editor.setProperty(_UNEDITED_VALUE_PROPERTY, None)

        editor.valueChanged.connect(forget_unedited_value)
        editor.lineEdit().textEdited.connect(forget_unedited_value)

        return editor

    def set_editor_data(self, editor, value):
        """Load ``value``, keeping it for an unedited commit if out of range.

        QSpinBox clamps a value outside the device range to the nearer
        bound, so opening the cell and committing without typing would
        silently rewrite a loaded value to that bound.
        """
        super().set_editor_data(editor, value)

        clamped = value is not None and editor.value() != int(value)
        editor.setProperty(_UNEDITED_VALUE_PROPERTY, value if clamped else None)

    def get_editor_data(self, editor):
        """Return the loaded value if the user never changed the spinbox."""
        unedited_value = editor.property(_UNEDITED_VALUE_PROPERTY)

        if unedited_value is not None:
            return unedited_value

        return super().get_editor_data(editor)

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
