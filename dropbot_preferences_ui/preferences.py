import json

from traits.api import observe
from traitsui.api import VGroup, View, Item
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.preferences_UI_helpers import create_item_label_group
from logger.logger_service import get_logger

logger = get_logger(__name__)

from microdrop_style.text_styles import preferences_group_style_sheet

from dropbot_controller.preferences import DropbotPreferences
from dropbot_controller.consts import CHANGE_SETTINGS


dropbot_tab = PreferencesCategory(
    id="microdrop.dropbot_settings",
    name="Dropbot Settings",
)


class DropbotPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = DropbotPreferences

    category = dropbot_tab.id

    #### 'DeviceViewerPreferencesPane' interface ################################

    # Create the single item for the default svg for the main view group.
    drop_detect_setting = create_item_label_group("droplet_detection_capacitance",
                                                            label_text="Drop Detect Capacitance (pF)")

    capacitance_update_setting = create_item_label_group(
        "capacitance_update_interval", label_text="Capacitance Update Interval (ms)" )


    settings = VGroup(
        capacitance_update_setting, Item("_"),
        drop_detect_setting,
        label="",
        show_border=True,
    ),

    view = View(

        Item("_"),  # Separator
        settings,
        Item("_"),  # Separator to space this out from further contributions to the pane.

        resizable=True
    )

    @observe("model:*")
    def publish_preference_change(self, event):
        print(event)

        if event.new != event.old:
            msg = json.dumps({event.name: event.new})
            publish_message(msg, CHANGE_SETTINGS)
