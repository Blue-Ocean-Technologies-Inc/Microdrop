# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from template_status_and_controls.base_plugin import BaseStatusPlugin

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
