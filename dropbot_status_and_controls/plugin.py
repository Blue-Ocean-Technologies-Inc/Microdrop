from pyface.action.schema.schema_addition import SchemaAddition

from template_status_and_controls.base_plugin import BaseStatusPlugin

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class DropbotStatusAndControlsPlugin(BaseStatusPlugin):
    """Envisage plugin for DropBot status display and controls."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_pane import DropbotStatusAndControlsDockPane
        return DropbotStatusAndControlsDockPane

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT

    def _get_menu_additions(self) -> list:
        from .menus import menu_factory
        return [
            SchemaAddition(
                factory=menu_factory,
                before="TaskToggleGroup",
                path="MenuBar/View",
            )
        ]
