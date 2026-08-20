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
