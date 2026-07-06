"""Standalone visual demo for the Toggle-switch editors in
microdrop_utils.traitsui_qt_helpers: a two-value Enum/Str trait rendered as a
sliding switch instead of a radio group. Checked maps to ``on_value``,
unchecked to ``off_value``.

Two widgets are shown:
  * SlidingToggleEditor   - the static Toggle switch (sliding handle, no animation).
  * AnimatedToggleEditor  - the AnimatedToggle switch (animated handle + pulse
                            halo on switch). Accepts checked_color and
                            pulse_checked_color.

Run:
    pixi run python examples/demos/enum_toggle_editor_demo.py

Click the switches and the trait values print to the console, so the
write-back path is visible too. The same trait is bound to both switches,
so flipping one updates the other.
"""

from traits.api import Enum, HasTraits, observe
from traitsui.api import HGroup, Item, VGroup, View

from microdrop_utils.traitsui_qt_helpers import SlidingToggleEditor, AnimatedToggleEditor
from microdrop_style.colors import WARNING_COLOR


class EnumToggleDemo(HasTraits):
    # The heater-UI use case: open-loop PWM vs closed-loop Temp.
    mode = Enum("PWM", "Temp")
    # A second trait, switched with custom checked + pulse-halo colours.
    direction = Enum("Cool", "Heat")

    view = View(
        VGroup(
            # The same `mode` trait bound to both switches (default colours);
            # flipping either updates the other.
            HGroup(
                Item("mode", label="Toggle",
                     editor=SlidingToggleEditor(on_value="Temp", off_value="PWM")),
                Item("mode", label="Animated",
                     editor=AnimatedToggleEditor(on_value="Temp",
                                                 off_value="PWM")),
            ),
            # AnimatedToggle with custom accent + pulse-halo colours.
            HGroup(
                Item("direction", label="Direction",
                     editor=AnimatedToggleEditor(
                         on_value="Heat", off_value="Cool",
                         checked_color=WARNING_COLOR,
                         pulse_checked_color="#44F5A623",
                     )),
            ),
            show_border=True,
            label="Toggle vs AnimatedToggle switch for an Enum trait",
        ),
        title="Toggle editors demo",
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
