from PySide6.QtCore import Property
from apptools.preferences.api import PreferencesHelper
from traits.api import Float, Int, Dict
from logger.logger_service import get_logger

logger = get_logger(__name__)

from .consts import DROPLET_DETECTION_CAPACITANCE_THRESHOLD


preferences_names = [
            'droplet_detection_capacitance',
            'capacitance_update_interval',
        ]

class DropbotPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.dropbot_settings"

    #### Preferences ##########################################################
    droplet_detection_capacitance = Float(DROPLET_DETECTION_CAPACITANCE_THRESHOLD, desc="Threshold for electrode capcitance past which we consider a droplet present.")
    capacitance_update_interval = Int(100, desc="how often to poll capacitance from dropbot (in ms)")

    preferences_name_map = Property(Dict)

    def _get_preferences_name_map(self):
        # Use a dict comprehension to build the dictionary
        return {pref: getattr(self, pref) for pref in preferences_names}
