from template_status_and_controls.base_plugin import BaseStatusPlugin

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT


class HeaterControlsUiPlugin(BaseStatusPlugin):
    """Envisage plugin for heater status display and controls.

    Contributes a Tools ▸ Heater ▸ Search Connection menu entry (the heater's
    connection scan, also reachable by clicking the status-bar heater icon).
    """

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_pane import HeaterStatusDockPane
        return HeaterStatusDockPane

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT

    def _get_menu_additions(self) -> list:
        from pyface.action.schema.schema_addition import SchemaAddition
        from .menus import heater_tools_menu_factory
        return [
            SchemaAddition(
                factory=heater_tools_menu_factory,
                path="MenuBar/Tools",
            )
        ]
