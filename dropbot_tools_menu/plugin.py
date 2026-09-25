# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import Bool, Instance, List, Str, observe

# Microdrop package imports.
from dropbot_controller.consts import (
    CHIP_INSERTED,
    DROPBOT_CONNECTED,
    DROPBOT_DISCONNECTED,
    SELF_TESTS_PROGRESS,
    SELF_TESTS_RESULTS,
)
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG

# Microdrop utils imports.
from microdrop_utils.dramatiq_controller_base import (
    generate_class_method_dramatiq_listener_actor,
)

# Local imports.
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class DropbotToolsMenuPlugin(Plugin):
    """Contributes UI actions on top of the IPython Kernel Plugin."""

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
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    dropbot_connected = Bool(False)

    #: Shows the self-test progress and results dialogs; built on first use
    #: so the Qt/matplotlib dialog modules load only when a test runs.
    self_test_dialogs_controller = Instance(
        "dropbot_tools_menu.self_test_dialogs_controller.SelfTestDialogsController"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_listener_actor()

    #### Trait initializers ###################################################

    def _self_test_dialogs_controller_default(self):
        from .self_test_dialogs_controller import SelfTestDialogsController

        return SelfTestDialogsController(application=self.application)

    def _contributed_task_extensions_default(self):

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        factory=self.dropbot_tools_menu_factory,
                        path="MenuBar/Tools",
                    )
                ],
            )
        ]

    @observe("application:application_initialized")
    def on_application_initialized(self, event):
        # Wait for the window to be created
        if self.application.active_window is None:
            # If window is not created yet, observe the window creation
            self.application.on_trait_change(self._on_window_created, "active_window")
            return

    def _on_window_created(self, window):
        """Called when the application window is created."""
        if window is not None:
            # Remove the observer since we don't need it anymore
            self.application.on_trait_change(
                self._on_window_created, "active_window", remove=True
            )

    def _listener_actor_routine(self, message, topic):
        if topic == CHIP_INSERTED:
            logger.debug(f"Received {topic} signal")
            self.dropbot_connected = True
            logger.info("Chip inserted signal received; marking DropBot connected")
        elif topic == DROPBOT_DISCONNECTED:
            logger.debug(f"Received {topic} signal")
            self.dropbot_connected = False
            logger.info(f"Dropbot connected: {self.dropbot_connected}")
        elif topic == DROPBOT_CONNECTED:
            logger.debug(f"Received {topic} signal")
            self.dropbot_connected = True
            logger.info(f"Dropbot connected: {self.dropbot_connected}")
        elif topic == SELF_TESTS_PROGRESS:
            self.self_test_dialogs_controller.on_self_tests_progress(message)
        elif topic == SELF_TESTS_RESULTS:
            self.self_test_dialogs_controller.on_self_tests_results(message)

    def _setup_listener_actor(self):
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=f"{PKG}_listener", class_method=self._listener_actor_routine
        )

    def dropbot_tools_menu_factory(self):
        from .menus import dropbot_tools_menu_factory

        return dropbot_tools_menu_factory(plugin=self)
