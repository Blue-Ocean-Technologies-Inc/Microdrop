import os

from dropbot_preferences_ui.plugin import DropbotPreferencesPlugin
from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
from dropbot_status_and_controls.plugin import DropbotStatusAndControlsPlugin
from logger.plugin import LoggerPlugin
from logger_ui.plugin import LoggerUIPlugin
from manual_controls.plugin import ManualControlsPlugin
from microdrop_application.application import MicrodropApplication
from microdrop_application.backend_application import MicrodropBackendApplication
from microdrop_application.plugin import MicrodropPlugin
from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
from opendrop_status_and_controls.plugin import OpendropStatusAndControlsPlugin
from peripheral_controller.plugin import PeripheralControllerPlugin
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from protocol_grid.plugin import ProtocolGridControllerUIPlugin
from dropbot_controller.plugin import DropbotControllerPlugin
from electrode_controller.plugin import ElectrodeControllerPlugin
from envisage.api import CorePlugin
from envisage.ui.tasks.api import TasksPlugin
from message_router.plugin import MessageRouterPlugin
from microdrop_utils.broker_server_helpers import dramatiq_workers_context, redis_server_context
from device_viewer.plugin import DeviceViewerPlugin
from peripherals_ui.plugin import PeripheralUiPlugin
from opendrop_controller.plugin import OpenDropControllerPlugin
from mock_dropbot_controller.plugin import MockDropbotControllerPlugin
from mock_dropbot_status.plugin import MockDropbotStatusPlugin
from user_help_plugin.plugin import UserHelpPlugin

# The order of plugins matters. This determines whose start routine will be run first,
# and whose contributions will be prioritized
# For example: the microdrop plugin and the tasks contributes a preferences dialog service.
# The dialog contributed by the plugin listed first will be used. That is how the envisage application get_service
# method works.

FRONTEND_PLUGINS = [
    MicrodropPlugin,
    TasksPlugin,
    LoggerUIPlugin,
    ProtocolGridControllerUIPlugin,
    DeviceViewerPlugin,
    PeripheralUiPlugin,
    UserHelpPlugin,
    # PluggableProtocolTreePlugin,
    # DropbotProtocolControlsPlugin
]

DROPBOT_FRONTEND_PLUGINS = [
    DropbotPreferencesPlugin,
    DropbotStatusAndControlsPlugin,
    DropbotToolsMenuPlugin,
]

OPENDROP_FRONTEND_PLUGINS = [
    OpendropStatusAndControlsPlugin
]


BACKEND_PLUGINS = [
    ElectrodeControllerPlugin,
]

OPENDROP_BACKEND_PLUGINS = [
    OpenDropControllerPlugin,
]

DROPBOT_BACKEND_PLUGINS = [
    PeripheralControllerPlugin,
    DropbotControllerPlugin
]

# Mock DropBot plugins — swap these in place of DROPBOT_BACKEND_PLUGINS
# and DROPBOT_FRONTEND_PLUGINS to use the mock controller (no hardware needed).
MOCK_DROPBOT_BACKEND_PLUGINS = [
    MockDropbotControllerPlugin,
]

MOCK_DROPBOT_FRONTEND_PLUGINS = [
    MockDropbotStatusPlugin,
]

REQUIRED_PLUGINS = [
    CorePlugin,
    MessageRouterPlugin,
    LoggerPlugin
]

REQUIRED_CONTEXT = [
    (dramatiq_workers_context, {"worker_threads": 4, "worker_timeout": 100}) #TODO optimize threads and timeout
]

SERVER_CONTEXT = [
    (redis_server_context, {})
]

BACKEND_APPLICATION = MicrodropBackendApplication

FRONTEND_APPLICATION = MicrodropApplication

DEFAULT_APPLICATION = MicrodropApplication
