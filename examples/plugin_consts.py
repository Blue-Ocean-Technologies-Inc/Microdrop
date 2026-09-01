# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from envisage.api import CorePlugin
from envisage.ui.tasks.api import TasksPlugin

from device_viewer.plugin import DeviceViewerPlugin
from dropbot_controller.plugin import DropbotControllerPlugin
from dropbot_preferences_ui.plugin import DropbotPreferencesPlugin
from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
from dropbot_status_and_controls.plugin import DropbotStatusAndControlsPlugin
from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
from electrode_controller.plugin import ElectrodeControllerPlugin
from logger_ui.plugin import LoggerUIPlugin
from message_router.plugin import MessageRouterPlugin
from microdrop_application.application import MicrodropApplication
from microdrop_application.backend_application import MicrodropBackendApplication
from microdrop_application.plugin import MicrodropPlugin
from microdrop_status_bar.plugin import StatusBarPlugin
from mock_dropbot_controller.plugin import MockDropbotControllerPlugin
from mock_dropbot_status.plugin import MockDropbotStatusPlugin
from opendrop_controller.plugin import OpenDropControllerPlugin
from opendrop_status_and_controls.plugin import OpendropStatusAndControlsPlugin
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from plugin_management.plugin import PluginManagementPlugin
from portable_dropbot_controller.plugin import PortableDropbotControllerPlugin
from portable_dropbot_protocol_controls.plugin import (
    PortableDropbotProtocolControlsPlugin,
)
from portable_dropbot_status_and_controls.plugin import (
    PortableDropbotStatusAndControlsPlugin,
)
from protocol_quick_action_tools.plugin import ProtocolQuickActionToolsPlugin
from ssh_controls.plugin import SSHControlsPlugin
from ssh_controls_ui.plugin import SSHUIPlugin
from user_help_plugin.plugin import UserHelpPlugin
from video_protocol_controls.plugin import VideoProtocolControlsPlugin
from volume_threshold_protocol_controls.plugin import (
    VolumeThresholdProtocolControlsPlugin,
)

from microdrop_utils.broker_server_helpers import (
    dramatiq_workers_context,
    load_dramatiq_worker_settings,
    redis_server_context,
)

from logger.plugin import LoggerPlugin

# The order of plugins matters. This determines whose start routine will be run
# first, and whose contributions will be prioritized.
# For example: the microdrop plugin and the tasks plugin both contribute a
# preferences dialog service. The dialog contributed by the plugin listed first
# will be used. That is how the envisage application get_service method works.

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
    StatusBarPlugin,
    LoggerUIPlugin,
    PluginManagementPlugin,
    DeviceViewerPlugin,
    UserHelpPlugin,
    SSHUIPlugin,
    PluggableProtocolTreePlugin,
    DropbotProtocolControlsPlugin,
    # The Z-Stage/magnet and heater stacks are standalone installable plugin
    # packages now (magnet-microdrop-plugin, heater-microdrop-plugin): their
    # groups are discovered from the installed packages' manifests and
    # enabled by the plugin-group manager at application_initialized / via
    # Tools > Manage Plugins — never listed here (double-loading a plugin
    # duplicates its service offers and panes). The protocol tree hot-swaps
    # their protocol columns when PROTOCOL_COLUMNS contributions change.
    ProtocolQuickActionToolsPlugin,
    VolumeThresholdProtocolControlsPlugin,
    VideoProtocolControlsPlugin,
]

DROPBOT_FRONTEND_PLUGINS = [
    DropbotPreferencesPlugin,
    DropbotStatusAndControlsPlugin,
    DropbotToolsMenuPlugin,
]

OPENDROP_FRONTEND_PLUGINS = [OpendropStatusAndControlsPlugin]

PORTABLE_DROPBOT_FRONTEND_PLUGINS = [
    PortableDropbotStatusAndControlsPlugin,
    PortableDropbotProtocolControlsPlugin,
]


BACKEND_PLUGINS = [
    ElectrodeControllerPlugin,
]

OPENDROP_BACKEND_PLUGINS = [
    OpenDropControllerPlugin,
]

PORTABLE_DROPBOT_BACKEND_PLUGINS = [
    PortableDropbotControllerPlugin,
]

DROPBOT_BACKEND_PLUGINS = [
    # PeripheralControllerPlugin / HeaterControllerPlugin are group-managed —
    # see the note in FRONTEND_PLUGINS.
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

REQUIRED_PLUGINS = [CorePlugin, MessageRouterPlugin, LoggerPlugin]

# Worker kwargs come from redis_settings.json when present (e.g. written by
# the standalone launcher's Server Settings tab), else 4 threads / 100 ms.
REQUIRED_CONTEXT = [(dramatiq_workers_context, load_dramatiq_worker_settings())]

SERVER_CONTEXT = [(redis_server_context, {})]

BACKEND_APPLICATION = MicrodropBackendApplication

FRONTEND_APPLICATION = MicrodropApplication

DEFAULT_APPLICATION = MicrodropApplication
