from traits.api import List, Str
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT


class PortableManualControlsPlugin(Plugin):
    """Envisage plugin for Portable DropBot manual controls."""

    id = PKG + ".plugin"
    name = f"{PKG_name} Plugin"

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _contributed_task_extensions_default(self):
        from .DockPane import PortableManualControlsDockPane

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[PortableManualControlsDockPane],
            )
        ]
