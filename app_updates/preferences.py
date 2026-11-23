# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from apptools.preferences.api import Preferences, PreferencesHelper
from traits.api import Bool, Str

# Microdrop utils imports.
from microdrop_utils.application_home import updates_preferences_file_path

# Local imports.
from .consts import PREFERENCES_PATH


class AppUpdatesPreferences(PreferencesHelper):
    """Update settings, on whichever preferences node they are given."""

    preferences_path = PREFERENCES_PATH

    #: True: move to the newest release at startup. False: stay on this one.
    auto_update = Bool(True)

    #: The newest release the user has been told about.
    last_announced_version = Str()


def app_updates_preferences():
    """Return the update settings as saved now, on their own file
    (``updates_preferences_file_path``) rather than the application's
    preferences, which every process saves at exit. A missing file means
    the defaults; flushing the returned helper's ``preferences`` saves."""
    preferences = Preferences(filename=str(updates_preferences_file_path()))

    return AppUpdatesPreferences(preferences=preferences)
