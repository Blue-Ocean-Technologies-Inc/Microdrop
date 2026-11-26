# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import faulthandler
import logging
import os
import uuid
from pathlib import Path

# Enthought library imports.
from envisage.api import Plugin
from traits.api import Any, observe

# Local imports.
from .consts import PKG, PKG_name
from .logger_service import LEVELS, init_logger
from .preferences import LoggerPreferences


class LoggerPlugin(Plugin):
    """Logger plugin."""

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG_name + " Plugin"

    #: Open file faulthandler dumps every thread's Python stack into when the
    #: process dies natively (access violation, abort) — such crashes never
    #: reach the logging handlers. Must stay open while enabled.
    _fault_log_file = Any()

    # #### Plugin interface #####################################################

    def start(self):
        """Starts the plugin."""
        init_logger(
            preferred_log_level=LEVELS.get(LoggerPreferences().level, logging.INFO),
            file_handler=self.get_file_handler(),
        )

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
        self._enable_faulthandler(logs_path)

        app_name = self.application.id.replace(".app", "")
        log_name = f"{app_name}.{uuid.getnode()}-{os.getpid()}.log"

        # utf-8: the default locale encoding (cp1252 on Windows) crashes the
        # handler on any non-ASCII character in a log message.
        return logging.FileHandler(
            logs_path / log_name,
            mode="a",
            encoding="utf-8",
        )

    def _enable_faulthandler(self, logs_path):
        """Point faulthandler's native-crash dump at this session's log dir."""
        old_file = self._fault_log_file
        fault_path = logs_path / f"faulthandler.{os.getpid()}.log"

        self._fault_log_file = open(fault_path, "a", encoding="utf-8")
        faulthandler.enable(file=self._fault_log_file, all_threads=True)

        if old_file is not None:
            old_file.close()
