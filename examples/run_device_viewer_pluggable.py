import contextlib
import os
import sys
import signal
import time
from functools import partial

# import platform
# Set environment variables for Qt scaling for low DPI displays i.e, Raspberry Pi 4
# if "pi" in platform.uname().node.lower():
#         os.environ["QT_SCALE_FACTOR"] = "0.7"
#         print(f"running with environment variables: {os.environ['QT_SCALE_FACTOR']}")

from envisage.ui.tasks.tasks_application import TasksApplication
from PySide6.QtWidgets import QApplication

from microdrop_style.helpers import style_app

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from logger.logger_service import get_logger
from microdrop_utils.root_dir_utils import get_project_root
root = get_project_root()

os.environ["PATH"] = str(root) + os.pathsep + os.environ.get("PATH", "") # Add root to PATH for PyInstaller. Should do nothing normal operation

logger = get_logger(__name__)


def stop_app(app, signum, frame):
    print("Shutting down...")
    if isinstance(app,
                  TasksApplication):  # It's a UI application, so we call exit so that the application can save its state via TasksApplication.exit()
        app.exit()
    else:  # It's a backend application, so we call Application.stop() since exit() doesn't exist
        app.stop()
    sys.exit(0)


def main(plugins, contexts, application, persist):
    """Run the application."""

    app_instance = QApplication.instance() or QApplication(sys.argv)

    style_app(app_instance)

    logger.debug(f"Instantiating application {application} with plugins {plugins}")

    # Instantiate plugins
    plugin_instances = [plugin() for plugin in plugins]

    #### Startup application with context

    with contextlib.ExitStack() as stack:  # contextlib.ExitStack is a context manager that allows you to stack multiple context managers
        for context in contexts:
            stack.enter_context(context())

        # Instantiate application
        app = application(plugins=plugin_instances)

        # Register signal handlers
        stop_app_func = partial(stop_app, app)
        signal.signal(signal.SIGINT, stop_app_func)
        signal.signal(signal.SIGTERM, stop_app_func)

        app.run()

        if persist:
            while True:
                time.sleep(0.001)


if __name__ == "__main__":
    from plugin_consts import REQUIRED_PLUGINS, FRONTEND_PLUGINS, BACKEND_PLUGINS, REQUIRED_CONTEXT, SERVER_CONTEXT, DEFAULT_APPLICATION

    main(
        plugins=REQUIRED_PLUGINS + FRONTEND_PLUGINS + BACKEND_PLUGINS,
        contexts=SERVER_CONTEXT + REQUIRED_CONTEXT,
        application=DEFAULT_APPLICATION,
        persist=False # UI so no
         )
