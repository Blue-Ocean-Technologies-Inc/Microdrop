# Standard library imports.
import logging
import uuid
import os
from pathlib import Path

# Enthought library imports.
from envisage.api import Plugin
from traits.api import  observe

# Local imports
from .logger_service import init_logger, LEVELS
from .consts import PKG, PKG_name
from .preferences import LoggerPreferences


class LoggerPlugin(Plugin):
    """Logger plugin."""

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG_name + " Plugin"

    # #### Plugin interface #####################################################

    def start(self):
        """Starts the plugin."""
        init_logger(preferred_log_level=LEVELS.get(LoggerPreferences().level, logging.INFO),
                    file_handler=self.get_file_handler())

    @observe("application:experiment_changed")
    def _current_exp_dir_changed(self, event):
        print("Changing Log File")
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

                print(f"Log File detached: {handler.baseFilename}")
                break  # Stop after finding the first one

            # 3. Add the new FileHandler
        if old_formatter:  # Check if we actually found one
            new_file_h = self.get_file_handler()

            # Apply the old settings
            new_file_h.setFormatter(old_formatter)
            new_file_h.setLevel(old_level)  # Ensure logging level is preserved

            ROOT_LOGGER.addHandler(new_file_h)
            print(f"Log File Attached: {new_file_h.baseFilename}")
        else:
            print("Warning: No FileHandler was found to replace.")

    def get_file_handler(self):
        logs_path = Path(self.application.current_experiment_directory / "logs")
        logs_path.mkdir(parents=True, exist_ok=True)
        return logging.FileHandler(logs_path / f"{self.application.id.replace('.app', '')}.{uuid.getnode()}-{os.getpid()}.log", mode = 'a')


