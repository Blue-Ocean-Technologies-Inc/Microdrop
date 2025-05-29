import os
import sys
import contextlib
import signal
import time

from envisage.ui.tasks.tasks_application import TasksApplication

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from examples.plugin_consts import *
from microdrop_utils._logger import get_logger
logger = get_logger(__name__)

def main(args, plugins=None, contexts=None, application=None, persist=False):
    """Run the application."""

    if plugins is None:
        plugins = REQUIRED_PLUGINS + FRONTEND_PLUGINS + BACKEND_PLUGINS
    if contexts is None:
        contexts = FRONTEND_CONTEXT + BACKEND_CONTEXT + REQUIRED_CONTEXT
    if application is None:
        application = DEFAULT_APPLICATION


    logger.debug(f"Instantiating application {application} with plugins {plugins}")

    # Instantiate plugins
    plugin_instances = [plugin() for plugin in plugins]

    # Instantiate application
    app = application(plugins=plugin_instances)

    def stop_app(signum, frame):
        print("Shutting down...")
        if isinstance(app, TasksApplication): # It's a UI application, so we call exit so that the application can save its state via TasksApplication.exit()
            app.exit()
        else: # It's a backend application, so we call Application.stop() since exit() doesn't exist
            app.stop()
        exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, stop_app)
    signal.signal(signal.SIGTERM, stop_app)

    with contextlib.ExitStack() as stack: # contextlib.ExitStack is a context manager that allows you to stack multiple context managers
        for context in contexts:
            stack.enter_context(context())
        app.run()
        if persist:
            while True:
                time.sleep(0.001)


if __name__ == "__main__":
    main(sys.argv)