import json

from traits.api import observe
from traitsui.api import VGroup, View, Item
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_style.text_styles import preferences_group_style_sheet
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.preferences_UI_helpers import create_item_label_group, create_grid_group
from logger.logger_service import get_logger

logger = get_logger(__name__)

from peripheral_controller.preferences import PeripheralPreferences, z_stage_preferences_names

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

    #### 'DeviceViewerPreferencesPane' interface ################################

    # Create the single item for the default svg for the main view group.
    drop_detect_setting = create_item_label_group("_droplet_detection_capacitance_view",
                                                            label_text="Drop Detect Capacitance (pF)")

    capacitance_update_setting = create_item_label_group("_capacitance_update_interval_view",
                                                         label_text="Capacitance Update Interval (ms)" )

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