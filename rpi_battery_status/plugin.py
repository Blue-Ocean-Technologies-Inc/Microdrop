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
from envisage.api import Plugin
from traits.api import Instance, List
from traitsui.api import UI

# Microdrop package imports.
from microdrop_status_bar.consts import STATUS_BAR_ICONS

# Local imports.
from .consts import PKG, PKG_name
from .controllers.battery_status_controller import BatteryStatusController
from .views.battery_details_view import show_battery_details
from .views.battery_status_view import build_status_bar_icon

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class RpiBatteryStatusPlugin(Plugin):
    """Show the Raspberry Pi battery in the app status bar.

    Reads the rpi-battery-monitor daemon's status file; where no daemon
    runs (e.g. Windows dev machines) the icon stays grey. Clicking (or
    tapping) the icon opens a small panel with the full readings, which
    keeps updating while it is open.

    The icon is built in ``start()``: ``TasksApplication.run`` creates its
    pyface GUI, and with it the QApplication, before starting plugins, and
    a hot load starts the plugin in the running app. The status-bar plugin
    places contributions made before its window exists once it does.
    """

    #: The plugin unique identifier.
    id = PKG + ".plugin"

    #: The plugin name (suitable for displaying to the user).
    name = f"{PKG_name} Plugin"

    #: The battery icon while the plugin runs.
    status_bar_icons = List(contributes_to=STATUS_BAR_ICONS)

    #: Polls the daemon's status file into the battery model.
    controller = Instance(BatteryStatusController, ())

    #: The contributed status-bar widget while the plugin runs.
    _icon = Instance("pyface.qt.QtWidgets.QWidget")

    #: The TraitsUI UI inside that widget while the plugin runs.
    _icon_ui = Instance(UI)

    #: The details panel's UI once opened; its control is None once closed.
    _details_ui = Instance(UI)

    def start(self):
        """Contribute the battery icon and start polling."""
        self._icon, self._icon_ui = build_status_bar_icon(
            self.controller.model, on_click=self._show_details
        )
        self.status_bar_icons.append(self._icon)

        self.controller.start()

    def stop(self):
        """Stop polling and withdraw the icon and its panel (hot unload)."""
        self.controller.stop()

        if self._details_ui is not None and self._details_ui.control is not None:
            # The panel is a child of the icon, which the window may
            # already have deleted at app exit.
            try:
                self._details_ui.dispose()
            except RuntimeError as e:
                logger.debug(f"Battery details panel already deleted: {e}")

        self._details_ui = None

        if self._icon_ui is not None:
            self.status_bar_icons.remove(self._icon)

            # At app exit the window may already have deleted the widget.
            try:
                self._icon_ui.dispose()
            except RuntimeError as e:
                logger.debug(f"Battery icon already deleted: {e}")

            self._icon = None
            self._icon_ui = None

    def _show_details(self):
        """Open the details panel at the icon, or raise the open one."""
        self._details_ui = show_battery_details(
            self.controller.model, self._icon, self._details_ui
        )
