# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Demo: Pictogrammers Material Design Icons (MDI) in a TraitsUI app.

Exercises the MDI webfont (``microdrop_style/icons/Material_Design_Icons``)
loaded by ``style_app`` alongside the Material Symbols font, through the
production ``IconButtonEditor`` / ``IconToggleEditor`` with their
``font_family`` option pointed at ``MDI_ICON_FONT_FAMILY``.

Unlike Material Symbols, the MDI font has NO ligatures — glyphs are the
``\\U000Fxxxx`` codepoints listed on each icon's page at
https://pictogrammers.com/library/mdi/ (also in the webfont repo's CSS).

Run:
    pixi run python examples/demos/mdi_icon_buttons_demo.py
"""

import sys

from PySide6.QtWidgets import QApplication
from traits.api import Bool, Button, HasTraits, Str, observe
from traitsui.api import HGroup, Item, UItem, View

from microdrop_style.fonts.fontnames import MDI_ICON_FONT_FAMILY
from microdrop_style.helpers import style_app
from microdrop_utils.traitsui_qt_helpers import IconButtonEditor, IconToggleEditor

# MDI codepoints (from the pictogrammers.com icon pages) — glyphs Material
# Symbols has no equivalent for.
MDI_ICON_FLASK_OUTLINE = "\U000f0096"  # flask-outline
MDI_ICON_TEST_TUBE = "\U000f0668"  # test-tube
MDI_ICON_BEAKER_OUTLINE = "\U000f0690"  # beaker-outline
MDI_ICON_EYEDROPPER = "\U000f020a"  # eyedropper
MDI_ICON_MICROSCOPE = "\U000f0654"  # microscope
MDI_ICON_MOLECULE = "\U000f0bac"  # molecule
MDI_ICON_CHIP = "\U000f061a"  # chip
MDI_ICON_PIPE_VALVE = "\U000f184d"  # pipe-valve
MDI_ICON_WATER = "\U000f058c"  # water (droplet)
MDI_ICON_WATER_OFF = "\U000f058d"  # water-off
MDI_ICON_MAGNET = "\U000f0347"  # magnet
MDI_ICON_MAGNET_ON = "\U000f0348"  # magnet-on


class MdiIconButtonsDemoModel(HasTraits):
    """Fire-and-forget buttons plus two glyph toggles, all MDI glyphs."""

    flask_button = Button()
    test_tube_button = Button()
    beaker_button = Button()
    eyedropper_button = Button()
    microscope_button = Button()
    molecule_button = Button()
    chip_button = Button()
    pipe_valve_button = Button()

    droplet_present = Bool(True)
    magnet_engaged = Bool(False)

    last_action = Str("click an icon...")

    @observe(
        "flask_button, test_tube_button, beaker_button, "
        "eyedropper_button, microscope_button, molecule_button, "
        "chip_button, pipe_valve_button"
    )
    def _on_icon_button_fired(self, event):
        self.last_action = f"{event.name} clicked"
        print(f"[demo] {self.last_action}")

    @observe("droplet_present, magnet_engaged")
    def _on_toggle_changed(self, event):
        self.last_action = f"{event.name} -> {event.new}"
        print(f"[demo] {self.last_action}")


mdi_icon_buttons_demo_view = View(
    HGroup(
        UItem(
            "flask_button",
            editor=IconButtonEditor(
                glyph=MDI_ICON_FLASK_OUTLINE,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="flask-outline",
            ),
        ),
        UItem(
            "test_tube_button",
            editor=IconButtonEditor(
                glyph=MDI_ICON_TEST_TUBE,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="test-tube",
            ),
        ),
        UItem(
            "beaker_button",
            editor=IconButtonEditor(
                glyph=MDI_ICON_BEAKER_OUTLINE,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="beaker-outline",
            ),
        ),
        UItem(
            "eyedropper_button",
            editor=IconButtonEditor(
                glyph=MDI_ICON_EYEDROPPER,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="eyedropper",
            ),
        ),
        UItem(
            "microscope_button",
            editor=IconButtonEditor(
                glyph=MDI_ICON_MICROSCOPE,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="microscope",
            ),
        ),
        UItem(
            "molecule_button",
            editor=IconButtonEditor(
                glyph=MDI_ICON_MOLECULE,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="molecule",
            ),
        ),
        UItem(
            "chip_button",
            editor=IconButtonEditor(
                glyph=MDI_ICON_CHIP, font_family=MDI_ICON_FONT_FAMILY, tooltip="chip"
            ),
        ),
        UItem(
            "pipe_valve_button",
            editor=IconButtonEditor(
                glyph=MDI_ICON_PIPE_VALVE,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="pipe-valve",
            ),
        ),
        label="MDI icon buttons",
        show_border=True,
    ),
    HGroup(
        UItem(
            "droplet_present",
            editor=IconToggleEditor(
                on_glyph=MDI_ICON_WATER,
                off_glyph=MDI_ICON_WATER_OFF,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="droplet present",
            ),
        ),
        UItem(
            "magnet_engaged",
            editor=IconToggleEditor(
                on_glyph=MDI_ICON_MAGNET_ON,
                off_glyph=MDI_ICON_MAGNET,
                font_family=MDI_ICON_FONT_FAMILY,
                tooltip="magnet engaged",
            ),
        ),
        label="MDI glyph toggles",
        show_border=True,
    ),
    Item("last_action", style="readonly", show_label=False),
    title="Pictogrammers MDI icons demo",
    resizable=True,
)


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    style_app(app)  # loads Material Symbols AND the MDI webfont

    MdiIconButtonsDemoModel().configure_traits(view=mdi_icon_buttons_demo_view)
