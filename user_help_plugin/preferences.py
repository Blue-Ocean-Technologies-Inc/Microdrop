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
from apptools.preferences.api import PreferencesHelper
from traits.api import Str


class UserHelpPreferences(PreferencesHelper):
    """Help-menu settings, attached to the application's global preferences."""

    preferences_path = "microdrop.user_help"

    #: Where the user last pointed Help > Open MicroDrop Setup and Launcher.
    launcher_executable_path = Str()
