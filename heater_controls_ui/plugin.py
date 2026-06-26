from template_status_and_controls.base_plugin import BaseStatusPlugin

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT


class HeaterControlsUiPlugin(BaseStatusPlugin):
    """Envisage plugin for heater status display and controls.

    The "Search Connection" tools-menu entry lives in peripherals_ui (listed
    under Tools ▸ Peripherals ▸ Heater alongside the Z-Stage), so this plugin
    contributes no menu of its own.
    """

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_pane import HeaterStatusDockPane
        return HeaterStatusDockPane

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT
