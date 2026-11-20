# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The app's data folder, and reading a preference before the Envisage
application exists.

Both application modules call ``configure_application_home`` at import time,
so ``ETSConfig`` names the same folders in the frontend, the backend, and any
startup step that runs before either.
"""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from apptools.preferences.api import Preferences
from traits.etsconfig.api import ETSConfig

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Envisage keeps the app's preferences in this file inside the application home.
PREFERENCES_FILENAME = "preferences.ini"

#: The update policy's own file in the application home. Every frontend and
#: backend process saves its start-time copy of ``PREFERENCES_FILENAME`` when
#: it stops, which would undo a policy changed meanwhile in another process;
#: only the app_updates plugin writes this one, the moment it changes.
UPDATES_PREFERENCES_FILENAME = "app_updates.ini"


def configure_application_home():
    """Point ``ETSConfig`` at the MicroDrop company, user-data and home folders."""
    ETSConfig.company = "Sci-Bots"
    ETSConfig.user_data = str(
        Path.home() / "Documents" / ETSConfig.company / "Microdrop"
    )
    ETSConfig.application_home = str(Path(ETSConfig.application_data) / "Microdrop")


def preferences_file_path():
    """Return the path of the app's preferences file."""
    configure_application_home()

    return Path(ETSConfig.application_home) / PREFERENCES_FILENAME


def updates_preferences_file_path():
    """Return the path of the update policy's own preferences file."""
    configure_application_home()

    return Path(ETSConfig.application_home) / UPDATES_PREFERENCES_FILENAME


def read_bool_preference(path, default, filename=None):
    """Read one ``True``/``False`` preference straight from a preferences file.

    Parameters
    ----------
    path : str
        Dotted preference path, e.g. ``"microdrop.app_updates.auto_update"``.
    default : bool
        Returned when the file or key is missing, the value is not a boolean,
        or the preferences file cannot be located or read.
    filename : str or Path, optional
        The file to read; the app's preferences file when omitted.
    """
    # Startup calls this before the app exists, so any failure falls back.
    try:
        if filename is None:
            filename = preferences_file_path()

        value = Preferences(filename=str(filename)).get(path)

    except Exception:
        logger.warning(f"Could not read preference {path}", exc_info=True)

        return default

    return {"true": True, "false": False}.get(str(value).lower(), default)
