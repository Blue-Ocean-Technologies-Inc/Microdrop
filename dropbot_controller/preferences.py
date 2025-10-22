from apptools.preferences.api import PreferencesHelper
from traits.api import Float, Int, Dict, Property
from logger.logger_service import get_logger

logger = get_logger(__name__)

from .consts import DROPLET_DETECTION_CAPACITANCE_THRESHOLD

from microdrop_application.helpers import get_microdrop_redis_globals_manager
preferences_names = [
            'droplet_detection_capacitance',
            'capacitance_update_interval',
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

    preferences_name_map = Property(Dict)

    def _droplet_detection_capacitance_default(self):
        return app_globals.get(preferences_names[0], DROPLET_DETECTION_CAPACITANCE_THRESHOLD)

    def _capacitance_update_interval_default(self):
        return app_globals.get(preferences_names[1], 100)

    def _get_preferences_name_map(self):
        # Use a dict comprehension to build the dictionary
        return {pref: getattr(self, pref) for pref in preferences_names}

