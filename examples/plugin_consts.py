from dropbot_preferences_ui.plugin import DropbotPreferencesPlugin
from logger.plugin import LoggerPlugin
from microdrop_application.application import MicrodropApplication
from microdrop_application.backend_application import MicrodropBackendApplication
from microdrop_application.plugin import MicrodropPlugin
from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
from dropbot_status.plugin import DropbotStatusPlugin
from manual_controls.plugin import ManualControlsPlugin
from peripheral_controller.plugin import PeripheralControllerPlugin
from protocol_grid.plugin import ProtocolGridControllerUIPlugin
from dropbot_controller.plugin import DropbotControllerPlugin
from electrode_controller.plugin import ElectrodeControllerPlugin
from envisage.api import CorePlugin
from envisage.ui.tasks.api import TasksPlugin
from message_router.plugin import MessageRouterPlugin
from microdrop_utils.broker_server_helpers import dramatiq_workers_context, redis_server_context
from device_viewer.plugin import DeviceViewerPlugin
from peripherals_ui.plugin import PeripheralUiPlugin

# The order of plugins matters. This determines whose start routine will be run first,
# and whose contributions will be prioritized
# For example: the microdrop plugin and the tasks contributes a preferences dialog service.
# The dialog contributed by the plugin listed first will be used. That is how the envisage application get_service
# method works.

FRONTEND_PLUGINS = [
    MicrodropPlugin,
    TasksPlugin,
    # DropbotStatusPlotPlugin,
    DropbotToolsMenuPlugin,
    DropbotStatusPlugin,
    ManualControlsPlugin,
    ProtocolGridControllerUIPlugin,
    DeviceViewerPlugin,
    PeripheralUiPlugin,
    DropbotPreferencesPlugin
]

BACKEND_PLUGINS = [
    DropbotControllerPlugin,
    ElectrodeControllerPlugin,
    PeripheralControllerPlugin
]

REQUIRED_PLUGINS = [
    CorePlugin,
    MessageRouterPlugin,
    LoggerPlugin
]


REQUIRED_CONTEXT = [
    dramatiq_workers_context
]

SERVER_CONTEXT = [
    redis_server_context
]

BACKEND_APPLICATION = MicrodropBackendApplication

FRONTEND_APPLICATION = MicrodropApplication

DEFAULT_APPLICATION = MicrodropApplication