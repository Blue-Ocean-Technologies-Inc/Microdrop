# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Run the real app shell without touching the user's MicroDrop.

* A private Redis on a free port (never 6379, where a live session may
  run), started here and stopped on exit, with the Dramatiq broker pointed
  at it before any plugin module asks for the broker.
* A throw-away application home and user-data folder (preferences, saved
  layout, Experiments, logs), deleted on exit.

Enter ``isolated_session()`` before importing any MicroDrop plugin module.
"""

# Standard library imports.
import logging
import shutil
import socket
import tempfile
from contextlib import contextmanager
from pathlib import Path

# Enthought library imports.
from traits.etsconfig.api import ETSConfig

# Microdrop utils imports.
from microdrop_utils import application_home
from microdrop_utils.broker_server_helpers import (
    configure_dramatiq_broker,
    start_redis_server,
    stop_redis_server,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The live app's Redis port: never used here.
LIVE_REDIS_PORT = 6379

PRIVATE_REDIS_HOST = "127.0.0.1"

#: Seconds to wait for the private Redis to listen.
REDIS_START_TIMEOUT_S = 5.0

HOME_PREFIX = "microdrop_notifications_ux_"


def free_port(host=PRIVATE_REDIS_HOST):
    """A TCP port nothing listens on now, other than the live app's."""

    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
            port = probe.getsockname()[1]

        if port != LIVE_REDIS_PORT:
            return port


def use_application_home(root, theme):
    """Point the app's home and user data at ``root`` (also for every later
    ``configure_application_home()`` call), with ``theme`` preset."""
    home = root / "Microdrop"
    user_data = root / "Documents"

    def configure_demo_home():
        ETSConfig.company = "Sci-Bots"
        ETSConfig.user_data = str(user_data)
        ETSConfig.application_home = str(home)

    application_home.configure_application_home = configure_demo_home
    configure_demo_home()

    home.mkdir(parents=True, exist_ok=True)
    (home / application_home.PREFERENCES_FILENAME).write_text(
        f"[microdrop.app]\ncolor_scheme = {theme}\n", encoding="utf-8"
    )


@contextmanager
def isolated_session(theme="follow_system"):
    """A private Redis and a temporary home for the demo; yields the home's
    root folder."""
    root = Path(tempfile.mkdtemp(prefix=HOME_PREFIX))
    port = free_port()
    process = None

    use_application_home(root, theme)
    logger.info(f"Notifications UX demo: home {root}, private Redis on port {port}")

    try:
        process = start_redis_server(
            timeout=REDIS_START_TIMEOUT_S, host=PRIVATE_REDIS_HOST, port=port
        )

        # None: something else already listens there; never share it.
        if process is None or process.poll() is not None:
            raise RuntimeError(f"Could not start a private Redis on port {port}")

        configure_dramatiq_broker(host=PRIVATE_REDIS_HOST, port=port)

        yield root

    finally:
        stop_redis_server(process)
        _close_log_files()
        shutil.rmtree(root, ignore_errors=True)


def _close_log_files():
    """Let go of the session's log file, so its folder can be deleted."""
    root_logger = logging.getLogger()

    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.FileHandler):
            handler.close()
            root_logger.removeHandler(handler)
