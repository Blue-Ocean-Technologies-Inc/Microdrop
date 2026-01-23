import contextlib
import os
import sys
import signal
import time
from functools import partial

from microdrop_utils.system_config import is_rpi
# Set environment variables for Qt for pi
if is_rpi():
    os.environ["QT_MEDIA_BACKEND"] = "gstreamer"

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
    """
    Run the application.

    **Note**
    The order of plugins matters. This determines whose start routine will be run first, and whose contributions will be prioritized
    For example: the microdrop plugin and the tasks contributes a preferences dialog service.
    The dialog contributed by the plugin listed first will be used. That is how the envisage application get_service
    method works.

    """

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
