# enthought imports
from traits.api import List, Str, Bool
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from protocol_grid.services.message_listener import MessageListener
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
        self._message_listener = None
        # self._droplet_detection_service = DropletDetectionService()
        # self._dropbot_controller_plugin = None
        # self._initialization_attempts = 0
        # self._max_initialization_attempts = 10
        self._setup_listener()

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .dock_pane import PGCDockPane

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[PGCDockPane]
            )
        ]

    def _setup_listener(self):
        try:
            if self._message_listener is None:                
                self._message_listener = MessageListener()

                self._message_listener.signal_emitter.dropbot_connection_changed.connect(
                    self._on_dropbot_connection_changed
                )

                logger.info("Protocol Grid Message Listener setup complete")
            else:
                logger.info("message listener already exists, refusing")
        except Exception as e:
            logger.info(f"failed to setup message listener: {e}")

    def _on_dropbot_connection_changed(self, connected):
        self.dropbot_connected = connected
        logger.info(f"Dropbot connection status changed: {connected}")
        # if connected:
        #     self._initialization_attempts = 0
        #     self._initialize_droplet_detection_service()
    
    def get_listener(self):
        return self._message_listener