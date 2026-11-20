# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The pre-flight section of the hub: the board checklist, the tray and pad
buttons, and Start / Cancel. Instantiable alone against a PreflightModel."""

# Enthought library imports.
from traitsui.api import HGroup, Item, UItem, VGroup, View

checklist = VGroup(
    Item("tray_text", style="readonly", resizable=True, label="Tray"),
    Item("pads_text", style="readonly", resizable=True, label="Pogo pads"),
    Item("chip_text", style="readonly", resizable=True, label="Chip on pads"),
    Item("board_text", style="readonly", resizable=True, label="Board check"),
)

mechanisms = HGroup(
    UItem("refresh_button", tooltip="Read the tray, pads and board again"),
    UItem("tray_in_button", tooltip="Pull the tray in (the pads stay put)"),
    UItem("tray_out_button", tooltip="Push the tray out (the pads stay put)"),
    UItem(
        "pads_press_button",
        tooltip="Press the pogo pads; the test board is recognised only then",
    ),
    UItem("pads_release_button", tooltip="Lift the pogo pads"),
)

decision = VGroup(
    Item(
        "chip_absent_acknowledged",
        label="Run without a detected test board",
        tooltip="Tests that need the pads pressed (voltage, shorts, channels) "
        "then have the HV refused and report no verdict unless the run's pad "
        "press makes contact",
        visible_when="board_detected is not True",
    ),
    UItem("start_hint", style="readonly", resizable=True),
    HGroup(
        UItem("start_button", enabled_when="can_start"),
        UItem("cancel_button"),
    ),
)

preflight_view = View(
    VGroup(
        UItem("tests_text", style="readonly", resizable=True),
        checklist,
        mechanisms,
        decision,
        label="Pre-flight check",
        show_border=True,
    ),
)
