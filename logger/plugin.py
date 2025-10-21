# Standard library imports.
import logging
from pathlib import Path

# Enthought library imports.
from envisage.api import Plugin
from envisage.ids import PREFERENCES_PANES
from traits.api import List, observe

from .dramatiq_listener import DramatiqLoggerControl
from .logger_service import LEVELS, file_formatter, console_formatter
from .preferences import LoggerPreferences
from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT

# microdrop imports
from message_router.consts import ACTOR_TOPIC_ROUTES


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
    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

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

        # start dramatiq listener
        self.dramatiq_listener = DramatiqLoggerControl()

    @observe("application:current_experiment_directory")
    def _current_exp_dir_changed(self, event):
        ROOT_LOGGER = logging.getLogger()

        old_formatter = None
        old_level = None

        for handler in ROOT_LOGGER.handlers[:]:  # Iterate on a copy!
            if isinstance(handler, logging.FileHandler):
                # Save its settings
                old_formatter = handler.formatter
                old_level = handler.level

                # Close and remove it
                handler.close()
                ROOT_LOGGER.removeHandler(handler)

                print(f"Removed: {handler.baseFilename}")
                break  # Stop after finding the first one

            # 3. Add the new FileHandler
        if old_formatter:  # Check if we actually found one
            new_file_h = logging.FileHandler(self.application.current_experiment_directory / "microdrop_app.log")

            # Apply the old settings
            new_file_h.setFormatter(old_formatter)
            new_file_h.setLevel(old_level)  # Ensure logging level is preserved

            ROOT_LOGGER.addHandler(new_file_h)
            print(f"Added: {new_file_h.baseFilename}")
        else:
            print("Warning: No FileHandler was found to replace.")


