# enthought imports
from functools import partial

from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import List, observe, Str, Bool
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from message_router.consts import ACTOR_TOPIC_ROUTES
from device_viewer.consts import PKG as device_viewer_PKG

from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name

from dropbot_controller.consts import DROPBOT_SETUP_SUCCESS
from microdrop_utils.dramatiq_dropbot_serial_proxy import DISCONNECTED

from microdrop_utils._logger import get_logger
logger = get_logger(__name__)


class DropbotToolsMenuPlugin(Plugin):
    """ Contributes UI actions on top of the IPython Kernel Plugin. """

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"

    #: The plugin name (suitable for displaying to the user).
    name = f"{PKG_name} Plugin"

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    # This plugin wants some actors to be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{device_viewer_PKG}.task")

    dropbot_connected = Bool(False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_listener_actor()
    
    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        factory=self.dropbot_tools_menu_factory,
                        path='MenuBar/Tools',
                    )

                ]
            )
        ]

    @observe("application:application_initialized")
    def on_application_initialized(self, event):
        # Wait for the window to be created
        if self.application.active_window is None:
            # If window is not created yet, observe the window creation
            self.application.on_trait_change(self._on_window_created, 'active_window')
            return

    def _on_window_created(self, window):
        """Called when the application window is created."""
        if window is not None:
            # Remove the observer since we don't need it anymore
            self.application.on_trait_change(self._on_window_created, 'active_window', remove=True)     

    def _listener_actor_routine(self, message, topic):
        if topic == DROPBOT_SETUP_SUCCESS:
            logger.debug(f"Received {topic} signal")
            self.dropbot_connected = True
            print(f"Dropbot connected: {self.dropbot_connected}")
        elif topic == DISCONNECTED:
            logger.debug(f"Received {topic} signal")
            self.dropbot_connected = False   
            print(f"Dropbot connected: {self.dropbot_connected}")
    
    def _setup_listener_actor(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=f"{PKG}_listener",
            class_method=self._listener_actor_routine)    
    
    def dropbot_tools_menu_factory(self):
        from .menus import dropbot_tools_menu_factory

        return dropbot_tools_menu_factory(plugin = self)