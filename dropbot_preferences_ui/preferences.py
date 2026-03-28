import json

from apptools.preferences.api import PreferencesHelper
from protocol_grid.preferences import protocol_grid_tab
from traits.api import observe, Range
from traitsui.api import VGroup, HGroup, View, Item
from envisage.ui.tasks.api import PreferencesCategory

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesPane

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.preferences_UI_helpers import create_item_label_group
from dropbot_controller.preferences import DropbotPreferences
from dropbot_controller.consts import CHANGE_SETTINGS

from .consts import (
    DEFAULT_MIN_VOLTAGE, DEFAULT_MAX_VOLTAGE,
    DEFAULT_MIN_FREQUENCY, DEFAULT_MAX_FREQUENCY,
    VOLTAGE_FREQUENCY_RANGE_CHANGED,
)

from logger.logger_service import get_logger
logger = get_logger(__name__)


class VoltageFrequencyRangePreferences(PreferencesHelper):
    """Frontend-only preferences for voltage/frequency spinner range limits.

    These control the min/max bounds on voltage and frequency spinners across
    all frontend plugins (manual controls, dropbot status, protocol grid).
    Persisted under a separate preferences path from DropbotPreferences since
    they are purely a UI concern and do not affect backend hardware validation.
    """

    preferences_path = "microdrop.voltage_frequency_range"

    min_voltage = Range(low=0, high=300, value=DEFAULT_MIN_VOLTAGE,
                        desc="minimum allowed voltage in V")
    max_voltage = Range(low=0, high=300, value=DEFAULT_MAX_VOLTAGE,
                        desc="maximum allowed voltage in V")
    min_frequency = Range(low=0, high=100_000, value=DEFAULT_MIN_FREQUENCY,
                          desc="minimum allowed frequency in Hz")
    max_frequency = Range(low=0, high=100_000, value=DEFAULT_MAX_FREQUENCY,
                          desc="maximum allowed frequency in Hz")


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


class VoltageFrequencyRangePane(PreferencesPane):
    """Voltage/frequency range limits, displayed under the Protocol Settings tab.

    Uses VoltageFrequencyRangePreferences as its model (separate from DropbotPreferences).
    On change, publishes all four range values via VOLTAGE_FREQUENCY_RANGE_CHANGED so
    that open spinners across manual controls, dropbot status, and protocol grid
    update their bounds immediately.
    """

    model_factory = VoltageFrequencyRangePreferences
    category = protocol_grid_tab.id

    voltage_range_settings = VGroup(
        HGroup(
            create_item_label_group("min_voltage", label_text="Min Voltage (V)"),
            create_item_label_group("max_voltage", label_text="Max Voltage (V)"),
        ),
        label="Voltage Range",
        show_border=True,
    ),

    frequency_range_settings = VGroup(
        HGroup(
            create_item_label_group("min_frequency", label_text="Min Frequency (Hz)"),
            create_item_label_group("max_frequency", label_text="Max Frequency (Hz)"),
        ),
        label="Frequency Range",
        show_border=True,
    ),

    view = View(
        Item("_"),
        voltage_range_settings,
        Item("_"),
        frequency_range_settings,
        Item("_"),
        resizable=True
    )

    @observe("model:[min_voltage, max_voltage, min_frequency, max_frequency]")
    def publish_range_change(self, event):
        """Publish all four range values when any one changes, so subscribers
        can update their spinner bounds in one shot."""
        if event.new != event.old:
            msg = json.dumps({
                "min_voltage": int(self.model.min_voltage),
                "max_voltage": int(self.model.max_voltage),
                "min_frequency": int(self.model.min_frequency),
                "max_frequency": int(self.model.max_frequency),
            })
            publish_message(msg, VOLTAGE_FREQUENCY_RANGE_CHANGED)