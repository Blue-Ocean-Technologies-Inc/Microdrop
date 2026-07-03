# Standard library imports.
from traits.api import List, Str
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_status_bar.consts import STATUS_BAR_ICONS

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

    #: Status-bar widgets contributed at runtime: the device-viewer dock
    #: pane extends this list (joystick + recording icons); the
    #: microdrop_status_bar plugin places, spaces, and removes them.
    status_bar_icons = List(contributes_to=STATUS_BAR_ICONS)

    ###########################################################################
    # Protected interface.
    ###########################################################################

    def _preferences_panes_default(self):
        from .preferences import DeviceViewerPreferencesPane,DeviceViewerAdvancedPreferencesPane
        from .views.camera_control_view.preferences import CameraPreferencesPane

        return [DeviceViewerPreferencesPane, CameraPreferencesPane, DeviceViewerAdvancedPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import device_viewer_tab
        return [device_viewer_tab]

    def _contributed_task_extensions_default(self):
        from .views.device_view_dock_pane import DeviceViewerDockPane
        from .menus import tools_menu_factory

        return [ 
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[DeviceViewerDockPane],
                actions=[
                    SchemaAddition(
                        factory=tools_menu_factory,
                        path='MenuBar/File',
                        before='Exit',
                    ),
                ]
            )
        ]