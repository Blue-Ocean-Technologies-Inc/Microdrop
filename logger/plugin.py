# Standard library imports.
import logging
from pathlib import Path

# Enthought library imports.
from envisage.api import Plugin
from envisage.ids import PREFERENCES_PANES
from traits.api import List

from .logger_service import LEVELS, file_formatter, console_formatter
from .preferences import LoggerPreferences
from .consts import PKG, PKG_name

class LoggerPlugin(Plugin):
    """Logger plugin."""

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG_name + " Plugin"

    #### Contributions to extension points made by this plugin ################
    # views = List(contributes_to=VIEWS)
    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    ###########################################################################
    # Protected interface.
    ###########################################################################

    def _preferences_panes_default(self):
        from .preferences import LoggerPreferencesPane
        return [LoggerPreferencesPane]

    # #### Plugin interface #####################################################
    #
    def start(self):
        """Starts the plugin."""
        preferred_log_level = LEVELS.get(LoggerPreferences().level, "INFO")

        # Create handlers
        file_handler = logging.FileHandler(self.application.current_experiment_directory / "microdrop_app.log", mode='a')
        file_handler.setFormatter(file_formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)

        # Set root logger initial config
        ROOT_LOGGER = logging.getLogger()
        ROOT_LOGGER.setLevel(preferred_log_level)
        ROOT_LOGGER.handlers = []  # Clear existing handlers
        ROOT_LOGGER.addHandler(file_handler)
        ROOT_LOGGER.addHandler(console_handler)
