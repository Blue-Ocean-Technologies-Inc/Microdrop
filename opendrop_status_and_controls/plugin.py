from template_status_and_controls.base_plugin import BaseStatusPlugin

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT


class OpendropStatusAndControlsPlugin(BaseStatusPlugin):
    """Envisage plugin for OpenDrop status display and controls."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_pane import OpendropStatusAndControls
        return OpendropStatusAndControls

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT
