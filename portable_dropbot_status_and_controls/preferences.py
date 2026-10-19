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
pane's fan toggle drives, and which pogo contacts count as a chip."""

# Enthought library imports.
from apptools.preferences.api import PreferencesHelper
from envisage.ui.tasks.api import PreferencesCategory, PreferencesPane
from traits.api import Enum, observe
from traitsui.api import Item, VGroup, View

# Microdrop package imports.
from microdrop_application.helpers import get_microdrop_redis_globals_manager
from portable_dropbot_controller.consts import (
    CHIP_DETECT_RULES,
    DEFAULT_CHIP_DETECT_RULE,
    DEFAULT_FAN_BOARD,
    FAN_BOARDS,
    PORTABLE_DROPBOT_PREFERENCES_PATH,
)

# Microdrop utils imports.
from microdrop_utils.preferences_UI_helpers import create_item_label_group
from microdrop_utils.traitsui_qt_helpers import HoverScrollEnumEditor

# Local imports.
from .consts import CHIP_DETECT_RULE_LABELS, FAN_BOARD_LABELS

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

    view = View(
        Item("_"),
        settings,
        Item("_"),
        resizable=True,
    )
