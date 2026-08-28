# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import contextlib
import os
import signal
import sys
import time
from functools import partial

from envisage.ui.tasks.tasks_application import TasksApplication
from pyface.qt.QtWidgets import QApplication

from microdrop_utils.app_setup_helpers import microdrop_runner_setup

microdrop_runner_setup()

from examples.plugin_consts import (  # noqa: E402
    BACKEND_APPLICATION,
    BACKEND_PLUGINS,
    DROPBOT_BACKEND_PLUGINS,
    DROPBOT_FRONTEND_PLUGINS,
    FRONTEND_APPLICATION,
    FRONTEND_PLUGINS,
    MOCK_DROPBOT_BACKEND_PLUGINS,
    MOCK_DROPBOT_FRONTEND_PLUGINS,
    OPENDROP_BACKEND_PLUGINS,
    OPENDROP_FRONTEND_PLUGINS,
    PORTABLE_DROPBOT_BACKEND_PLUGINS,
    PORTABLE_DROPBOT_FRONTEND_PLUGINS,
    REQUIRED_CONTEXT,
    REQUIRED_PLUGINS,
    SERVER_CONTEXT,
    SERVICE_PLUGINS,
)

from logger.logger_service import get_logger  # noqa: E402

logger = get_logger(__name__)

from microdrop_style.helpers import style_app  # noqa: E402

from microdrop_utils.system_config import is_rpi  # noqa: E402

# Set environment variables for Qt for pi
if is_rpi():
    os.environ["QT_MEDIA_BACKEND"] = "gstreamer"
    print("Detected Raspberry Pi. Setting QT_MEDIA_BACKEND to gstreamer")


def stop_app(app, signum, frame):
    print("Shutting down...")
    # A UI application exits, so that TasksApplication.exit() can save its
    # state; a backend application has no exit(), so it stops.
    if isinstance(app, TasksApplication):
        app.exit()
    else:
        app.stop()
    sys.exit(0)


def main(plugins, contexts, application, persist):
    """
    Run the application.

    **Note**
    The order of plugins matters. This determines whose start routine will be
    run first, and whose contributions will be prioritized. For example: the
    microdrop plugin and the tasks contributes a preferences dialog service.
    The dialog contributed by the plugin listed first will be used. That is
    how the envisage application get_service method works.

    """

    app_instance = QApplication.instance() or QApplication(sys.argv)

    style_app(app_instance)

    print(f"Instantiating application {application} with plugins {plugins}")

    # Instantiate plugins
    plugin_instances = [plugin() for plugin in plugins]

    #### Startup application with context

    # contextlib.ExitStack is a context manager that allows you to stack
    # multiple context managers.
    with contextlib.ExitStack() as stack:
        for context, kwargs in contexts:
            stack.enter_context(context(**kwargs))

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
    # Required before anything spawns a process on Windows,
    # and a no-op elsewhere.
    import multiprocessing

    multiprocessing.freeze_support()

    import argparse

    parser = argparse.ArgumentParser(description="Run the device viewer plugins.")

    parser.add_argument(
        "--device",
        type=str,
        choices=["dropbot", "opendrop", "portable", "mock"],
        default="dropbot",  # Sets a default if the user doesn't provide the flag
        help="Specify the device to use: 'dropbot', 'opendrop' or 'portable'",
    )

    parser.add_argument(
        "--plugins",
        nargs="+",
        choices=["frontend", "backend", "services"],
        default=["frontend", "backend"],
        help="Which plugin layers to load (space-separated). 'frontend' also pulls in "
        "the colocated service plugins. Default: frontend backend.",
    )

    args = parser.parse_args()
    selected = set(args.plugins)

    plugins = list(REQUIRED_PLUGINS)

    if "frontend" in selected:
        plugins += FRONTEND_PLUGINS
        if args.device == "dropbot":
            plugins += DROPBOT_FRONTEND_PLUGINS
        elif args.device == "opendrop":
            plugins += OPENDROP_FRONTEND_PLUGINS
        elif args.device == "portable":
            plugins += PORTABLE_DROPBOT_FRONTEND_PLUGINS
        elif args.device == "mock":
            plugins += MOCK_DROPBOT_FRONTEND_PLUGINS + DROPBOT_FRONTEND_PLUGINS

    # Service plugins are host-bound by trust and must colocate with the GUI,
    # so they load alongside the frontend as well as on explicit request.
    if "frontend" in selected or "services" in selected:
        plugins += SERVICE_PLUGINS

    if "backend" in selected:
        plugins += BACKEND_PLUGINS
        if args.device == "dropbot":
            plugins += DROPBOT_BACKEND_PLUGINS
        elif args.device == "opendrop":
            plugins += OPENDROP_BACKEND_PLUGINS
        elif args.device == "portable":
            plugins += PORTABLE_DROPBOT_BACKEND_PLUGINS
        elif args.device == "mock":
            plugins += MOCK_DROPBOT_BACKEND_PLUGINS

    # De-duplicate while preserving load order (matters for service priority).
    plugins = list(dict.fromkeys(plugins))

    # A GUI process when the frontend is loaded; otherwise a persistent
    # headless backend process.
    has_frontend = "frontend" in selected

    # The frontend host owns the Redis server; a backend-only process is
    # assumed to be remote and connects to an already-running Redis.
    contexts = (SERVER_CONTEXT + REQUIRED_CONTEXT) if has_frontend else REQUIRED_CONTEXT

    main(
        plugins=plugins,
        contexts=contexts,
        application=FRONTEND_APPLICATION if has_frontend else BACKEND_APPLICATION,
        persist=not has_frontend,
    )
