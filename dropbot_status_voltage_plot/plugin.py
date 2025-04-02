# enthought imports
from traits.api import List
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension

from .consts import PKG, ACTOR_TOPIC_DICT

# microdrop imports
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_utils._logger import get_logger
# Initialize logger
logger = get_logger(__name__)


class DropbotStatusVoltagePlotPlugin(Plugin):
    """ Contributes a dropbot status UI view with plots. """

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG.title().replace("_", " ")

    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .dock_pane import DropbotStatusVoltagePlotDockPane
        from device_viewer.consts import PKG

        return [
            TaskExtension(
                task_id=f"{PKG}.task",  # specify which task id it has to add on to
                dock_pane_factories=[
                    DropbotStatusVoltagePlotDockPane
                ],
            )
        ]
