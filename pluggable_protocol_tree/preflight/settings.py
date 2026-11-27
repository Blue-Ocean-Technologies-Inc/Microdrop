# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Opens the Settings dialog on the Protocol Settings tab, for the card's
"All protocol settings…" link."""

# Enthought library imports.
from envisage.ui.tasks.api import PreferencesDialog

# Microdrop package imports.
from pluggable_protocol_tree.consts import PROTOCOL_TREE_PREFERENCES_PANE_ID

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def open_protocol_settings(application, parent):
    """Open the application's Settings dialog, modal over ``parent``, on the
    Protocol Settings tab, and save the preferences if it closes on OK, as
    the Settings menu action does."""
    dialog = application.get_service(PreferencesDialog)

    if dialog is None:
        logger.error("No Settings dialog service; cannot open Protocol Settings")

        return

    if dialog.open_on_pane(PROTOCOL_TREE_PREFERENCES_PANE_ID, parent):
        application.preferences.save()
