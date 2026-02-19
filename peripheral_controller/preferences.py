from apptools.preferences.api import PreferencesHelper
from traits.api import Dict, Property
from pyface.api import warning

from logger.logger_service import get_logger
logger = get_logger(__name__)

from microdrop_application.helpers import get_microdrop_redis_globals_manager
app_globals = get_microdrop_redis_globals_manager()

from microdrop_utils.pyface_helpers import RangeWithViewHints

from .consts import DEFAULT_UP_HEIGHT_MM, DEFAULT_DOWN_HEIGHT_MM, MAX_ZSTAGE_HEIGHT_MM, MIN_ZSTAGE_HEIGHT_MM

z_stage_preferences_names = [
            'down_height_mm', 'up_height_mm'
        ]

z_stage_trait_name_mapping = {
    'down_height_mm': 'zstage_down_position',
    'up_height_mm': 'zstage_up_position',
}


class PeripheralPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.peripheral_settings"


    up_height_mm = RangeWithViewHints(
        value=DEFAULT_UP_HEIGHT_MM,
        low=MIN_ZSTAGE_HEIGHT_MM + 0.1,
        high=MAX_ZSTAGE_HEIGHT_MM,
        desc="Height of stage when up command sent"
    )

    _max_down_height = Property(observe="up_height_mm")

    down_height_mm = RangeWithViewHints(
        value=DEFAULT_DOWN_HEIGHT_MM,
        low=MIN_ZSTAGE_HEIGHT_MM,
        high="_max_down_height",
        desc="Height of stage when down command sent"
    )

    #### Preferences ##########################################################

    preferences_name_map = Property(Dict)

    ################ View Model ################################################

    def _get__max_down_height(self):
        return self.up_height_mm - 0.1