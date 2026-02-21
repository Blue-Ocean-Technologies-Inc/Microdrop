# enthought imports
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from traits.api import List, Str

from logger.logger_service import get_logger
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG

from .consts import ACTOR_TOPIC_DICT, PKG

logger = get_logger(__name__)


class OpenDropStatusPlugin(Plugin):
    """Contributes an OpenDrop status UI view."""

    id = PKG + ".plugin"
    name = PKG.title().replace("_", " ")

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _contributed_task_extensions_default(self):
        from .dock_pane import OpenDropStatusDockPane

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[OpenDropStatusDockPane],
            )
        ]
