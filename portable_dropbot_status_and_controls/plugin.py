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
from traits.api import observe

# Microdrop package imports.
from template_status_and_controls.base_plugin import BaseStatusPlugin

# Local imports.
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class PortableDropbotStatusAndControlsPlugin(BaseStatusPlugin):
    """Envisage plugin for Portable Dropbot status display, controls,
    and the motor panel."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_panes import PortableDropbotStatusAndControls

        return PortableDropbotStatusAndControls

    def _get_extra_dock_pane_classes(self):
        from .dock_panes import (
            PortableDropbotAdvancedControlsDockPane,
            PortableDropbotCalibrationDockPane,
            PortableDropbotMoreControlsDockPane,
            PortableDropbotMotorsDockPane,
        )

        return [
            PortableDropbotMotorsDockPane,
            PortableDropbotCalibrationDockPane,
            PortableDropbotMoreControlsDockPane,
            PortableDropbotAdvancedControlsDockPane,
        ]

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT

    def _get_menu_additions(self) -> list:
        from pyface.action.schema.schema_addition import SchemaAddition

        from .menus import display_scale_group_factory

        return [
            SchemaAddition(
                factory=display_scale_group_factory,
                path="MenuBar/Tools",
            )
        ]

    def start(self):
        super().start()
        # An xrandr transform does not survive a reboot, so the
        # persisted interface scale is re-applied on every launch.
        from .controllers.display_scale_controller import apply_persisted_scale

        apply_persisted_scale()
        self._widen_dock_separators_on_rpi()

    @observe("application:application_initialized")
    def _on_application_initialized(self, event):
        # Wait for the window to be created
        if self.application.active_window is None:
            self.application.on_trait_change(self._on_window_created, "active_window")
            return

        self._go_fullscreen_on_rpi(self.application.active_window)
        self._enable_touch_flick_scrolling_on_rpi(self.application.active_window)

    def _on_window_created(self, window):
        """Called when the application window is created."""
        if window is None:
            return

        # Remove the observer since we don't need it anymore
        self.application.on_trait_change(
            self._on_window_created, "active_window", remove=True
        )
        self._go_fullscreen_on_rpi(window)
        self._enable_touch_flick_scrolling_on_rpi(window)

    @staticmethod
    def _go_fullscreen_on_rpi(window):
        """Kiosk mode: on the portable rig's touchscreen, fullscreen covers
        the taskbar and removes the title bar (no close/minimize buttons) so
        the instrument doesn't look like a desktop PC — the sidebar's Exit
        button is then the only way back to the desktop. Other platforms
        keep a normal, titled window."""
        from microdrop_utils.system_config import is_rpi

        if not is_rpi():
            return

        if window is None or window.control is None:
            return

        from pyface.api import GUI

        # Deferred so it runs after the window's layout/state restore.
        GUI.invoke_later(window.control.showFullScreen)

    @staticmethod
    def _enable_touch_flick_scrolling_on_rpi(window):
        """Finger-flick kinetic scrolling on every scrollable pane, so lists
        and trees scroll by dragging the content like a phone. The device
        canvas (a QGraphicsView) is excluded — drags there toggle electrodes
        and draw routes."""
        from microdrop_utils.system_config import is_rpi

        if not is_rpi():
            return

        if window is None or window.control is None:
            return

        from pyface.api import GUI
        from pyface.qt.QtWidgets import (
            QAbstractScrollArea,
            QGraphicsView,
            QScroller,
        )

        def grab_scrollers():
            for area in window.control.findChildren(QAbstractScrollArea):
                if isinstance(area, QGraphicsView):
                    continue
                QScroller.grabGesture(
                    area.viewport(), QScroller.ScrollerGestureType.TouchGesture
                )

        # Deferred so every dock pane's widgets exist first.
        GUI.invoke_later(grab_scrollers)

    @staticmethod
    def _widen_dock_separators_on_rpi():
        """The portable rig is a touchscreen — dock-pane resize handles
        must be finger-sized. Other platforms keep the native handle."""
        from microdrop_utils.system_config import is_rpi

        if not is_rpi():
            return

        from pyface.qt.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return

        from microdrop_style.dock_separator_style import get_dock_separator_style
        from microdrop_style.helpers import is_dark_mode

        theme = "dark" if is_dark_mode() else "light"
        app.setStyleSheet(app.styleSheet() + get_dock_separator_style(theme))
