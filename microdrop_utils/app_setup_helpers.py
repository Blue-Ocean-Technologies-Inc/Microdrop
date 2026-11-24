# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import sys

# Microdrop utils imports.
from microdrop_utils.broker_server_helpers import configure_dramatiq_broker
from microdrop_utils.source_update_startup import (
    PROJECT_ROOT,
    apply_source_update_policy,
)
from microdrop_utils.web_engine_guard import block_web_engine_views_on_linux

# Logger import.
from logger.logger_service import get_logger, init_logger

logger = get_logger(__name__)


def _open_startup_splash_screen():
    """Open the MicroDrop splash and paint it."""
    # Imported here: it creates the QApplication, which must come after the
    # QtWebEngine block.
    from microdrop_utils.splash_screen import MicrodropSplashScreen

    splash_screen = MicrodropSplashScreen()
    splash_screen.open()

    return splash_screen


def microdrop_runner_setup(show_splash_screen=False):
    """
    Common setup for all MicroDrop runner scripts.

    Configures the Dramatiq broker from redis_settings.json, adds the project
    root to sys.path so submodules are importable, keeps QtWebEngine views
    out of the process on Linux (see :mod:`microdrop_utils.web_engine_guard`),
    then logs the source version and applies the auto-update preference (see
    :func:`~microdrop_utils.source_update_startup.apply_source_update_policy`).
    When that moves the checkout to a newer release, it re-runs this command
    on the new version and exits with its exit code, so this call does not
    return. A development checkout is never moved. Optionally it then opens
    the splash screen, before the caller imports any plugin module.

    Must be called before importing any modules that use dramatiq.get_broker().

    Parameters
    ----------
    show_splash_screen : bool
        Open the splash after the update step, for a process that goes on to
        run the GUI application.

    Returns
    -------
    MicrodropSplashScreen or None
        The open splash, for the GUI application to take over as its
        ``splash_screen``; None unless ``show_splash_screen`` is set.
    """
    configure_dramatiq_broker()

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    # Handlers only attach when the LoggerPlugin starts, and a handler-less
    # root logger silently drops INFO records — without this, the version
    # line below never reaches the console. The plugin's later init_logger()
    # clears these handlers first, so nothing is duplicated.
    init_logger()

    # Before any plugin or TraitsUI editor can import QtWebEngine.
    block_web_engine_views_on_linux()

    apply_source_update_policy()

    # Only after the update step: on Windows a moved checkout re-runs the app
    # in a child while this process waits, and a splash opened earlier would
    # stay on top of the relaunched app. Also after init_logger(), which
    # would drop the splash's log handler.
    if show_splash_screen:
        return _open_startup_splash_screen()

    return None
