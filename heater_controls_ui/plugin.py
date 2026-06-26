from pyface.action.schema.schema_addition import SchemaAddition

from template_status_and_controls.base_plugin import BaseStatusPlugin

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT


class HeaterControlsUiPlugin(BaseStatusPlugin):
    """Envisage plugin for heater status display and controls."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_pane import HeaterStatusDockPane
        return HeaterStatusDockPane

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT

    def _get_menu_additions(self) -> list:
        from .menus import tools_menu_factory
        return [
            SchemaAddition(
                factory=tools_menu_factory,
                path="MenuBar/Tools",
            )
        ]
