# Standard library imports.
import os.path

from traits.api import List, Str
from device_viewer.menus import open_file_dialogue_menu_factory, open_svg_dialogue_menu_factory
from message_router.consts import ACTOR_TOPIC_ROUTES

# Enthought library imports.
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskFactory, TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition

# local imports
from microdrop_application.consts import PKG as microdrop_application_PKG
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class DeviceViewerPlugin(Plugin):
    """Device Viewer plugin based on enthought envisage's The chaotic attractors plugin."""

    #### 'IPlugin' interface ##################################################

    # The plugin's unique identifier.
    id = PKG

    # The plugin's name (suitable for displaying to the user).
    name = PKG_name + " Plugin"

    #### Contributions to extension points made by this plugin ################
    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _contributed_task_extensions_default(self):
        from .views.device_view_pane import DeviceViewerDockPane

        return [ 
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[DeviceViewerDockPane],
                actions=[
                    SchemaAddition(
                        factory=open_file_dialogue_menu_factory,
                        path='MenuBar/File'
                    ),
                    SchemaAddition(
                        factory=open_svg_dialogue_menu_factory,
                        path='MenuBar/File'
                    )

                ]
            )
        ]