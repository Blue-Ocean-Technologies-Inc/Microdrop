# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Open the plugin load-status panel when the status-bar indicator is
clicked: one modeless panel at a time, opened on the first failure."""

# Enthought library imports.
from traits.api import Instance
from traitsui.api import UI, Controller

# Local imports.
from .load_status_model import PluginLoadStatusPanelModel
from .load_status_view import PluginLoadStatusView

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class PluginLoadStatusController(Controller):
    """Show, raise and close the load-status panel."""

    #: The panel's state.
    model = Instance(PluginLoadStatusPanelModel, ())

    #: The open panel's UI; its control is None once the panel closed.
    _panel_ui = Instance(UI)

    def show_panel(self, parent=None):
        """Open the panel with the first failure selected, or raise it."""
        if self._panel_ui is not None and self._panel_ui.control is not None:
            self._panel_ui.control.raise_()
            self._panel_ui.control.activateWindow()

            return

        self._panel_ui = self.edit_traits(view=PluginLoadStatusView, parent=parent)

        # Selected once the table is on screen: only a visible view scrolls
        # to its new current row, and the failure may be far down the list.
        self.model.select_first_failure()

    def close_panel(self):
        """Close the panel if it is open."""
        if self._panel_ui is not None and self._panel_ui.control is not None:
            # At app exit the window may already have deleted the panel.
            try:
                self._panel_ui.dispose()

            except RuntimeError as error:
                logger.debug(f"Plugin load-status panel already deleted: {error}")

        self._panel_ui = None
