"""Relaunch the running app into the microdrop-plugins pixi environment so a
just-installed plugin's freshly-added dependencies become importable.

A live interpreter can't safely import packages added to a *different* pixi
environment mid-run, so we re-exec the same entry point under
``pixi run -e microdrop-plugins``.
"""

import os
import sys
from pathlib import Path

from logger.logger_service import get_logger

#: The pixi workspace root (microdrop-py/, parent of src/) — has pyproject.toml.
WORKSPACE_DIR = Path(__file__).resolve().parents[2]

PLUGINS_ENV = "microdrop-plugins"

logger = get_logger(__name__)


def _relaunch_argv(script: str):
    """`pixi run -e <env> python <script> <args...>` for the current process.

    ``script`` must already be an absolute path (resolved before any chdir).
    ``sys.argv[1:]`` (the original arguments after the script name) are
    forwarded verbatim so the restarted process receives the same flags.
    """
    return [
        "pixi", "run", "-e", PLUGINS_ENV,
        "python", script, *sys.argv[1:],
    ]


def relaunch_into_plugins_env(application=None):
    """Quit the app (if given) and re-exec into the plugins env. Best-effort:
    on failure, logs and returns so the caller can fall back to a message.

    The entry script is resolved to an ABSOLUTE path against the current
    working directory BEFORE any ``os.chdir``.  If the resolved path does not
    exist the function logs an error and returns WITHOUT touching the
    application, leaving it running (graceful degradation).
    """
    try:
        # Resolve the entry script while the original cwd is still intact.
        script = os.path.abspath(sys.argv[0])
        if not os.path.exists(script):
            logger.error(
                f"relaunch: entry script not found at '{script}'; "
                "aborting relaunch to keep the app alive"
            )
            return

        argv = _relaunch_argv(script)
        logger.info(f"relaunching into {PLUGINS_ENV}: {' '.join(argv)}")

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
