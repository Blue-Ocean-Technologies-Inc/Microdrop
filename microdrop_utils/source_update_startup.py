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
from microdrop_utils.application_home import (
    read_bool_preference,
    updates_preferences_file_path,
)
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
from microdrop_utils.user_environment import user_environment_variable

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

#: How often, and how many seconds apart, a checkout refused for git's index
#: lock is retried.
CHECKOUT_RETRY_COUNT = 5
CHECKOUT_RETRY_DELAY_S = 1

#: Git names this file when another git process holds the checkout.
INDEX_LOCK_NAME = "index.lock"


def source_version_line(repo_root):
    """Return the line logged at every start: the checkout's version and
    branch, or ``pinned release`` on a detached HEAD."""
    # The read helpers warn on a tree without .git; this line must not.
    if checkout_state(repo_root)[0] == NO_GIT:
        return "MicroDrop source version: unknown (not a git checkout)"

    branch = current_branch(repo_root) or "pinned release"

    return f"MicroDrop source version: {describe(repo_root)} ({branch})"


def skip_variable_is_set():
    """Return True when ``SKIP_GIT_UPDATE_ENV_VAR`` is set in this process or
    saved for the user — a process started before it was saved does not see
    it, yet must treat automatic updates as off just the same."""
    if os.environ.get(SKIP_GIT_UPDATE_ENV_VAR):
        return True

    return bool(user_environment_variable(SKIP_GIT_UPDATE_ENV_VAR))


def _switch_with_retries(repo_root, tag_name):
    """Check out ``tag_name``. Return True once the checkout is at the tag,
    whichever process moved it.

    Only git's index lock is waited out: a second instance starting at the
    same moment holds it while it makes the very same switch. Any other
    refusal (a file in the way) would only refuse again, delaying every
    start."""
    for attempt in range(CHECKOUT_RETRY_COUNT + 1):
        if attempt > 0:
            time.sleep(CHECKOUT_RETRY_DELAY_S)

        try:
            switch_to(repo_root, tag_name)

        except SourceVersionError as e:
            error = e

        else:
            return True

        if exact_release(repo_root) == tag_name:
            return True

        if INDEX_LOCK_NAME not in error.output:
            break

    logger.warning(
        f"Could not switch the MicroDrop source to {tag_name}; starting on the "
        f"current version. {error}: {error.output}"
    )

    return False


def _restart_app(argv, env):
    """Run ``argv`` with ``env`` in place of this process and exit with its
    exit code. Raise OSError when it cannot be started.

    The app handles Ctrl+C itself and shuts down gracefully (Envisage exit,
    Redis, the hardware backend), so this process must never cut that short.
    """
    if os.name == "posix":
        # Same PID: signals and the exit code go straight to the app.
        os.execve(sys.executable, argv, env)

    else:
        # Windows has no exec that keeps the process, so wait on a child
        # sharing the console.
        with subprocess.Popen(argv, env=env) as child:
            while child.returncode is None:
                try:
                    child.wait()

                # The child got the same console event and is shutting
                # itself down; outlive it, and never kill it.
                except KeyboardInterrupt:
                    pass

        sys.exit(child.returncode)


def _rerun_and_exit():
    """Run this command again on the switched checkout, in place of this
    process, and exit with its exit code. Raise OSError when it cannot be
    started."""
    # exec discards unwritten buffers and a child shares the console, so this
    # process's last lines go out first.
    for handler in logging.getLogger().handlers:
        handler.flush()

    # pythonw has no standard streams.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.flush()

    # orig_argv[0] may be a bare "python"; start the same interpreter by path.
    argv = [sys.executable, *sys.orig_argv[1:]]
    env = {**os.environ, UPDATE_APPLIED_ENV_VAR: "1"}

    _restart_app(argv, env)


def apply_source_update_policy(repo_root=PROJECT_ROOT):
    """Log the source version and apply the auto-update preference.

    When the checkout is managed, the preference allows it, and a newer
    release with the Updates panel exists, check that release out and re-run
    the app on it — this call then does not return. Every failure is a
    logged warning and the app goes on starting; only a restart that cannot
    be started leaves it on a checkout already moved.
    """
    # A spawned child re-imports the launcher, so without this every worker
    # in a pool would run its own update — the app's own ROI batch once
    # produced one per CPU.
    if multiprocessing.parent_process() is not None:
        logger.debug("Source update skipped: worker process")

        return

    # Popped before anything that can fail, so what this run starts later
    # (the in-app relaunch) is a fresh start that may update again.
    update_applied = os.environ.pop(UPDATE_APPLIED_ENV_VAR, None)

    try:
        logger.info(source_version_line(repo_root))

        if update_applied:
            return

        if skip_variable_is_set():
            logger.info(
                f"Automatic source updates skipped ({SKIP_GIT_UPDATE_ENV_VAR} is set)"
            )

            return

        auto_update = read_bool_preference(
            AUTO_UPDATE_PREFERENCE_PATH, True, filename=updates_preferences_file_path()
        )

        if not auto_update:
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

        try:
            _rerun_and_exit()

        # Starting anyway keeps the app usable, though modules it imports
        # from here on come from the new release. SystemExit from the re-run
        # is not an Exception, so it passes through.
        except Exception as e:
            logger.warning(
                f"MicroDrop source is now on {tag.name}, but the restart could "
                f"not be started ({e}); restart MicroDrop to run the new version."
            )

    except Exception as e:
        logger.warning(f"Source update at startup failed: {e}")
