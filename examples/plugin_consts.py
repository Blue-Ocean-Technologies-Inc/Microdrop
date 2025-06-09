from envisage.application import Application
from microdrop_application.application import MicrodropApplication
from microdrop_application.plugin import MicrodropPlugin
from dropbot_status_plot.plugin import DropbotStatusPlotPlugin
from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
from dropbot_status.plugin import DropbotStatusPlugin
from manual_controls.plugin import ManualControlsPlugin
from protocol_grid.plugin import ProtocolGridControllerUIPlugin
from BlankMicrodropCanvas.application import MicrodropCanvasTaskApplication
from dropbot_controller.plugin import DropbotControllerPlugin
from electrode_controller.plugin import ElectrodeControllerPlugin
from envisage.api import CorePlugin
from envisage.ui.tasks.api import TasksPlugin
from message_router.plugin import MessageRouterPlugin
from microdrop_utils.broker_server_helpers import dramatiq_workers_context, redis_server_context

FRONTEND_PLUGINS = [
    TasksPlugin,
    MicrodropPlugin,
    DropbotStatusPlotPlugin,
    DropbotToolsMenuPlugin,
    DropbotStatusPlugin,
    ManualControlsPlugin,
    ProtocolGridControllerUIPlugin
]

BACKEND_PLUGINS = [
    DropbotControllerPlugin,
    ElectrodeControllerPlugin,
]

REQUIRED_PLUGINS = [
    CorePlugin,
    MessageRouterPlugin,
]


REQUIRED_CONTEXT = [
    dramatiq_workers_context
]

BACKEND_CONTEXT = [
    redis_server_context
]

FRONTEND_CONTEXT = [
]

BACKEND_APPLICATION = Application

FRONTEND_APPLICATION = MicrodropApplication

DEFAULT_APPLICATION = MicrodropApplication