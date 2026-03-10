from template_status_and_controls.base_plugin import BaseStatusPlugin

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class MockDropbotStatusPlugin(BaseStatusPlugin):
    """Envisage plugin for MockDropBot status dock pane."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    def _get_dock_pane_class(self):
        from .dock_pane import MockDropbotStatusDockPane
        return MockDropbotStatusDockPane

    def _get_actor_topic_dict(self) -> dict:
        return ACTOR_TOPIC_DICT
