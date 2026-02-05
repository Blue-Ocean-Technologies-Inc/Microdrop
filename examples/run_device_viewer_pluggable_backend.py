import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import *

def main():
    """Run only the backend plugins."""

    plugins = REQUIRED_PLUGINS + BACKEND_PLUGINS

    run_device_viewer_pluggable(plugins=plugins, contexts=REQUIRED_CONTEXT, application=BACKEND_APPLICATION, persist=True)


if __name__ == "__main__":
    main()
