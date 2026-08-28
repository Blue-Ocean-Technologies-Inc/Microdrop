# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Process-level half of Display Scale: put the persisted scale into
the environment before Qt starts, and relaunch the runner when the
user picks a different one.

Qt samples ``QT_SCALE_FACTOR`` once, inside the QGuiApplication
constructor, and offers nothing to change the device pixel ratio
afterwards — so the scale has to be read here, ahead of every Qt
import that matters, and a new choice only lands on the next process.

Deliberately free of Qt, envisage and dramatiq imports: this module is
called before any of them are set up.
"""

# Standard library imports.
import os
import subprocess
import sys
from pathlib import Path

# Enthought library imports.
from apptools.preferences.api import Preferences
from traits.etsconfig.api import ETSConfig

# Local imports.
from .consts import (
    PREFERENCES_FILENAME,
    SCALE_DEFAULT_PERCENT,
    SCALE_ENV_VAR,
    SCALE_MAX_PERCENT,
    SCALE_MIN_PERCENT,
    SCALE_PREFERENCE_NAME,
    SCALE_PREFERENCES_NODE,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Set by the Display Scale dialog and read back by the runner once the
#: application has stopped and its contexts (Redis, dramatiq workers)
#: have been torn down — relaunching any earlier would leave the new
#: process fighting the old one for the broker.
_relaunch_requested = False


def preferences_path():
    """Return the path of the application's persisted preferences file."""
    # Importing the application module is what points ETSConfig at
    # Sci-Bots/Microdrop; every runner imports it moments later anyway.
    import microdrop_application.application  # noqa: F401

    return Path(ETSConfig.application_home) / PREFERENCES_FILENAME


def read_scale_percent():
    """Return the persisted interface scale, clamped to the slider range.

    Falls back to 100% for a first run, an unreadable preferences file,
    or a value someone hand-edited out of range.
    """
    path = preferences_path()
    if not path.exists():
        return SCALE_DEFAULT_PERCENT

    try:
        preferences = Preferences()
        preferences.load(str(path))
        raw = preferences.get(f"{SCALE_PREFERENCES_NODE}.{SCALE_PREFERENCE_NAME}")
    except Exception as e:
        logger.warning(f"Could not read {path}: {e}")
        return SCALE_DEFAULT_PERCENT

    if raw is None:
        # Never set — the overwhelmingly common case, not a problem.
        return SCALE_DEFAULT_PERCENT

    try:
        percent = int(float(raw))
    except (TypeError, ValueError):
        logger.warning(f"Ignoring unreadable interface scale {raw!r} in {path}")
        return SCALE_DEFAULT_PERCENT

    return max(SCALE_MIN_PERCENT, min(SCALE_MAX_PERCENT, percent))


def active_scale_percent():
    """Return the scale this process actually started at."""
    try:
        return round(float(os.environ[SCALE_ENV_VAR]) * 100)
    except (KeyError, ValueError):
        return SCALE_DEFAULT_PERCENT


def apply_scale_from_preferences():
    """Export the persisted scale as ``QT_SCALE_FACTOR``.

    Must run before the QApplication is constructed. A scale set in the
    environment by hand keeps precedence while the preference is still
    at its default, so ``QT_SCALE_FACTOR=0.75 pixi run ...`` remains a
    working one-off override.
    """
    percent = read_scale_percent()
    if percent == SCALE_DEFAULT_PERCENT and SCALE_ENV_VAR in os.environ:
        logger.info(
            f"Interface scale left at the inherited {SCALE_ENV_VAR}="
            f"{os.environ[SCALE_ENV_VAR]}"
        )
        return

    os.environ[SCALE_ENV_VAR] = f"{percent / 100:g}"
    logger.info(
        f"Interface scale set to {percent}% ({SCALE_ENV_VAR}="
        f"{os.environ[SCALE_ENV_VAR]})"
    )


def request_relaunch():
    """Ask the runner to start a fresh process once this one has stopped."""
    global _relaunch_requested
    _relaunch_requested = True


def relaunch_if_requested():
    """Start the replacement process, if the user asked for a new scale.

    Called by the runner after the application has stopped and its
    context managers have unwound. The child is spawned rather than
    exec'd so the teardown this process is in the middle of completes
    normally on every platform.
    """
    if not _relaunch_requested:
        return

    command = _relaunch_command()
    if command is None:
        logger.warning(
            "Cannot work out how to relaunch; start Microdrop again "
            "by hand to pick up the new interface scale."
        )
        return

    # The child works its own scale out from the preferences it re-reads, so
    # it must not inherit ours — otherwise a return to 100% would look like an
    # external override and the old factor would stick.
    environment = os.environ.copy()
    environment.pop(SCALE_ENV_VAR, None)

    logger.info(
        f"Relaunching Microdrop to apply the new interface scale: {' '.join(command)}"
    )
    subprocess.Popen(command, cwd=os.getcwd(), env=environment)


def _relaunch_command():
    """Rebuild this process' own command line.

    The runners are started as ``python -m examples.run_...``; replaying
    that as a file path would put the script's directory on ``sys.path``
    instead of the repo root and break every package import, so the
    module form is reconstructed from ``__main__``'s spec whenever there
    is one.
    """
    spec = getattr(sys.modules.get("__main__"), "__spec__", None)
    if spec is not None:
        return [sys.executable, "-m", spec.name, *sys.argv[1:]]

    if sys.argv and Path(sys.argv[0]).is_file():
        return [sys.executable, *sys.argv]

    # Started as `python -c ...` or embedded — nothing to replay.
    return None
