# enthought imports
from traits.api import List, Str, Bool
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor
from dropbot_controller.consts import DROPBOT_DISCONNECTED, CHIP_INSERTED, DROPBOT_CONNECTED

from microdrop_utils._logger import get_logger

# This module's package.
from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT

logger = get_logger(__name__)


class ProtocolGridControllerUIPlugin(Plugin):

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"

    #: The plugin name (suitable for displaying to the user).
    name = PKG_name

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    dropbot_connected = Bool(False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_listener_actor()

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .dock_pane import PGCDockPane

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[PGCDockPane]
            )
        ]
    
    def _listener_actor_routine(self, message, topic):
        if topic == CHIP_INSERTED:
            logger.debug(f"Received {topic} signal")
            self.dropbot_connected = True
            logger.info(f"Dropbot connected: {self.dropbot_connected}")
        elif topic == DROPBOT_DISCONNECTED:
            logger.debug(f"Received {topic} signal")
            self.dropbot_connected = False   
            logger.info(f"Dropbot connected: {self.dropbot_connected}")
        elif topic == DROPBOT_CONNECTED:
            logger.debug(f"Received {topic} signal")
            self.dropbot_connected = True
            logger.info(f"Dropbot connected: {self.dropbot_connected}")

    def _setup_listener_actor(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=f"{PKG}_dropbot_listener",
            class_method=self._listener_actor_routine
        )