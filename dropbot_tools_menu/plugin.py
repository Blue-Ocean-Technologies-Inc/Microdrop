# enthought imports
from functools import partial

from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import List, observe, Str
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from message_router.consts import ACTOR_TOPIC_ROUTES
from device_viewer.consts import PKG as device_viewer_PKG

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name

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

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .menus import dropbot_tools_menu_factory

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        factory=dropbot_tools_menu_factory,
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
            
        self._setup_task_listeners()

    def _on_window_created(self, window):
        """Called when the application window is created."""
        if window is not None:
            self._setup_task_listeners()
            # Remove the observer since we don't need it anymore
            self.application.on_trait_change(self._on_window_created, 'active_window', remove=True)

    def _setup_task_listeners(self):
        """Set up the task listeners once the window is available."""
        for task in self.application.active_window.tasks:
            if task.id == f"{device_viewer_PKG}.task":
                # removed the device_viewer_task_method_additions.py file, added below debug statement for sanity check
                logger.debug(f"Task {task.id} is ready to receive progress updates.")