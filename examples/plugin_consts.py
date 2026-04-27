import os

from dropbot_preferences_ui.plugin import DropbotPreferencesPlugin
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
from ssh_controls.plugin import SSHControlsPlugin
from ssh_controls_ui.plugin import SSHUIPlugin
from user_help_plugin.plugin import UserHelpPlugin

# The order of plugins matters. This determines whose start routine will be run first,
# and whose contributions will be prioritized
# For example: the microdrop plugin and the tasks contributes a preferences dialog service.
# The dialog contributed by the plugin listed first will be used. That is how the envisage application get_service
# method works.

# ---------------------------------------------------------------------------
# Plugin categories
# ---------------------------------------------------------------------------
# There are three categories:
#
#   FRONTEND_PLUGINS — Qt/Pyface UI plugins. Must run in the GUI process.
#   BACKEND_PLUGINS  — Plugins that talk to physical hardware (DropBot,
#                      OpenDrop, peripherals). Must run on the host wired
#                      to the device.
#   SERVICE_PLUGINS  — Dramatiq-worker plugins that are host-bound by
#                      user-trust context (credentials, private keys,
#                      local filesystem), not by hardware or UI. These
#                      must colocate with the GUI process, not with the
#                      remote backend.
#
# A service plugin (e.g., ssh_controls) has no UI and no hardware
# dependency — but shipping it to the remote backend host would either
# fail (no SSH keys there) or invert the rsync direction and force the
# backend to push files into the frontend, which we explicitly reject.
# Keep service plugins in this list and include it in the plugin sets
# for any run script that launches the GUI.
# ---------------------------------------------------------------------------

FRONTEND_PLUGINS = [
    MicrodropPlugin,
    TasksPlugin,
    LoggerUIPlugin,
    ProtocolGridControllerUIPlugin,
    DeviceViewerPlugin,
    PeripheralUiPlugin,
    UserHelpPlugin,
    SSHUIPlugin,
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

# Host-bound-by-trust plugins. See the category comment above.
SERVICE_PLUGINS = [
    SSHControlsPlugin,
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
