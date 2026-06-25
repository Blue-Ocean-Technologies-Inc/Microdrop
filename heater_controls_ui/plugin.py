from envisage.ids import TASK_EXTENSIONS
from traits.api import Str, List
from envisage.api import Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition

from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG
from logger.logger_service import get_logger

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT

logger = get_logger(__name__)


class HeaterControlsUiPlugin(Plugin):
    """Contributes the heater controls dock pane + a Tools-menu connection search."""

    #: The plugin unique identifier.
    id = PKG + ".plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG_name + " Plugin"

    #: The task id to contribute the task extension view to.
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    # This plugin contributes an actor that subscribes to the heater signals.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #### Contributions to extension points made by this plugin ################
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _contributed_task_extensions_default(self):
        from .dock_pane import HeaterControlDockPane

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[HeaterControlDockPane],
                actions=[
                    SchemaAddition(
                        factory=self._tools_menu_factory,
                        path='MenuBar/Tools',
                    )
                ],
            )
        ]

    def _tools_menu_factory(self):
        from .menus import tools_menu_factory
        return tools_menu_factory()
