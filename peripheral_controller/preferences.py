from apptools.preferences.api import PreferencesHelper
from traits.api import Float, Int, Dict, Property, Range, observe
from pyface.api import warning

from logger.logger_service import get_logger

from .consts import DEFAULT_UP_HEIGHT_MM, DEFAULT_DOWN_HEIGHT_MM, MAX_ZSTAGE_HEIGHT_MM, MIN_ZSTAGE_HEIGHT_MM

logger = get_logger(__name__)

from microdrop_application.helpers import get_microdrop_redis_globals_manager
z_stage_preferences_names = [
            'down_height_mm', 'up_height_mm'
        ]

app_globals = get_microdrop_redis_globals_manager()

class RangeWithViewHints(Range):
    def create_editor(self):
        """ Returns the default UI editor for the trait.
        """
        # fixme: Needs to support a dynamic range editor.

        auto_set = self.auto_set
        if auto_set is None:
            auto_set = True

        from traitsui.api import RangeEditor

        return RangeEditor(
            self,
            mode=self.mode or "auto",
            cols=self.cols or 3,
            auto_set=auto_set,
            enter_set=self.enter_set or False,
            low_label=self.low or "",
            high_label=self.high or "",
            low_name=self._low_name,
            high_name=self._high_name,
            format_str='%.2f',
            is_float=True
        )

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


    def _get_preferences_name_map(self):
        # Use a dict comprehension to build the dictionary
        return {pref: getattr(self, pref) for pref in z_stage_preferences_names}