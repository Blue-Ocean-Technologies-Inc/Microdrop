# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The startup step that logs the source version and, when the user's
preference allows, moves a managed checkout to the newest release with the
Updates panel, then re-runs the app on it.

It runs on every start of every install, before the app exists, so it never
raises and never moves a development checkout.
"""

# Standard library imports.
import logging
import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path

# Microdrop utils imports.
from microdrop_utils.application_home import read_bool_preference
from microdrop_utils.source_version import (
    NO_GIT,
    SourceVersionError,
    checkout_state,
    current_branch,
    describe,
    exact_release,
    pending_update,
    switch_to,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: The MicroDrop source checkout this module is part of.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Set to any non-empty value to keep the checkout where it is at startup —
#: for developer machines where the IDE or the launcher scripts manage it.
SKIP_GIT_UPDATE_ENV_VAR = "MICRODROP_SKIP_GIT_UPDATE"

#: Set in the re-run app, so it starts on the version it was given.
UPDATE_APPLIED_ENV_VAR = "MICRODROP_SOURCE_UPDATE_APPLIED"

#: True: move to the newest release at startup. False: stay on this one.
AUTO_UPDATE_PREFERENCE_PATH = "microdrop.app_updates.auto_update"

#: The newest release the user has been told about.
LAST_ANNOUNCED_PREFERENCE_PATH = "microdrop.app_updates.last_announced_version"

#: How often, and how many seconds apart, a refused checkout is retried.
CHECKOUT_RETRY_COUNT = 5
CHECKOUT_RETRY_DELAY_S = 1

#: The exit code of a process ended by Ctrl+C.
_INTERRUPTED_EXIT_CODE = 130


def source_version_line(repo_root):
    """Return the line logged at every start: the checkout's version and
    branch, or ``pinned release`` on a detached HEAD."""
    # The read helpers warn on a tree without .git; this line must not.
    if checkout_state(repo_root)[0] == NO_GIT:
        return "MicroDrop source version: unknown (not a git checkout)"

    branch = current_branch(repo_root) or "pinned release"

    return f"MicroDrop source version: {describe(repo_root)} ({branch})"


def _switch_with_retries(repo_root, tag_name):
    """Check out ``tag_name``, retrying while git refuses. Return True once
    the checkout is at the tag, whichever process moved it."""
    error = None

    for attempt in range(CHECKOUT_RETRY_COUNT + 1):
        # A second instance starting at the same moment holds git's index
        # lock while it makes the very same switch.
        if attempt > 0:
            time.sleep(CHECKOUT_RETRY_DELAY_S)

            if exact_release(repo_root) == tag_name:
                return True

        try:
            switch_to(repo_root, tag_name)

        except SourceVersionError as e:
            error = e

        else:
            return True

    logger.warning(
        f"Could not switch the MicroDrop source to {tag_name}; starting on the "
        f"current version. {error}: {error.output}"
    )

    return False


def _rerun_and_exit():
    """Run this command again in a child process on the switched checkout,
    then exit with the child's exit code."""
    # The child shares the console, so the parent's last lines go out first.
    for handler in logging.getLogger().handlers:
        handler.flush()

    # pythonw has no standard streams.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.flush()

    # orig_argv[0] may be a bare "python"; start the same interpreter by path.
    argv = [sys.executable, *sys.orig_argv[1:]]
    env = {**os.environ, UPDATE_APPLIED_ENV_VAR: "1"}

    # Ctrl+C reaches the child too; the parent just ends without a traceback.
    try:
        code = subprocess.call(argv, env=env)

    except KeyboardInterrupt:
        code = _INTERRUPTED_EXIT_CODE

    sys.exit(code)


def apply_source_update_policy(repo_root=PROJECT_ROOT):
    """Log the source version and apply the auto-update preference.

    When the checkout is managed, the preference allows it, and a newer
    release with the Updates panel exists, check that release out and re-run
    the app on it — this call then does not return. Every failure is a
    logged warning; the app starts on the version it has.
    """
    # A spawned child re-imports the launcher, so without this every worker
    # in a pool would run its own update — the app's own ROI batch once
    # produced one per CPU.
    if multiprocessing.parent_process() is not None:
        logger.debug("Source update skipped: worker process")

        return

    try:
        logger.info(source_version_line(repo_root))

        if os.environ.get(UPDATE_APPLIED_ENV_VAR):
            return

        if os.environ.get(SKIP_GIT_UPDATE_ENV_VAR):
            logger.info(
                f"Automatic source updates skipped ({SKIP_GIT_UPDATE_ENV_VAR} is set)"
            )

            return

        if not read_bool_preference(AUTO_UPDATE_PREFERENCE_PATH, True):
            return

        tag = pending_update(repo_root)

        if tag is None:
            return

        old_version = describe(repo_root)

        if not _switch_with_retries(repo_root, tag.name):
            return

        logger.warning(
            f"MicroDrop source updated ({old_version} -> {tag.name}); "
            f"restarting on the new version."
        )
        _rerun_and_exit()

    # SystemExit from the re-run is not an Exception, so it passes through.
    except Exception as e:
        logger.warning(f"Source update at startup failed: {e}")
