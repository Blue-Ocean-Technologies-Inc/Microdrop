import sys
import os

from microdrop_utils.broker_server_helpers import dramatiq_workers_context

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from examples.run_device_viewer_pluggable import main as run_device_viewer_pluggable
from examples.plugin_consts import (REQUIRED_PLUGINS, FRONTEND_PLUGINS,
                                    FRONTEND_CONTEXT, REQUIRED_CONTEXT,
                                    FRONTEND_APPLICATION)

from logger.plugin import LoggerPlugin

def main():
    """Run only the frontend plugins."""
    plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS + [LoggerPlugin]
    contexts = [dramatiq_workers_context]
    run_device_viewer_pluggable(plugins=plugins, contexts=contexts,
                                application=FRONTEND_APPLICATION, persist=False)


if __name__ == "__main__":
    main()
