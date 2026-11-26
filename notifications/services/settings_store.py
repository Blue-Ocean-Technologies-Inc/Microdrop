# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notification settings kept in settings.json in the notifications data
folder: loaded once, after the main window first paints, then saved shortly
after each change (the chime design's included), a slider's drag written
once. A missing or unreadable file means the defaults."""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from traits.api import Bool, Callable, HasTraits, Instance, observe

# Microdrop utils imports.
from microdrop_utils.json_state_file import read_json_state, write_json_state

# Local imports.
from ..consts import NOTIFICATION_SETTINGS_FILENAME, notifications_data_dir
from ..models.settings import (
    SAVED_CATEGORY_CHOICES,
    SAVED_SETTINGS,
    NotificationSettings,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Milliseconds after a change before the settings are saved.
SAVE_DELAY_MS = 500


class NotificationSettingsStore(HasTraits):
    """Loads the settings from their file, and saves them as they change."""

    settings = Instance(NotificationSettings)

    #: The file; settings.json in the notifications data folder by default.
    path = Instance(Path)

    #: ``invoke_after(milliseconds, callable)`` on the GUI event loop.
    invoke_after = Callable()

    #: Changes are saved only once loaded: never the defaults over the file.
    _loaded = Bool(False)
    _save_queued = Bool(False)

    def _path_default(self):
        return notifications_data_dir() / NOTIFICATION_SETTINGS_FILENAME

    def _invoke_after_default(self):
        from pyface.api import GUI

        return GUI.invoke_after

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def load(self):
        """Take the saved settings, if any; save every change from now on."""
        state = read_json_state(self.path)

        if state is not None:
            rejected = self.settings.apply_state(state)

            if rejected:
                logger.warning(f"Ignored unusable settings in {self.path}: {rejected}")

        self._loaded = True

    def save(self):
        """Write the settings now."""
        self._save_queued = False

        write_json_state(self.path, self.settings.to_state())

    def flush(self):
        """Write a change still waiting to be saved."""

        if self._save_queued:
            self.save()

    # ------------------------------------------------------------------ #
    # Following the settings                                              #
    # ------------------------------------------------------------------ #

    @observe(f"settings:[{', '.join(SAVED_SETTINGS)}]")
    @observe("settings:chime:updated")
    @observe(
        f"settings:groups:items:categories:items:[{', '.join(SAVED_CATEGORY_CHOICES)}]"
    )
    def _queue_save(self, event):

        if not self._loaded or self._save_queued:
            return

        self._save_queued = True
        self.invoke_after(SAVE_DELAY_MS, self.save)
