"""Standalone visual demo for DictFloatTableEditor (microdrop_utils.
traitsui_qt_helpers): a Dict(Str, Float) trait rendered as a two-column
Column | Wait Time (s) table — read-only names on the left, a float
spinbox per value on the right.

Run:
    pixi run python examples/demos/dict_float_table_editor_demo.py

Edit a spinbox and the dict prints to the console on OK, so the
write-back path is visible too.
"""

from traits.api import Dict, Float, HasTraits, Str, observe
from traitsui.api import Group, Item, View

from microdrop_utils.traitsui_qt_helpers import DictFloatTableEditor


class AckTimesDemo(HasTraits):
    ack_times = Dict(Str, Float)

    def _ack_times_default(self):
        # -1.0 is the wait-forever sentinel - rendered as the infinity text.
        return {"Routes": 5.0, "Voltage (V)": 5.0,
                "Frequency (Hz)": 5.0, "Magnet": 10.0,
                "Check Droplets": -1.0}

    view = View(
        Group(
            Item("ack_times", show_label=False,
                 editor=DictFloatTableEditor(
                     key_label="Column", value_label="Wait Time (s)",
                     low=0.0, high=120.0, decimals=1, step=0.5,
                     allow_infinity=True, infinity_value=-1.0,
                     infinity_text="∞ (wait forever)",
                 )),
            label="Column Ack Wait Times (0 = don't wait)",
            show_border=True,
        ),
        title="DictFloatTableEditor demo",
        width=420,
        buttons=["OK", "Cancel"],
        resizable=True,
    )

    @observe("ack_times")
    def _ack_times_changed(self, event):
        print("Ack times changed")
        print(event.new)


if __name__ == "__main__":
    demo = AckTimesDemo()
    demo.configure_traits()
    print(f"final ack_times: {demo.ack_times}")
