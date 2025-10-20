# enthought imports
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import List, Str, Bool, Event
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from protocol_grid.services.message_listener import MessageListener
from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_utils.dramatiq_controller_base import generate_class_method_dramatiq_listener_actor
from dropbot_controller.consts import DROPBOT_DISCONNECTED, CHIP_INSERTED, DROPBOT_CONNECTED
from protocol_grid.services.advanced_mode_menu import advanced_mode_menu_factory


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

    # advanced mode state tracking
    _advanced_mode = Bool(False)
    advanced_mode_changed = Event()

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
                dock_pane_factories=[PGCDockPane],
                actions=[
                    SchemaAddition(
                        factory=lambda: advanced_mode_menu_factory(self),
                        path='MenuBar/Edit',
                        after='Preferences',
                        id='advanced_mode_menu'
                    )
                ]
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
    
    def get_advanced_mode_state(self):
        return self._advanced_mode
    
    def set_advanced_mode_state(self, state):
        """set and sync with widget."""
        if self._advanced_mode != state:
            self._advanced_mode = state
            
            # update NavigationBar checkbox if widget exists
            self._sync_advanced_mode_to_widget(state)
            
            # trigger menu update by firing the event
            self.advanced_mode_changed = True
            
            logger.info(f"Advanced mode state set to: {state}")
    
    def _sync_advanced_mode_to_widget(self, state):
        """Synchronize advanced mode state to NavigationBar checkbox."""
        try:
            # try to find widget through dock pane
            if hasattr(self, '_widget_ref') and self._widget_ref:
                widget = self._widget_ref()
                if widget and hasattr(widget, 'navigation_bar'):
                    # temporarily disconnect signal to prevent infinite loop
                    checkbox = widget.navigation_bar.advanced_user_mode_checkbox
                    
                    # block signals while updating to prevent recursion
                    checkbox.blockSignals(True)
                    checkbox.setChecked(state)
                    checkbox.blockSignals(False)
                    
                    logger.debug(f"Synced advanced mode to widget: {state}")
        except Exception as e:
            logger.error(f"Error syncing advanced mode to widget: {e}")
    
    # method to set widget reference for state synchronization
    def set_widget_reference(self, widget):
        """Set a weak reference to the widget for state synchronization."""
        import weakref
        self._widget_ref = weakref.ref(widget)
        
        # initialize advanced mode state from widget if checkbox exists
        if hasattr(widget, 'navigation_bar') and hasattr(widget.navigation_bar, 'advanced_user_mode_checkbox'):
            initial_state = widget.navigation_bar.advanced_user_mode_checkbox.isChecked()
            if initial_state != self._advanced_mode:
                self._advanced_mode = initial_state
                logger.info(f"Initialized advanced mode state from widget: {initial_state}")