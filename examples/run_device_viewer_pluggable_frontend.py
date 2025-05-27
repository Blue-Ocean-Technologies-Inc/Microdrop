import os
import sys
from envisage.api import CorePlugin
from envisage.ui.tasks.api import TasksPlugin



sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from microdrop_utils.broker_server_helpers import dramatiq_workers_context


def main(args):
    """Run the application."""

    from device_viewer.application import DeviceViewerApplication
    from device_viewer.plugin import DeviceViewerPlugin
    from dropbot_status.plugin import DropbotStatusPlugin
    from message_router.plugin import MessageRouterPlugin
    from manual_controls.plugin import ManualControlsPlugin
    from dropbot_tools_menu.plugin import DropbotToolsMenuPlugin
    from dropbot_status_plot.plugin import DropbotStatusPlotPlugin


    plugins = [
        CorePlugin(),
        TasksPlugin(),
        DeviceViewerPlugin(),
        DropbotStatusPlugin(),
        MessageRouterPlugin(),
        ManualControlsPlugin(),
        DropbotToolsMenuPlugin(),
        DropbotStatusPlotPlugin()
    ]

    app = DeviceViewerApplication(plugins=plugins)

    # # Need to run with a dramatiq broker context since app requires plugins that use dramatiq
    with dramatiq_workers_context():
        app.run()


if __name__ == "__main__":
    main(sys.argv)