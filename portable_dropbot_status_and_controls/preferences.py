# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Portable DropBot Settings preferences tab: which board the status
pane's fan toggle drives, which pogo contacts count as a chip, and the
preset quick-pick values for PMT gain, heater target and motor moves."""

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from traits.api import Enum, Str, observe
from traitsui.api import Item, VGroup, View

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from portable_dropbot_controller.consts import (
    CHIP_DETECT_RULES,
    DEFAULT_CHIP_DETECT_RULE,
    DEFAULT_FAN_BOARD,
    FAN_BOARDS,
    PMT_GAIN_BOUNDS,
    PORTABLE_DROPBOT_PREFERENCES_PATH,
    TEMP_TARGET_C_BOUNDS,
)

# Microdrop utils imports.
from microdrop_utils.preferences_UI_helpers import create_item_label_group
from microdrop_utils.traitsui_qt_helpers import HoverScrollEnumEditor

# Local imports.
from .consts import (
    CHIP_DETECT_RULE_LABELS,
    DEFAULT_GAIN_PRESETS,
    DEFAULT_MOVE_PRESETS,
    DEFAULT_TEMPERATURE_PRESETS,
    FAN_BOARD_LABELS,
    MOVE_DISTANCE_MM_BOUNDS,
    PRESET_SLOTS_MAX,
)

app_globals = get_microdrop_redis_globals_manager()

portable_dropbot_tab = PreferencesCategory(
    id="microdrop.portable_dropbot_settings",
    name="Portable DropBot Settings",
)


class PortableDropbotSettingsPreferences(PreferencesHelper):
    """Portable DropBot settings, on the same preferences node as the
    backend's PortableDropbotPreferences, which picks up applied changes
    through its node listener."""

    preferences_path = PORTABLE_DROPBOT_PREFERENCES_PATH

    #: Board whose fan the status pane's fan toggle drives.
    fan_board = Enum(
        DEFAULT_FAN_BOARD,
        FAN_BOARDS,
        desc="Board whose fan the status pane's fan toggle drives",
    )

    #: Which chip_on_pad contact masks count as a chip on the pad.
    chip_detect_rule = Enum(
        DEFAULT_CHIP_DETECT_RULE,
        CHIP_DETECT_RULES,
        desc="Which pogo pad contacts count as a chip on the pad",
    )

    # ---- Preset quick-pick buttons -------------------------------------
    # Free text rather than typed lists: a hand-edited value can never
    # break loading, and the panes skip whatever does not parse.

    #: PMT gains offered as buttons beside the gain fields.
    gain_presets = Str(DEFAULT_GAIN_PRESETS)

    #: Heater targets (°C) offered as buttons below the Target field.
    temperature_presets = Str(DEFAULT_TEMPERATURE_PRESETS)

    #: Relative motor moves (mm, signed) offered below Move By.
    move_presets = Str(DEFAULT_MOVE_PRESETS)

    @observe("fan_board, chip_detect_rule")
    def _publish_to_app_globals(self, event):
        """Mirror applied changes into app_globals for readers."""
        # The preferences pane edits a copy detached from the node until
        # Apply; its unapplied edits must not reach readers.
        if self.preferences is None:
            return

        app_globals[event.name] = event.new


class PortableDropbotSettingsPreferencesPane(PreferencesPane):
    """Preferences pane contributing the Portable DropBot Settings tab."""

    model_factory = PortableDropbotSettingsPreferences

    category = portable_dropbot_tab.id

    settings = VGroup(
        create_item_label_group(
            "fan_board",
            label_text="Fan toggle controls",
            editor=HoverScrollEnumEditor(
                values=list(FAN_BOARDS), format_func=FAN_BOARD_LABELS.get
            ),
            width=260,
        ),
        Item("_"),
        create_item_label_group(
            "chip_detect_rule",
            label_text="Chip detected when",
            editor=HoverScrollEnumEditor(
                values=list(CHIP_DETECT_RULES),
                format_func=CHIP_DETECT_RULE_LABELS.get,
            ),
            width=260,
        ),
        Item("_"),
        label="",
        show_border=True,
    )

    presets = VGroup(
        create_item_label_group(
            "gain_presets",
            label_text="Gain presets",
            tooltip=(
                f"Comma-separated PMT gains ({PMT_GAIN_BOUNDS[0]}–"
                f"{PMT_GAIN_BOUNDS[1]}), one button each, up to "
                f"{PRESET_SLOTS_MAX}"
            ),
            width=260,
        ),
        Item("_"),
        create_item_label_group(
            "temperature_presets",
            label_text="Temperature presets (°C)",
            tooltip=(
                f"Comma-separated heater targets ({TEMP_TARGET_C_BOUNDS[0]:g}–"
                f"{TEMP_TARGET_C_BOUNDS[1]:g} °C), one button each, up to "
                f"{PRESET_SLOTS_MAX}"
            ),
            width=260,
        ),
        Item("_"),
        create_item_label_group(
            "move_presets",
            label_text="Move presets (mm)",
            tooltip=(
                f"Comma-separated relative moves ({MOVE_DISTANCE_MM_BOUNDS[0]:g} "
                f"to {MOVE_DISTANCE_MM_BOUNDS[1]:g} mm, negative moves back), "
                f"one button each, up to {PRESET_SLOTS_MAX}"
            ),
            width=260,
        ),
        label="Presets",
        show_border=True,
    )

    view = View(
        Item("_"),
        settings,
        presets,
        Item("_"),
        resizable=True,
    )
