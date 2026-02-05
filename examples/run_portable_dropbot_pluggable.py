import sys
import os

from portable_dropbot_controller.plugin import PortDropbotControllerPlugin
from portable_dropbot_status.plugin import PortDropbotStatusPlugin

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import *


BACKEND_PLUGINS = [PortDropbotControllerPlugin]

FRONTEND_PLUGINS = [PortDropbotStatusPlugin]


def main():
    """Run only the backend plugins."""

    plugins = REQUIRED_PLUGINS + BACKEND_PLUGINS + FRONTEND_PLUGINS

    run_device_viewer_pluggable(
        plugins=plugins,
        contexts=REQUIRED_CONTEXT + SERVER_CONTEXT,
        application=DEFAULT_APPLICATION,
        persist=False,
    )


if __name__ == "__main__":
    main()
