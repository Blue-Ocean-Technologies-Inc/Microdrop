# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Notifications dock pane: docked right, hidden until opened.

The plugin's model collects the notifications on its own, so nothing is
missed while the pane is hidden.
"""

# Enthought library imports.
from pyface.tasks.api import DockPane
from traits.api import Bool, Instance
from traitsui.api import UI

# Local imports.
from .consts import DOCK_PANE_ID, DOCK_PANE_NAME
from .models.notifications_pane_model import NotificationsPaneModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class NotificationsDockPane(DockPane):
    """Shows a NotificationsPaneModel; opened by the status-bar bell."""

    id = DOCK_PANE_ID
    name = DOCK_PANE_NAME
    dock_area = "right"

    #: Hidden until the bell (or the View menu) opens it.
    visible = False

    #: What the pane shows.
    model = Instance(NotificationsPaneModel)

    #: True while the contents are on screen: not while the pane is closed
    #: or behind another tab (pyface's ``visible`` stays True behind a tab).
    showing_contents = Bool(False)

    #: The contents' TraitsUI UI once built.
    _ui = Instance(UI)

    def create(self, parent):
        """Create the pane as pyface does, then follow Qt's visibility."""
        super().create(parent)

        self.control.visibilityChanged.connect(self._follow_dock_visibility)

    def create_contents(self, parent):
        from .views.notifications_view import NotificationsView

        self._ui = self.model.edit_traits(
            view=NotificationsView, kind="subpanel", parent=parent
        )

        return self._ui.control

    def destroy(self):
        """Detach the contents from the model, which outlives the pane."""

        if self.control is not None:
            self.control.visibilityChanged.disconnect(self._follow_dock_visibility)

        self.showing_contents = False

        if self._ui is not None:
            # At app exit the window may already have deleted the contents.
            try:
                self._ui.dispose()

            except RuntimeError as error:
                logger.debug(f"Notifications pane contents already deleted: {error}")

            self._ui = None

        super().destroy()

    def reveal(self):
        """Show the pane and bring it in front of the panes tabbed with it."""
        self.visible = True

        if self.control is not None:
            self.control.raise_()

    def conceal(self):
        """Hide the pane."""
        self.visible = False

    def _follow_dock_visibility(self, visible):
        """Qt's flag, not ``isVisible()``: it turns False behind a tab."""
        self.showing_contents = visible
