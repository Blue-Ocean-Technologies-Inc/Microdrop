import sys
import os

from ssh_controls_ui.plugin import SSHUIPlugin

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import REQUIRED_PLUGINS, FRONTEND_PLUGINS, REQUIRED_CONTEXT, FRONTEND_APPLICATION

def main():
    """Run only the frontend plugins."""

    plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS

    run_device_viewer_pluggable(plugins=plugins, contexts=REQUIRED_CONTEXT,
                                application=FRONTEND_APPLICATION, persist=False)


if __name__ == "__main__":
    main()
