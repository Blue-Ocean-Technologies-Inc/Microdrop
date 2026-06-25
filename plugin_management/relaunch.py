"""Relaunch the running app into the microdrop-plugins pixi environment so a
just-installed plugin's freshly-added dependencies become importable.

A live interpreter can't safely import packages added to a *different* pixi
environment mid-run, so we re-exec the same entry point under
``pixi run -e microdrop-plugins``.
"""

import os
import sys

from plugin_management.pixi_env import PLUGINS_ENV, WORKSPACE_DIR
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _relaunch_argv():
    """`pixi run -e <env> python <script> <args...>` for the current process."""
    return [
        "pixi", "run", "-e", PLUGINS_ENV,
        "python", *sys.argv,
    ]


def relaunch_into_plugins_env(application=None):
    """Quit the app (if given) and re-exec into the plugins env. Best-effort:
    on failure, logs and returns so the caller can fall back to a message."""
    argv = _relaunch_argv()
    logger.info(f"relaunching into {PLUGINS_ENV}: {' '.join(argv)}")
    try:
        # Ask the envisage app to exit cleanly first (saves window state).
        if application is not None:
            try:
                application.exit()
            except Exception:
                logger.exception("relaunch: application.exit() failed; continuing")
        # Replace this process. os.chdir so pixi finds the workspace manifest.
        os.chdir(str(WORKSPACE_DIR))
        os.execvp(argv[0], argv)
    except Exception:
        logger.exception("relaunch into plugins env failed")
