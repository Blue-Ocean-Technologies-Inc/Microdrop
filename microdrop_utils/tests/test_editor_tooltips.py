# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The custom editors apply an item's tooltip, or the trait's desc, as
TraitsUI's own editors do. Built offscreen."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtWidgets
from traits.api import Float, HasTraits, Int, List
from traitsui.api import Item, UItem, View

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import (
    DoubleSpinBoxEditor,
    PresetButtonsEditor,
    SteppedSpinEditor,
)

ITEM_TOOLTIP = "HV amplitude applied to the actuated electrodes"


class _Panel(HasTraits):
    voltage = Int(100, desc="HV amplitude setpoint (V)")
    duration = Float(1.5)
    presets = List(Float, [1.0, 2.0])


EDITORS = {
    "stepped spin": (
        "voltage",
        SteppedSpinEditor(low=30, high=200, suffix=" V"),
        QtWidgets.QSpinBox,
    ),
    "double spin": (
        "duration",
        DoubleSpinBoxEditor(low=0.0, high=60.0, decimals=2),
        QtWidgets.QDoubleSpinBox,
    ),
}


def control_of(view, control_type):
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ui = _Panel().edit_traits(view=view)
    control = ui.control.findChild(control_type)

    return ui, control


@pytest.mark.parametrize("name", list(EDITORS))
def test_item_tooltip_is_applied(name):
    trait_name, editor, control_type = EDITORS[name]
    ui, control = control_of(
        View(Item(trait_name, editor=editor, tooltip=ITEM_TOOLTIP)), control_type
    )

    assert control.toolTip() == ITEM_TOOLTIP

    ui.dispose()


def test_trait_desc_is_applied_without_an_item_tooltip():
    trait_name, editor, control_type = EDITORS["stepped spin"]
    ui, control = control_of(View(Item(trait_name, editor=editor)), control_type)

    assert control.toolTip() == "Specifies HV amplitude setpoint (V)"

    ui.dispose()


def test_preset_row_carries_the_item_tooltip():
    view = View(
        UItem(
            "presets",
            editor=PresetButtonsEditor(target="duration"),
            tooltip="Set the duration now",
        )
    )
    ui, button = control_of(view, QtWidgets.QPushButton)

    assert button.parentWidget().toolTip() == "Set the duration now"

    ui.dispose()
