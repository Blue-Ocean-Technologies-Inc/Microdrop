# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from apptools.preferences.api import PreferencesHelper
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from traits.api import Bool, Enum
from traitsui.api import Item, VGroup, View

from microdrop_utils.preferences_UI_helpers import create_item_label_group
from microdrop_utils.traitsui_qt_helpers import HoverScrollEnumEditor
from .consts import DIELECTRIC_MATERIALS

dropbot_status_and_controls_tab = PreferencesCategory(
    id="microdrop.dropbot_status_and_controls",
    name="DropBot Status & Controls",
)


class DropbotStatusAndControlsPreferences(PreferencesHelper):
    """Persisted preferences for the DropBot status-and-controls panel."""

    preferences_path = "microdrop.dropbot_status_and_controls"

    default_dielectric_material = Enum(
        *list(DIELECTRIC_MATERIALS.keys()),
        desc="Default dielectric material selected on startup",
    )

    show_dielectric_info = Bool(
        True,
        desc="Show the dielectric readout section in the status panel by default",
    )


class DropbotStatusAndControlsPreferencesPane(PreferencesPane):
    """Preferences pane contributing the DropBot Status & Controls tab."""

    model_factory = DropbotStatusAndControlsPreferences

    category = dropbot_status_and_controls_tab.id

    settings = VGroup(
        create_item_label_group(
            "default_dielectric_material",
            label_text="Default Dielectric Material",
            editor=HoverScrollEnumEditor(values=list(DIELECTRIC_MATERIALS.keys())),
            width=160,
        ),
        Item("_"),
        create_item_label_group(
            "show_dielectric_info",
            label_text="Show Dielectric Info",
        ),
        Item("_"),
        label="",
        show_border=True,
    ),

    view = View(
        Item("_"),
        settings,
        Item("_"),
        resizable=True,
    )