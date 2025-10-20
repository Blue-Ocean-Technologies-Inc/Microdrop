# Standard library imports.
from pathlib import Path

from traits.api import List, Str
from device_viewer.menus import load_svg_dialog_menu_factory, open_svg_dialogue_menu_factory
from message_router.consts import ACTOR_TOPIC_ROUTES

# Enthought library imports.
from envisage.api import Plugin, TASK_EXTENSIONS, PREFERENCES_PANES, PREFERENCES_CATEGORIES
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition

# local imports
from microdrop_application.consts import PKG as microdrop_application_PKG
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name
from logger.logger_service import get_logger

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

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    ###########################################################################
    # Protected interface.
    ###########################################################################

    def _preferences_panes_default(self):
        from .preferences import DeviceViewerPreferencesPane

        return [DeviceViewerPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import device_viewer_tab
        return [device_viewer_tab]

    def _contributed_task_extensions_default(self):
        from .views.device_view_dock_pane import DeviceViewerDockPane

        return [ 
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[DeviceViewerDockPane],
                actions=[
                    SchemaAddition(
                        factory=load_svg_dialog_menu_factory,
                        path='MenuBar/File'
                    ),
                    SchemaAddition(
                        factory=open_svg_dialogue_menu_factory,
                        path='MenuBar/File'
                    )

                ]
            )
        ]