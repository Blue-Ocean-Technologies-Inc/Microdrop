# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The preset quick-pick row: one button per list value, labeled by
format_preset; a click sets the target trait, then fires the named button.
Built offscreen."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtWidgets
from traits.api import Bool, Button, Float, HasTraits, List, observe
from traitsui.api import UItem, VGroup, View

# Microdrop utils imports.
from microdrop_utils.traitsui_qt_helpers import PresetButtonsEditor, format_preset


class _Panel(HasTraits):
    connected = Bool(True)
    distance = Float(0.0)
    go_button = Button()
    presets = List(Float, [-1.0, 0.5, 2.0])
    #: distance at each go_button press.
    went_to = List(Float)

    @observe("go_button")
    def _record_go(self, event):
        self.went_to.append(self.distance)


_VIEW = View(
    VGroup(
        UItem(
            "presets",
            editor=PresetButtonsEditor(
                target="distance", fire="go_button", unit="mm", decimals=3, signed=True
            ),
        ),
        enabled_when="connected",
    )
)


@pytest.fixture
def panel():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    panel = _Panel()
    ui = panel.edit_traits(view=_VIEW)

    yield panel, ui

    ui.dispose()


def _buttons(ui):
    return ui.control.findChildren(QtWidgets.QPushButton)


@pytest.mark.parametrize(
    "value, kwargs, label",
    [
        (128, {}, "128"),
        (37.0, {"unit": "°C", "decimals": 1}, "37 °C"),
        (37.5, {"unit": "°C", "decimals": 1}, "37.5 °C"),
        (1.0, {"unit": "mm", "decimals": 3, "signed": True}, "+1 mm"),
        (-0.1, {"unit": "mm", "decimals": 3, "signed": True}, "-0.1 mm"),
        (10.0, {"unit": "mm", "decimals": 0}, "10 mm"),
    ],
)
def test_format_preset_labels(value, kwargs, label):
    assert format_preset(value, **kwargs) == label


def test_one_labeled_button_per_value(panel):
    _panel, ui = panel

    assert [button.text() for button in _buttons(ui)] == ["-1 mm", "+0.5 mm", "+2 mm"]


def test_click_sets_the_target_then_fires(panel):
    panel, ui = panel

    _buttons(ui)[2].click()

    assert panel.distance == 2.0
    assert panel.went_to == [2.0]


def test_reassigned_list_rebuilds_the_row(panel):
    panel, ui = panel

    panel.presets = [5.0]

    assert [button.text() for button in _buttons(ui)] == ["+5 mm"]

    panel.presets = []

    assert _buttons(ui) == []


def test_buttons_follow_the_enclosing_group_enabled_state(panel):
    panel, ui = panel

    panel.connected = False

    assert not any(button.isEnabled() for button in _buttons(ui))

    panel.connected = True

    assert all(button.isEnabled() for button in _buttons(ui))
