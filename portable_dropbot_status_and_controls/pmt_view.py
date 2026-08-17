"""The PMT pane: power and gain, plus the vendor's acquire macro
(fluorescence LED off → power on → gain → acquire). The firmware
dark-chambers the fluorescence LED during sampling on its own; the
live PMT reading shows in the status pane's Board Status group."""
from traitsui.api import HGroup, Item, Label, UItem, VGroup, View

from microdrop_utils.traitsui_qt_helpers import InPlaceToggleEditor

power_and_gain = VGroup(
    HGroup(
        UItem("pmt_power",
              style="custom",
              editor=InPlaceToggleEditor(on_label="PMT On",
                                         off_label="PMT Off")),
        Item("pmt_gain", label="Gain"),
        UItem("set_gain_button"),
    ),
    label="Power / Gain",
    show_border=True,
    enabled_when="connected",
)

acquire = VGroup(
    HGroup(
        UItem("acquire_button",
              enabled_when="connected and not acquiring"),
        Item("pmt_status_display", style="readonly", label="Result"),
    ),
    Label("Acquire runs the vendor macro: fluorescence LED off → "
          "power on → gain → sample (~10 s full buffer)."),
    label="Acquire",
    show_border=True,
    enabled_when="connected",
)

PmtView = View(
    VGroup(power_and_gain, acquire),
    resizable=True,
    scrollable=True,
)
