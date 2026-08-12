from traitsui.api import (
    HGroup, Item, Readonly, Spring, UItem, VGroup, View,
)

mechanisms = VGroup(
    HGroup(UItem("tray_in_button"), UItem("tray_out_button"),
           Readonly("tray_state", label="State"), label="Tray",
           show_border=True),
    HGroup(UItem("magnet_engage_button"),
           UItem("magnet_disengage_button"),
           UItem("magnet_press_button"), UItem("magnet_release_button"),
           Readonly("magnet_state", label="State"), label="Magnet",
           show_border=True),
    HGroup(Item("filter_position", label="Position"),
           Readonly("filter_state", label="State"), label="Filter",
           show_border=True),
    HGroup(UItem("lock_chip_button"), UItem("unlock_chip_button"),
           Readonly("pogo_state", label="L/R"),
           label="Chip lock (pogo pads)",
           show_border=True),
    HGroup(UItem("home_all_button"), Spring(),
           Readonly("homed_display", label="Homed")),
    label="Mechanisms",
    enabled_when="connected",
)

advanced = VGroup(
    HGroup(Item("selected_motor", label="Motor"),
           Item("move_mode", label="Mode"),
           Item("move_steps", label="Steps")),
    HGroup(UItem("move_button"), UItem("stop_button"),
           UItem("home_button")),
    Readonly("positions_display", label="Positions"),
    label="Advanced (steps)",
    show_border=True,
    enabled_when="connected",
    visible_when="show_advanced",
)

MotorsView = View(
    VGroup(
        mechanisms,
        Item("show_advanced", label="Show advanced motor controls"),
        advanced,
    ),
    resizable=True,
)
