# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Bring an out-of-date MicroDrop environment up to date, then relaunch.

A user who updates the source but not the pixi-microdrop launcher repository
runs an environment that lacks packages newer features need. The fix is the
launcher's own update path: ``git pull`` in the launcher checkout, then
``pixi install`` in its pixi workspace. This module is the Qt-free core —
locating the workspace and repository, building and running those commands,
and relaunching the app; ``environment_update_dialog`` is the user-facing
flow on top of it.
"""

# Standard library imports.
import os
import subprocess
import sys
from collections import deque
from pathlib import Path

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Same semantics as the startup source self-update: never start a merge
#: the user would have to resolve, and carry the legitimately-dirty manifest
#: (installed-plugin pins) across the pull.
GIT_PULL_COMMAND = ("git", "pull", "--ff-only", "--autostash")

#: Lines of a failed command's output an EnvironmentUpdateError keeps.
OUTPUT_TAIL_LINES = 40


class EnvironmentUpdateError(RuntimeError):
    """An update step could not run or failed; ``output`` is the tail of
    what it printed."""

    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output


def find_pixi_workspace(start=None):
    """The pixi workspace holding ``start`` (default: the running
    interpreter's ``sys.prefix``): the nearest directory at or above it with
    a ``pixi.toml``, or a ``pyproject.toml`` declaring a ``[tool.pixi``
    table. None when there is none (a packed hand-off install)."""
    start = Path(start or sys.prefix)

    for directory in (start, *start.parents):
        if (directory / "pixi.toml").exists():
            return directory

        pyproject = directory / "pyproject.toml"

        if not pyproject.exists():
            continue

        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning(f"Could not read {pyproject}: {e}")

            continue

        if "[tool.pixi" in text:
            return directory

    return None


def find_git_repository(start):
    """The git checkout holding ``start``: the nearest directory at or above
    it with a ``.git`` entry (a file for submodules and worktrees), or
    None."""
    start = Path(start)

    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory

    return None


def pixi_environment_name(prefix=None):
    """The pixi environment ``prefix`` (default ``sys.prefix``) is, from its
    ``.pixi/envs/<name>`` location, or None when it is not one."""
    prefix = Path(prefix or sys.prefix)

    if prefix.parent.name == "envs" and prefix.parent.parent.name == ".pixi":
        return prefix.name

    return None


def update_steps(workspace, repository, environment=None):
    """The update as ``[(argv, cwd), ...]``: pull the launcher
    ``repository``, then install ``environment`` (pixi's default when None)
    from the ``workspace``'s freshly pulled lockfile."""
    install = ["pixi", "install"]

    if environment:
        install += ["--environment", environment]

    return [
        (list(GIT_PULL_COMMAND), Path(repository)),
        (install, Path(workspace)),
    ]


def locate_update_steps(prefix=None):
    """``update_steps`` for the environment at ``prefix`` (default
    ``sys.prefix``). Raises EnvironmentUpdateError when it does not live in
    a pixi workspace inside a git checkout — such an install cannot update
    itself this way."""
    prefix = Path(prefix or sys.prefix)
    workspace = find_pixi_workspace(prefix)

    if workspace is None:
        raise EnvironmentUpdateError(
            f"No pixi workspace found above {prefix}, so this install cannot "
            "update itself."
        )

    repository = find_git_repository(workspace)

    if repository is None:
        raise EnvironmentUpdateError(
            f"The pixi workspace {workspace} is not inside a git checkout of "
            "the pixi-microdrop repository."
        )

    return update_steps(workspace, repository, pixi_environment_name(prefix))


def manual_update_commands(steps):
    """``steps`` as shell lines a user can run by hand."""
    return "\n".join(f'cd "{cwd}" && {" ".join(argv)}' for argv, cwd in steps)


def run_update_steps(steps):
    """Run ``steps`` in order, logging every line they print. Raises
    EnvironmentUpdateError naming the first command that could not start or
    exited non-zero; the steps after it do not run."""
    # A pull that needs credentials fails instead of waiting on a prompt
    # nobody can see.
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    for argv, cwd in steps:
        command = " ".join(argv)
        logger.info(f"Environment update: running `{command}` in {cwd}")

        try:
            process = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as e:
            raise EnvironmentUpdateError(f"`{command}` could not start: {e}") from e

        tail = deque(maxlen=OUTPUT_TAIL_LINES)

        for line in process.stdout:
            line = line.rstrip()

            if line:
                logger.info(f"{argv[0]}: {line}")
                tail.append(line)

        code = process.wait()

        if code != 0:
            raise EnvironmentUpdateError(
                f"`{command}` exited with code {code}", "\n".join(tail)
            )

    logger.info("Environment update finished")


def relaunch_command():
    """The command line that started this process: the same interpreter with
    the same flags and arguments (``sys.orig_argv`` keeps a ``-m module``
    launch intact, where ``sys.argv`` would not)."""
    return [sys.executable, *sys.orig_argv[1:]]


def relaunch(application=None):
    """Exit ``application`` (an Envisage application, if given — saves the
    window layout and stops the plugins) and start this process's command
    line again in the current working directory. Returns False when the
    exit was vetoed; otherwise does not return. Raises OSError when the new
    process cannot start."""
    argv = relaunch_command()

    if application is not None and not application.exit():
        logger.info("Relaunch cancelled: the application did not exit")

        return False

    logger.info(f"Relaunching: {' '.join(argv)} in {Path.cwd()}")

    if sys.platform == "win32":
        # os.execv on Windows spawns and exits anyway, but without quoting
        # its arguments, so an interpreter path with spaces would break.
        subprocess.Popen(argv)
        os._exit(0)

    os.execv(sys.executable, argv)
