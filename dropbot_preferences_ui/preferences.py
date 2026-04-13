import json

from traitsui.item import Spring

from microdrop_style.text_styles import preferences_group_style_sheet

from protocol_grid.preferences import protocol_grid_tab
from traits.api import observe
from traitsui.api import VGroup, HGroup, View, Item
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.preferences_UI_helpers import create_item_label_group, create_grid_group
from dropbot_controller.preferences import DropbotPreferences
from dropbot_controller.consts import CHANGE_SETTINGS

from .consts import (
    VOLTAGE_FREQUENCY_RANGE_CHANGED,
)

from logger.logger_service import get_logger
from .models import VoltageFrequencyRangePreferences

logger = get_logger(__name__)

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

    #### View definition ################################

    # Create the single item for the default svg for the main view group.
    drop_detect_setting = create_item_label_group("droplet_detection_capacitance_view",
                                                            label_text="Drop Detect Capacitance (pF)")

    capacitance_update_setting = create_item_label_group("capacitance_update_interval_view",
                                                         label_text="Capacitance Update Interval (ms)" )


    settings = VGroup(
        capacitance_update_setting, Item("_"),

        drop_detect_setting, Item("_"),

        label="",
        show_border=True,
    ),

    # Readonly hardware limits reported by the connected DropBot
    hardware_config = HGroup(
        VGroup(
        Item("_hardware_max_voltage_view", label="Max Voltage (V)", style="readonly"),
            Item("_hardware_max_frequency_view", label="Max Frequency (Hz)", style="readonly"),
        ),
        Item("12"), # spacer
        VGroup(
            Item("last_voltage", label="Last Applied Voltage (V)", style="readonly"),
        Item("last_frequency", label="Last Applied Frequency (Hz)", style="readonly"),
        ),
        label="Hardware Config",
        show_border=True,
        style_sheet=preferences_group_style_sheet,
    ),

    view = View(

        Item("_"),  # Separator
        settings,
        Item("_"),
        hardware_config,
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


class VoltageFrequencyRangePane(PreferencesPane):
    """Voltage/frequency range limits, displayed under the Protocol Settings tab.

    Uses VoltageFrequencyRangePreferences as its model (separate from DropbotPreferences).
    On change, publishes all four range values via VOLTAGE_FREQUENCY_RANGE_CHANGED so
    that open spinners across manual controls, dropbot status, and protocol grid
    update their bounds immediately.
    """

    #### 'PreferencesPane' interface ##########################################

    model_factory = VoltageFrequencyRangePreferences
    category = protocol_grid_tab.id

    #### View definition ################################

    # Create the grid group for the sidebar items.
    # Each tuple pairs a trait name with its display label.
    # With 2 columns, items fill left→right per row:
    #   Row 1: Min Voltage     | Min Frequency
    #   Row 2: Max Voltage     | Max Frequency
    #   Row 3: Default Voltage | Default Frequency
    _FIELD_LABEL_PAIRS = (
        ("ui_min_voltage",       "Min Voltage (V)"),
        ("ui_min_frequency",     "Min Frequency (Hz)"),
        ("ui_max_voltage",       "Max Voltage (V)"),
        ("ui_max_frequency",     "Max Frequency (Hz)"),
        ("ui_default_voltage",   "Default Voltage (V)"),
        ("ui_default_frequency", "Default Frequency (Hz)"),
    )

    range_settings = create_grid_group(
        [f for f, _ in _FIELD_LABEL_PAIRS],
        label_text=[l for _, l in _FIELD_LABEL_PAIRS],
        group_label="Protocol Setters Config",
        group_show_border=True,
        group_style_sheet=preferences_group_style_sheet,
        group_columns=4
    )

    view = View(
        Item("_"),
        range_settings,
        Item("_"),
        resizable=True
    )

    @observe("model:[ui_min_voltage, ui_max_voltage, ui_min_frequency, ui_max_frequency]")
    def publish_range_change(self, event):
        """Publish all four range values when any one changes, so subscribers
        can update their spinner bounds in one shot."""
        if event.new != event.old:
            msg = json.dumps({
                "ui_min_voltage": int(self.model.ui_min_voltage),
                "ui_max_voltage": int(self.model.ui_max_voltage),
                "ui_min_frequency": int(self.model.ui_min_frequency),
                "ui_max_frequency": int(self.model.ui_max_frequency),
            })
            publish_message(msg, VOLTAGE_FREQUENCY_RANGE_CHANGED)