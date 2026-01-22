from apptools.preferences.api import PreferencesHelper
from traits.api import Enum

class LoggerPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "microdrop.logger"

    #### Preferences ##########################################################
    # The log levels
    level = Enum("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    def _level_default(self):
        return "INFO"