# enthought imports
from envisage.ids import PREFERENCES_PANES, PREFERENCES_CATEGORIES
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

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    def _preferences_panes_default(self):
        from .preferences import ProtocolPreferencesPane
        return [ProtocolPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import protocol_grid_tab
        return [protocol_grid_tab]

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