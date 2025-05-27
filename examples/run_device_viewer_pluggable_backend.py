import sys
import os
import signal
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import *


def main(args):
    """Run the application."""
    plugins = REQUIRED_PLUGINS + BACKEND_PLUGINS
    contexts = BACKEND_CONTEXT + REQUIRED_CONTEXT
    
    run_device_viewer_pluggable(args, plugins=plugins, contexts=contexts, application=BACKEND_APPLICATION, persist=True)


if __name__ == "__main__":
    main(sys.argv)
