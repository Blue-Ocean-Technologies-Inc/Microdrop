from apptools.preferences.api import PreferencesHelper
from traits.api import Float, Int, Dict, Property, Range, observe
from logger.logger_service import get_logger

logger = get_logger(__name__)

from .consts import (
    DROPLET_DETECTION_CAPACITANCE_THRESHOLD,
    HARDWARE_DEFAULT_VOLTAGE,
    HARDWARE_DEFAULT_FREQUENCY, HARDWARE_MIN_VOLTAGE, HARDWARE_MIN_FREQUENCY,
)

from microdrop_application.helpers import get_microdrop_redis_globals_manager
preferences_names = [
            'droplet_detection_capacitance',
            'capacitance_update_interval',
            '_hardware_max_voltage', '_hardware_max_frequency',
        ]

app_globals = get_microdrop_redis_globals_manager()

class DropbotPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.dropbot_settings"

    #### Preferences ##########################################################
    droplet_detection_capacitance = Float(desc="Threshold for electrode capcitance past which we consider a droplet present.")
    capacitance_update_interval = Int(desc="how often to poll capacitance from dropbot (in ms)")

    # Upper bound is a trait reference (string) — Traits dynamically resolves
    # it against hardware_max_voltage/hardware_max_frequency at validation time.
    last_voltage = Range(
        HARDWARE_MIN_VOLTAGE,
        "_hardware_max_voltage",
        value=HARDWARE_DEFAULT_VOLTAGE,
        desc="the voltage last set on the dropbot device in V",
    )
    last_frequency = Range(
        HARDWARE_MIN_FREQUENCY,
        "_hardware_max_frequency",
        value=HARDWARE_DEFAULT_FREQUENCY,
        desc="the frequency last set on the dropbot device in Hz",
    )

    # Readonly hardware limits — set at runtime when DropBot connects.
    # Default to inf so the Range traits above are unconstrained until a device reports its limits.
    _hardware_max_voltage = Float(float("inf"), desc="maximum voltage from connected hardware")
    _hardware_max_frequency = Float(float("inf"), desc="maximum frequency from connected hardware")

    preferences_name_map = Property(Dict)

    ################ View Model ################################################
    droplet_detection_capacitance_view = Property(Float, observe="droplet_detection_capacitance")
    capacitance_update_interval_view = Property(Int, observe="capacitance_update_interval")

    _hardware_max_voltage_view = Property(Float)
    _hardware_max_frequency_view = Property(Float)

    def traits_init(self):
        """Seed traits from app_globals so downstream observers fire on startup."""
        self.droplet_detection_capacitance = self._get_droplet_detection_capacitance_view()
        self.capacitance_update_interval = self._get_capacitance_update_interval_view()

    def _droplet_detection_capacitance_default(self):
        return DROPLET_DETECTION_CAPACITANCE_THRESHOLD

    def _capacitance_update_interval_default(self):
        return 100

    def __hardware_max_voltage_view_default(self):
        return float(app_globals.get(preferences_names[2], float("inf")))

    def __hardware_max_frequency_view_default(self):
        return float(app_globals.get(preferences_names[3], float("inf")))

    def _get_droplet_detection_capacitance_view(self):
        return app_globals.get(preferences_names[0], DROPLET_DETECTION_CAPACITANCE_THRESHOLD)

    def _get_capacitance_update_interval_view(self):
        return app_globals.get(preferences_names[1], 100)

    def _get__hardware_max_voltage_view(self):
        return self.__hardware_max_voltage_view_default()

    def _get__hardware_max_frequency_view(self):
        return self.__hardware_max_frequency_view_default()

    def _set_droplet_detection_capacitance_view(self, value):
        self.droplet_detection_capacitance = value

    def _set_capacitance_update_interval_view(self, value):
        self.capacitance_update_interval = value

    def _get_preferences_name_map(self):
        # Use a dict comprehension to build the dictionary
        return {pref: getattr(self, pref) for pref in preferences_names}

    @observe('[_hardware_max_voltage, _hardware_max_frequency]')
    def _hardware_limit_changed(self, event):
        """Sync hardware limits to app_globals so view properties stay current."""
        logger.debug(f"Hardware limit changed: {event.name} = {event.new}")
        app_globals[event.name] = event.new
