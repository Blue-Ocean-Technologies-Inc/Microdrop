import sys
import os


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import *

from logger.plugin import LoggerPlugin
from dropbot_preferences_ui.plugin import DropbotPreferencesPlugin

FRONTEND_PLUGINS = [
    TasksPlugin,
    MicrodropPlugin,
    # DropbotStatusPlotPlugin,
    DropbotToolsMenuPlugin,
    DropbotStatusPlugin,
    ManualControlsPlugin,
    ProtocolGridControllerUIPlugin,
    DeviceViewerPlugin,
    PeripheralUiPlugin
]

def main():
    """Run only the frontend plugins."""
    plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS + [LoggerPlugin, DropbotPreferencesPlugin]
    contexts = [dramatiq_workers_context]
    run_device_viewer_pluggable(plugins=plugins, contexts=contexts,
                                application=FRONTEND_APPLICATION, persist=False)


if __name__ == "__main__":
    main()
