"""Standalone visual demo for EnumToggleEditor (microdrop_utils.
traitsui_qt_helpers): a two-value Enum/Str trait rendered as a single
checkable button instead of a radio group. Checked maps to ``on_value``,
unchecked to ``off_value``, and each state carries its own label + accent
colour (so it reads as "which of two modes is active", not "on vs off").

Run:
    pixi run python examples/demos/enum_toggle_editor_demo.py

Click the buttons and the trait values print to the console, so the
write-back path is visible too. The plain EnumEditor radio for the same
trait is shown alongside each toggle to compare the two renderings.
"""

from traits.api import Enum, HasTraits, observe
from traitsui.api import EnumEditor, HGroup, Item, VGroup, View

from microdrop_utils.traitsui_qt_helpers import EnumToggleEditor
from microdrop_style.colors import INFO_COLOR, WARNING_COLOR


class EnumToggleDemo(HasTraits):
    # The heater-UI use case: open-loop PWM vs closed-loop Temp.
    mode = Enum("PWM", "Temp")
    # A second trait with default labels/colours and the values used as text.
    direction = Enum("Heat", "Cool")

    view = View(
        VGroup(
            HGroup(
                Item("mode", label="Mode",
                     editor=EnumToggleEditor(on_value="Temp", off_value="PWM")),
                Item("mode", label="(radio)", style="custom",
                     editor=EnumEditor(cols=2)),
            ),
            HGroup(
                # Custom labels + accent colours per state.
                Item("direction", label="Direction",
                     editor=EnumToggleEditor(
                         on_value="Heat", off_value="Cool",
                         on_label="Heating", off_label="Cooling",
                         on_color=WARNING_COLOR, off_color=INFO_COLOR,
                     )),
                Item("direction", label="(radio)", style="custom",
                     editor=EnumEditor(cols=2)),
            ),
            show_border=True,
            label="Toggle button vs radio for the same Enum trait",
        ),
        title="EnumToggleEditor demo",
        width=420,
        buttons=["OK", "Cancel"],
        resizable=True,
    )

    @observe("mode, direction")
    def _trait_changed(self, event):
        print(f"{event.name} -> {event.new}")


if __name__ == "__main__":
    demo = EnumToggleDemo()
    demo.configure_traits()
    print(f"final mode: {demo.mode}, direction: {demo.direction}")
