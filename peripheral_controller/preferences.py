from apptools.preferences.api import PreferencesHelper
from traits.api import Float, Int, Dict, Property, Range
from logger.logger_service import get_logger

from .consts import DEFAULT_UP_HEIGHT_MM, DEFAULT_DOWN_HEIGHT_MM, MAX_ZSTAGE_HEIGHT_MM, MIN_ZSTAGE_HEIGHT_MM

logger = get_logger(__name__)

from microdrop_application.helpers import get_microdrop_redis_globals_manager
z_stage_preferences_names = [
            'down_height_mm', 'up_height_mm'
        ]

app_globals = get_microdrop_redis_globals_manager()

class PeripheralPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.peripheral_settings"


    up_height_mm = Range(value=DEFAULT_UP_HEIGHT_MM, low=MIN_ZSTAGE_HEIGHT_MM, high=MAX_ZSTAGE_HEIGHT_MM,
                         desc="Height of stage when up command sent")

    down_height_mm = Range(value=DEFAULT_DOWN_HEIGHT_MM, low=MIN_ZSTAGE_HEIGHT_MM, high=DEFAULT_UP_HEIGHT_MM,
                         desc="Height of stage when down command sent")

    #### Preferences ##########################################################

    preferences_name_map = Property(Dict)

    ################ View Model ################################################

    def _get_preferences_name_map(self):
        # Use a dict comprehension to build the dictionary
        return {pref: getattr(self, pref) for pref in z_stage_preferences_names}