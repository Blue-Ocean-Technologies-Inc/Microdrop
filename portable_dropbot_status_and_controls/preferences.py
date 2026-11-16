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
pane's fan toggle drives, which pogo contacts count as a chip, how a chip
lock presses the pads, the droplet detection threshold, the magnet engage
position with its board Read / Write / Preset to flash, and the preset
quick-pick values for PMT gain, heater target and motor moves."""

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from traits.api import Button, Enum, Float, Instance, Range, Str, observe
from traitsui.api import HGroup, Item, VGroup, View

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import YES, confirm
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from portable_dropbot_controller.consts import (
    CHIP_DETECT_RULES,
    CHIP_ENGAGE_MODES,
    DEFAULT_CHIP_DETECT_RULE,
    DEFAULT_CHIP_ENGAGE_MODE,
    DEFAULT_FAN_BOARD,
    DROPLET_DETECTION_THRESHOLD_PF,
    DROPLET_DETECTION_THRESHOLD_PF_BOUNDS,
    FAN_BOARDS,
    MAGNET_ENGAGE_PRESET,
    MAGNET_ENGAGE_READ,
    PMT_GAIN_BOUNDS,
    PORTABLE_DROPBOT_PREFERENCES_PATH,
    TEMP_TARGET_C_BOUNDS,
    magnet_engage_write_publisher,
)

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.preferences_UI_helpers import create_item_label_group
from microdrop_utils.traitsui_qt_helpers import HoverScrollEnumEditor

# Local imports.
from .consts import (
    CHIP_DETECT_RULE_LABELS,
    CHIP_ENGAGE_MODE_LABELS,
    DEFAULT_GAIN_PRESETS,
    DEFAULT_MAGNET_ENGAGE_MM,
    DEFAULT_MOVE_PRESETS,
    DEFAULT_TEMPERATURE_PRESETS,
    FAN_BOARD_LABELS,
    MOVE_DISTANCE_MM_BOUNDS,
    PRESET_SLOTS_MAX,
)
from .models.magnet_engage_model import MagnetEngageModel

app_globals = get_microdrop_redis_globals_manager()

portable_dropbot_tab = PreferencesCategory(
    id="microdrop.portable_dropbot_settings",
    name="Portable DropBot Settings",
    # The second tab: right after Microdrop General, before the device viewer.
    after="microdrop.app.general_settings",
    before="microdrop.device_viewer.preferences",
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

    #: How a chip lock presses the pogo pads.
    chip_engage_mode = Enum(
        DEFAULT_CHIP_ENGAGE_MODE,
        CHIP_ENGAGE_MODES,
        desc="How a chip lock presses the pogo pads",
    )

    #: Default capacitance (pF) a channel must read for droplet detection
    #: to count it as holding liquid.
    droplet_detection_threshold_pf = Range(
        *DROPLET_DETECTION_THRESHOLD_PF_BOUNDS, value=DROPLET_DETECTION_THRESHOLD_PF
    )

    #: Magnet engage position (mm). Kept across restarts here, but reaches
    #: the board only through the tab's explicit Write / Preset to flash.
    magnet_engage_mm = Float(DEFAULT_MAGNET_ENGAGE_MM)

    # ---- Preset quick-pick buttons -------------------------------------
    # Free text rather than typed lists: a hand-edited value can never
    # break loading, and the panes skip whatever does not parse.

    #: PMT gains offered as buttons beside the gain fields.
    gain_presets = Str(DEFAULT_GAIN_PRESETS)

    #: Heater targets (°C) offered as buttons below the Target field.
    temperature_presets = Str(DEFAULT_TEMPERATURE_PRESETS)

    #: Relative motor moves (mm, signed) offered below Move By.
    move_presets = Str(DEFAULT_MOVE_PRESETS)

    @observe(
        "fan_board, chip_detect_rule, chip_engage_mode, droplet_detection_threshold_pf"
    )
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

    #: The board's magnet engage replies; the plugin passes its session-long
    #: model, and the default keeps the pane instantiable standalone.
    magnet_engage = Instance(MagnetEngageModel, ())

    read_magnet_engage = Button("Read")
    write_magnet_engage = Button("Write")
    preset_magnet_engage = Button("Preset to flash")

    @observe("read_magnet_engage")
    def _read_magnet_engage_from_board(self, event):
        self.magnet_engage.status = "Reading..."
        publish_message(topic=MAGNET_ENGAGE_READ, message="")

    @observe("write_magnet_engage")
    def _write_magnet_engage_to_ram(self, event):
        # The unapplied edit on screen is what the user means to write.
        engage_mm = self._model.magnet_engage_mm

        try:
            magnet_engage_write_publisher.publish({"engage_mm": engage_mm})
        except ValidationError:
            self.magnet_engage.status = "Engage position must be 0 mm or more"
            return

        self.magnet_engage.status = f"Writing {engage_mm:.3f} mm..."

    @observe("preset_magnet_engage")
    def _preset_magnet_engage_to_flash(self, event):
        answer = confirm(
            None,
            "Persist magnet engage height to flash now? The value now in the "
            "board's RAM (the last Write) survives reboots from then on.",
            title="Preset to Flash",
        )

        if answer != YES:
            return

        self.magnet_engage.status = "Presetting to flash..."
        publish_message(topic=MAGNET_ENGAGE_PRESET, message="")

    @observe("magnet_engage:engage_read")
    def _fill_magnet_engage_from_read(self, event):
        # Into the pane's detached copy, so a read is an unapplied edit
        # until Apply, like typing the value.
        if self._model is not None:
            self._model.magnet_engage_mm = event.new

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
        create_item_label_group(
            "chip_engage_mode",
            label_text="Chip engage mode",
            tooltip=(
                "How locking the chip presses the pogo pads. Classic presses both "
                "pads to their fixed position. Smart lowers each pad until it "
                "touches the chip, then presses a little further; it needs both "
                "pads homed. Unlocking always releases the pads, whichever mode "
                "locked them."
            ),
            editor=HoverScrollEnumEditor(
                values=list(CHIP_ENGAGE_MODES),
                format_func=CHIP_ENGAGE_MODE_LABELS.get,
            ),
            width=260,
        ),
        Item("_"),
        create_item_label_group(
            "droplet_detection_threshold_pf",
            label_text="Droplet detection threshold (pF)",
            tooltip=(
                "Capacitance a channel must read for droplet detection to count "
                "it as holding liquid. Per channel, thresholds saved in the "
                "vendor app and a fresh chip baseline replace it, and the active "
                "chip's electrode sizes scale it."
            ),
            width=260,
        ),
        Item("_"),
        label="",
        show_border=True,
    )

    magnet = VGroup(
        create_item_label_group(
            "magnet_engage_mm",
            label_text="Engage position (mm)",
            tooltip=(
                "Magnet Z engage height, written to the motor board's device "
                "defaults. Write = RAM only (lost on reboot); Preset to flash "
                "keeps it. Must not exceed the magnet-Z soft limit."
            ),
            format_str="%.3f",
            width=260,
        ),
        HGroup(
            Item("handler.read_magnet_engage", show_label=False),
            Item("handler.write_magnet_engage", show_label=False),
            Item("handler.preset_magnet_engage", show_label=False),
        ),
        Item("handler.magnet_engage.status", style="readonly", show_label=False),
        label="Magnet",
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
        magnet,
        presets,
        Item("_"),
        resizable=True,
    )
