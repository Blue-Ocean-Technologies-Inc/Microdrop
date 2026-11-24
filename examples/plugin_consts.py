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
from envisage.api import CorePlugin
from envisage.ui.tasks.api import TasksPlugin

# Microdrop package imports.
from app_updates.plugin import AppUpdatesPlugin
from device_viewer.plugin import DeviceViewerPlugin
from dropbot_controller.plugin import DropbotControllerPlugin
from dropbot_preferences_ui.plugin import DropbotPreferencesPlugin
from dropbot_protocol_controls.plugin import DropbotProtocolControlsPlugin
from dropbot_status_and_controls.plugin import DropbotStatusAndControlsPlugin
from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
from electrode_controller.plugin import ElectrodeControllerPlugin
from image_viewer import consts as image_viewer_consts
from layout_presets.plugin import LayoutPresetsPlugin
from logger_ui.plugin import LoggerUIPlugin
from message_router.plugin import MessageRouterPlugin
from microdrop_application.application import MicrodropApplication
from microdrop_application.backend_application import MicrodropBackendApplication
from microdrop_application.plugin import MicrodropPlugin
from microdrop_status_bar.plugin import StatusBarPlugin
from mock_dropbot_controller.plugin import MockDropbotControllerPlugin
from mock_dropbot_status.plugin import MockDropbotStatusPlugin
from notifications.plugin import NotificationsPlugin
from opendrop_controller.plugin import OpenDropControllerPlugin
from opendrop_status_and_controls.plugin import OpendropStatusAndControlsPlugin
from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin
from plugin_management.plugin import PluginManagementPlugin
from portable_dropbot_protocol_controls.plugin import (
    PortableDropbotProtocolControlsPlugin,
)
from portable_dropbot_self_tests.plugin import PortableDropbotSelfTestsPlugin
from portable_dropbot_status_and_controls.plugin import (
    PortableDropbotStatusAndControlsPlugin,
)
from protocol_quick_action_tools.plugin import ProtocolQuickActionToolsPlugin
from user_help_plugin import consts as user_help_consts
from video_protocol_controls.plugin import VideoProtocolControlsPlugin
from volume_threshold_protocol_controls.plugin import (
    VolumeThresholdProtocolControlsPlugin,
)
from zone_protocol_controls.plugin import ZoneProtocolControlsPlugin

# Microdrop utils imports.
from microdrop_utils.broker_server_helpers import (
    dramatiq_workers_context,
    load_dramatiq_worker_settings,
    redis_server_context,
)
from microdrop_utils.deferred_plugins import DeferredDockPane, DeferredPlugin

# Logger import.
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
    # Early, so its log handler and load-record watcher see what follows.
    NotificationsPlugin,
    LoggerUIPlugin,
    PluginManagementPlugin,
    AppUpdatesPlugin,
    DeviceViewerPlugin,
    LayoutPresetsPlugin,
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
    ZoneProtocolControlsPlugin,
]

# Frontend plugins started only after the main window has painted, one per
# event-loop turn, by plugin_management. Each is a "module:Class" spec, so its
# module is not imported before then, plus the dock panes it contributes,
# which show placeholders until it has loaded. Only plugins nothing else needs
# at start-up belong here: no protocol columns, quick actions, services or
# mixins a base plugin looks up in its start(), and no topic they must hear
# before the window is up (a message published before a listener exists is
# lost). Run scripts list them after SERVICE_PLUGINS, which load the same
# way, so the SSH UI never runs without the SSH service.
DEFERRED_FRONTEND_PLUGINS = [
    DeferredPlugin(
        spec="image_viewer.plugin:ImageViewerPlugin",
        dock_panes=[
            DeferredDockPane(
                id=image_viewer_consts.DOCK_PANE_ID,
                name=image_viewer_consts.DOCK_PANE_NAME,
            ),
            DeferredDockPane(
                id=image_viewer_consts.ROI_PLOT_DOCK_PANE_ID,
                name=image_viewer_consts.ROI_PLOT_DOCK_PANE_NAME,
            ),
        ],
    ),
    DeferredPlugin(
        spec="user_help_plugin.plugin:UserHelpPlugin",
        dock_panes=[
            DeferredDockPane(
                id=user_help_consts.TUTORIAL_SIMULATIONS_DOCK_PANE_ID,
                name=user_help_consts.TUTORIAL_SIMULATIONS_DOCK_PANE_NAME,
                dock_area="right",
            ),
        ],
    ),
    DeferredPlugin(spec="ssh_controls_ui.plugin:SSHUIPlugin"),
]

DROPBOT_FRONTEND_PLUGINS = [
    DropbotPreferencesPlugin,
    DropbotStatusAndControlsPlugin,
    DropbotToolsMenuPlugin,
]

OPENDROP_FRONTEND_PLUGINS = [OpendropStatusAndControlsPlugin]

PORTABLE_DROPBOT_FRONTEND_PLUGINS = [
    PortableDropbotStatusAndControlsPlugin,
    PortableDropbotSelfTestsPlugin,
    PortableDropbotProtocolControlsPlugin,
    # The status-bar battery icon is the built-in "rpi_battery_ui" plugin
    # group (plugin_management/consts.py), toggled in Manage Plugins — never
    # list it here, see the note in FRONTEND_PLUGINS.
]


BACKEND_PLUGINS = [
    ElectrodeControllerPlugin,
]

OPENDROP_BACKEND_PLUGINS = [
    OpenDropControllerPlugin,
]


def _lazy_load_portable_dropbot_plugins():
    from portable_dropbot_controller.plugin import PortableDropbotControllerPlugin

    return [PortableDropbotControllerPlugin]


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

# Host-bound-by-trust plugins. See the category comment above. Declared like
# the deferred frontend plugins: a GUI process starts them after its window
# has painted, a services-only process imports and starts them at once.
SERVICE_PLUGINS = [
    DeferredPlugin(spec="ssh_controls.plugin:SSHControlsPlugin"),
]

# A failure to start one of these, or of the application shell, fails the
# launch; any other plugin that fails is skipped. The essential set is
# MicrodropApplication.essential_plugin_ids (default
# microdrop_application.consts.ESSENTIAL_PLUGIN_IDS) — pass
# essential_plugin_ids= to the application to change it.
REQUIRED_PLUGINS = [CorePlugin, MessageRouterPlugin, LoggerPlugin]

# Worker kwargs come from redis_settings.json when present (e.g. written by
# the standalone launcher's Server Settings tab), else 4 threads / 100 ms.
REQUIRED_CONTEXT = [(dramatiq_workers_context, load_dramatiq_worker_settings())]

SERVER_CONTEXT = [(redis_server_context, {})]

BACKEND_APPLICATION = MicrodropBackendApplication

FRONTEND_APPLICATION = MicrodropApplication

DEFAULT_APPLICATION = MicrodropApplication


def with_updates_panel(plugins):
    """Return a copy of ``plugins`` with ``AppUpdatesPlugin`` added when they
    load the frontend shell (``MicrodropPlugin``) without it — right after
    ``PluginManagementPlugin`` when that is loaded, else at the end.

    A launcher's saved plugin selection can predate the Updates panel; such a
    frontend would follow the default update policy with no way to see or
    change it.
    """
    plugins = list(plugins)

    if MicrodropPlugin not in plugins or AppUpdatesPlugin in plugins:
        return plugins

    if PluginManagementPlugin in plugins:
        position = plugins.index(PluginManagementPlugin) + 1
    else:
        position = len(plugins)

    plugins.insert(position, AppUpdatesPlugin)

    return plugins
