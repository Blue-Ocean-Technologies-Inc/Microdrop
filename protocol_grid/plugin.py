# enthought imports
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import List, Str
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from logger.logger_service import get_logger

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT

logger = get_logger(__name__)


class ProtocolGridControllerUIPlugin(Plugin):

    id = PKG + ".plugin"
    name = PKG_name

    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    # ProtocolPreferencesPane + protocol_grid_tab are contributed by
    # PluggableProtocolTreePlugin since #419 relocated the preferences there
    # (contributing them here too would duplicate the Settings tab).
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def _contributed_task_extensions_default(self):
        from .dock_pane import PGCDockPane
        from .menus import tools_menu_factory, new_experiment_factory

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[PGCDockPane],
                actions=[
                    SchemaAddition(
                        factory=new_experiment_factory,
                        path='MenuBar/File',
                        absolute_position="first",
                    ),
                    SchemaAddition(
                        factory=tools_menu_factory,
                        path='MenuBar/File',
                        before="Exit",
                    ),
                ]
            )
        ]