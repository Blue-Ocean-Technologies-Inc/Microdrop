# enthought imports
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import List, Str
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension

from .consts import PKG, ACTOR_TOPIC_DICT

# microdrop imports
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG
from logger.logger_service import get_logger

# Initialize logger
logger = get_logger(__name__)


class PeripheralUiPlugin(Plugin):
    """ Contributes a peripheral status UI view. """

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG.title().replace("_", " ")

    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .dock_pane import PeripheralStatusDockPane

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,  # specify which task id it has to add on to
                dock_pane_factories=[PeripheralStatusDockPane],
                actions=[
                    SchemaAddition(
                        factory=self._tools_menu_factory,
                        path='MenuBar/Tools'
                    )
                ]
            )
        ]

    def _tools_menu_factory(self):
        from .menus import tools_menu_factory

        return tools_menu_factory()