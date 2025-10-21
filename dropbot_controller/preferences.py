from apptools.preferences.api import PreferencesHelper
from traits.api import Float, Int
from logger.logger_service import get_logger

logger = get_logger(__name__)

from .consts import DROPLET_DETECTION_CAPACITANCE_THRESHOLD

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
