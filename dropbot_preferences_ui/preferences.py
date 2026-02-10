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

from dropbot_controller.preferences import DropbotPreferences, preferences_names
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
    drop_detect_setting = create_item_label_group("_droplet_detection_capacitance_view",
                                                            label_text="Drop Detect Capacitance (pF)")

    capacitance_update_setting = create_item_label_group("_capacitance_update_interval_view",
                                                         label_text="Capacitance Update Interval (ms)" )


    settings = VGroup(
        capacitance_update_setting, Item("_"),

        drop_detect_setting, Item("_"),

        create_item_label_group("default_voltage", label_text="Default Voltage (V)"), Item("_"),

        create_item_label_group("default_frequency", label_text="Default Frequency (Hz)"), Item("_"),

        label="",
        show_border=True,
    ),

    view = View(

        Item("_"),  # Separator
        settings,
        Item("_"),  # Separator to space this out from further contributions to the pane.

        resizable=True
    )

    @observe("model:[droplet_detection_capacitance, capacitance_update_interval]")
    def publish_preference_change(self, event):
        logger.info(event)

        if event.new != event.old:
            msg = json.dumps({event.name: event.new})
            publish_message(msg, CHANGE_SETTINGS)
    #
    # ###########################################################################
    # # 'Handler' interface.
    # ###########################################################################
    #
    # def apply(self, info=None):
    #     """Handles the Apply button being clicked."""
    #     trait_names = preferences_names
    #     self.model.copy_traits(self._model, trait_names)