"""Relaunch the running app into the default pixi environment so a
just-installed plugin's freshly-added dependencies become importable.

A live interpreter can't safely import packages added mid-run, so we re-exec
the same entry point under ``pixi run`` (the default environment).
"""

import os
from pathlib import Path

from microdrop_application.dialogs.pyface_wrapper import confirm, information, YES
from logger.logger_service import get_logger

#: The pixi workspace root (microdrop-py/, parent of src/) — has pyproject.toml.
WORKSPACE_DIR = Path(__file__).resolve().parents[2]

logger = get_logger(__name__)


def confirm_and_relaunch(task, msg_html):
    """Offer to relaunch now (applies the change) or later. Shared by the
    Manage-Plugins and Browse-Plugins controllers. Degrades gracefully when
    there is no running application (e.g. the standalone installer demo, where
    ``task`` is None): it just reports that the change applies next launch."""
    application = getattr(getattr(task, "window", None), "application", None)
    if application is not None and confirm(
            parent=None, title="Relaunch required",
            message=f"{msg_html}<br><br>Relaunch MicroDrop now to apply?",
            cancel=False) == YES:
        relaunch_app(application)
        return
    information(parent=None, title="Relaunch later",
                message="The change takes effect the next time you launch "
                        "MicroDrop.")


def relaunch_app(application=None):
    """Quit the app (if given) and re-exec into the default pixi environment by
    running the ``microdrop`` task. Best-effort: on failure, logs and returns so
    the caller can fall back to a message.

    ``--manifest-path`` points pixi at the workspace ``pyproject.toml`` so the
    task resolves regardless of the current working directory.
    """
    try:
        argv = [
            "pixi", "run",
            "--manifest-path", str(WORKSPACE_DIR / "pyproject.toml"),
            "microdrop",
        ]
        logger.info(f"relaunching into default env: {' '.join(argv)}")

        # Ask the envisage app to exit cleanly first (saves window state).
        if application is not None:
            try:
                application.exit()
            except Exception:
                logger.exception("relaunch: application.exit() failed; continuing")

        # Replace this process with the pixi task.
        os.execvp(argv[0], argv)
    except Exception:
        logger.exception("relaunch into default env failed")
