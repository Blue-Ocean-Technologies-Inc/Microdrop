"""The motor panel laid out like the original portable pane:
Select Motor / Macros / Manual Move, with macro buttons that
relabel (and hide) as the target motor changes."""
from traitsui.api import (
    ButtonEditor, HGroup, Item, UItem, VGroup, View,
)

from microdrop_utils.traitsui_qt_helpers import DoubleSpinBoxEditor

from ..consts import MOVE_DISTANCE_MM_BOUNDS

#: Touch-friendly mm spin box (the vendor UI's 3-decimal distance
#: spin), stepping a whole mm per tap.
_mm_spin_box = DoubleSpinBoxEditor(
    low=MOVE_DISTANCE_MM_BOUNDS[0], high=MOVE_DISTANCE_MM_BOUNDS[1],
    decimals=3, step=1.0,
)

select_motor = VGroup(
    Item("selected_motor", label="Target Motor"),
    label="Select Motor",
    show_border=True,
    enabled_when="connected",
)

#: The firmware only moves the magnet while a chip sits on the pad
#: (chip_on_pad), so the magnet macros grey out without one instead
#: of silently doing nothing.
_MAGNET_NEEDS_CHIP = "selected_motor != 'magnet' or chip_inserted"

macros = VGroup(
    HGroup(
        UItem("macro_button_1",
              editor=ButtonEditor(label_value="macro_button_1_label"),
              visible_when="macro_button_1_label",
              enabled_when=_MAGNET_NEEDS_CHIP),
        UItem("macro_button_2",
              editor=ButtonEditor(label_value="macro_button_2_label"),
              visible_when="macro_button_2_label",
              enabled_when=_MAGNET_NEEDS_CHIP),
        UItem("home_button"),
        UItem("home_all_button"),
    ),
    label="Macros",
    show_border=True,
    enabled_when="connected",
)

manual_move = VGroup(
    HGroup(Item("move_by_mm", label="Move By (mm)",
                editor=_mm_spin_box),
           UItem("move_by_button")),
    HGroup(Item("move_to_mm", label="Move To (mm)",
                editor=_mm_spin_box),
           UItem("move_to_button")),
    HGroup(Item("speed_um_per_s", label="Speed (μm/s)"),
           UItem("set_speed_button")),
    label="Manual Move",
    show_border=True,
    enabled_when="connected",
)

MotorsView = View(
    VGroup(select_motor, macros, manual_move),
    resizable=True,
)
