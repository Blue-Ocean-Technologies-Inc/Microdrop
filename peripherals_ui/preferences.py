import json

from traits.api import observe, List
from traitsui.api import VGroup, View, Item
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_style.text_styles import preferences_group_style_sheet
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.preferences_UI_helpers import create_item_label_group, create_grid_group
from logger.logger_service import get_logger
from peripheral_controller.consts import UPDATE_CONFIG
from peripheral_controller.datamodels import ZStageConfigData

logger = get_logger(__name__)

from peripheral_controller.preferences import PeripheralPreferences, z_stage_preferences_names, z_stage_trait_name_mapping

peripherals_tab = PreferencesCategory(
    id="microdrop.peripheral_settings",
    name="Peripheral Settings",
    after="microdrop.dropbot_settings"
)


class PeripheralPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = PeripheralPreferences

    category = peripherals_tab.id

    _changed_preferences = List()

    # Create the grid group for the sidebar items.
    settings_grid = create_grid_group(
        z_stage_preferences_names,
        group_label="Z-Stage Config",
        group_show_border=True,
        group_style_sheet=preferences_group_style_sheet,
    )

    view = View(
        Item("_"),  # Separator
        settings_grid,
        Item("_"),  # Separator to space this out from further contributions to the pane.
        resizable=True
    )

    @observe("model:[down_height_mm, up_height_mm]")
    def _preferences_changed(self, event):
        self._changed_preferences.append(event.name)

    def apply(self, info=None):
        super().apply(info)

        if self._changed_preferences:

            # get changed data dict with correct config names and values
            updated_config_dict = {z_stage_trait_name_mapping.get(el): getattr(self.model, el) for el in self._changed_preferences}

            # round values to 2 digits past decimal
            updated_config_dict = {key: round(float(val), 2) for key, val in updated_config_dict.items()}

            # get valid json message to send using model.
            data_model = ZStageConfigData(**updated_config_dict)
            json_msg = data_model.model_dump_json(exclude_none=True)

            logger.info(f"Preferences changed for z_stage: {json_msg}. Publishing change")
            publish_message(json_msg, UPDATE_CONFIG)

        else:
            logger.debug(f"No changes made for z_stage")

        self._changed_preferences.clear()

