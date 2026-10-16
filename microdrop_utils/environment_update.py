# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Bring an out-of-date MicroDrop environment up to date, then make the new
packages importable in the running app.

A user who updates the source but not the pixi-microdrop launcher repository
runs an environment that lacks packages newer features need. The fix is the
launcher's own update path: ``git pull`` in the launcher checkout, then
``pixi install`` in its pixi workspace.

Installing a plugin through Manage Plugins edits the launcher's
``pyproject.toml`` and ``pixi.lock``, so the pull would refuse a dirty tree.
The update therefore resets the launcher checkout, checks out its default
branch (a hand-off install cloned at a release tag sits on a detached HEAD,
which cannot pull), pulls, and re-adds the external plugins the user had
installed. Which plugins those are, and how to re-add them, is
plugin-management knowledge this shared module must not import: an
``IExternalPluginsProvider`` service supplies it.

A package the environment lacked entirely can be imported straight after the
install (``make_importable``), as the plugin hot-loader does.

This module is the Qt-free core — locating the workspace and repository,
building and running those commands, and importing a newly installed package;
``environment_update_dialog`` is the user-facing flow on top of it.
"""

# Standard library imports.
import importlib
import os
import shutil
import site
import subprocess
import sys
import sysconfig
from collections import deque
from pathlib import Path

# Enthought library imports.
from traits.api import HasTraits, Instance, Interface, List, Str, Tuple

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Logged before the reset, so the log records what it discarded.
GIT_STATUS_COMMAND = ("git", "status", "--porcelain")

#: Discards the tracked changes (installed-plugin edits to the manifest and
#: lockfile) that would stop the pull. No ``git clean``: untracked files stay.
#: Never recursed into submodules, whatever ``submodule.recurse`` says — the
#: Microdrop source checkout under the launcher keeps its own work.
GIT_RESET_COMMAND = ("git", "reset", "--hard", "--no-recurse-submodules")

#: Asks for the launcher's default branch, as ``origin/<branch>``; fails when
#: the clone never recorded ``origin/HEAD``.
GIT_DEFAULT_BRANCH_COMMAND = (
    "git",
    "symbolic-ref",
    "-q",
    "--short",
    "refs/remotes/origin/HEAD",
)

#: The branch the update checks out when ``origin/HEAD`` is not recorded.
FALLBACK_BRANCH = "master"

#: Never start a merge the user would have to resolve; leave the submodule
#: checkout alone, like the reset.
GIT_PULL_COMMAND = ("git", "pull", "--ff-only", "--no-recurse-submodules")

#: Lines of a failed command's output an EnvironmentUpdateError keeps.
OUTPUT_TAIL_LINES = 40


class EnvironmentUpdateError(RuntimeError):
    """An update step could not run or failed; ``output`` is the tail of
    what it printed."""

    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output


class ExternalPlugin(HasTraits):
    """A plugin package the user installed into the launcher's workspace,
    with what it takes to re-add it identically after the reset."""

    #: Package name, as Manage Plugins lists it.
    name = Str()

    #: Pinned version, or "" when the install took the channel's latest.
    version = Str()

    #: Channel the package was installed from.
    channel = Str()


class UpdatePlan(HasTraits):
    """A planned update: the commands to run and what the user is told
    about them before it starts."""

    #: The ``update_steps``, as ``(argv, cwd)`` pairs.
    steps = List(Tuple())

    #: The external plugins the steps re-add after the reset.
    plugins = List(Instance(ExternalPlugin))

    #: The launcher branch the steps check out and pull.
    branch = Str()


class IExternalPluginsProvider(Interface):
    """Service telling the update which external plugins to re-add.

    Offered by the plugin-management plugin, which owns how plugins are
    installed; without it the update refuses to reset the launcher, since it
    could not put the plugins back."""

    def installed_external_plugins(self, workspace):
        """The ``ExternalPlugin``s installed into the pixi ``workspace``, in
        manifest order. Raises EnvironmentUpdateError when that cannot be
        told."""

    def reinstall_arguments(self, plugin):
        """The pixi argument lists (without ``pixi``) that re-add
        ``plugin``, in order."""


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


def default_branch(repository):
    """The default branch of the git checkout ``repository``, from its
    ``origin/HEAD`` ref, or ``FALLBACK_BRANCH`` when that is not set (or git
    cannot run)."""
    try:
        result = subprocess.run(
            GIT_DEFAULT_BRANCH_COMMAND,
            cwd=str(repository),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
    except OSError as e:
        logger.warning(f"Could not ask git for the default branch: {e}")

        return FALLBACK_BRANCH

    branch = result.stdout.strip().removeprefix("origin/")

    if result.returncode != 0 or not branch:
        logger.info(
            f"No origin/HEAD recorded in {repository}; updating {FALLBACK_BRANCH}"
        )

        return FALLBACK_BRANCH

    return branch


def update_steps(
    workspace,
    repository,
    environment=None,
    reinstall_arguments=(),
    branch=FALLBACK_BRANCH,
):
    """The update as ``[(argv, cwd), ...]``: log and reset the launcher
    ``repository``, check out ``branch`` (off a detached HEAD), pull it, run
    each of ``reinstall_arguments`` (pixi argument lists, duplicates
    dropped) in the ``workspace``, then install ``environment`` (pixi's
    default when None) from the result."""
    repository = Path(repository)
    workspace = Path(workspace)
    install = ["pixi", "install"]

    if environment:
        install += ["--environment", environment]

    reinstall = dict.fromkeys(tuple(arguments) for arguments in reinstall_arguments)

    return [
        (list(GIT_STATUS_COMMAND), repository),
        (list(GIT_RESET_COMMAND), repository),
        # No --force: the reset just left the tree clean.
        (["git", "checkout", branch], repository),
        (list(GIT_PULL_COMMAND), repository),
        *((["pixi", *arguments], workspace) for arguments in reinstall),
        (install, workspace),
    ]


def locate_update(prefix=None, plugins_provider=None):
    """The ``UpdatePlan`` for the environment at ``prefix`` (default
    ``sys.prefix``): the ``update_steps``, the launcher's default branch
    they check out, and the ``ExternalPlugin``s they re-add, as told by
    ``plugins_provider`` (an ``IExternalPluginsProvider``).

    Raises EnvironmentUpdateError — before anything has run, so no plugin is
    lost — when the environment does not live in a pixi workspace inside a
    git checkout, pixi is not on the PATH, or the installed plugins cannot
    be told."""
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

    if shutil.which("pixi") is None:
        raise EnvironmentUpdateError(
            "pixi is not on the PATH, so the plugins could not be re-added "
            "after the update."
        )

    if plugins_provider is None:
        raise EnvironmentUpdateError(
            "Plugin management is not running, so the installed plugins "
            "cannot be told and would be lost by the update."
        )

    plugins = list(plugins_provider.installed_external_plugins(workspace))
    reinstall_arguments = [
        arguments
        for plugin in plugins
        for arguments in plugins_provider.reinstall_arguments(plugin)
    ]

    branch = default_branch(repository)
    steps = update_steps(
        workspace,
        repository,
        pixi_environment_name(prefix),
        reinstall_arguments,
        branch,
    )

    return UpdatePlan(steps=steps, plugins=plugins, branch=branch)


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


def make_importable(package):
    """Import ``package``, which an update has just installed into this
    interpreter's environment, into the running app and return the module.
    Raises EnvironmentUpdateError when it still cannot be imported.

    Only for a package the app has not imported before: one already in
    ``sys.modules`` keeps its old code, which takes a restart to replace."""
    known = {os.path.normcase(os.path.abspath(entry)) for entry in sys.path}

    # The install writes into this interpreter's own site-packages, normally
    # on sys.path since startup; one that did not exist then is added with
    # its .pth files. Never re-added when present, which would re-run them.
    for directory in {sysconfig.get_path("purelib"), sysconfig.get_path("platlib")}:
        if os.path.isdir(directory) and os.path.normcase(directory) not in known:
            logger.info(f"Adding {directory} to sys.path")
            site.addsitedir(directory)

    # The path finders cache directory listings (and the missing directories
    # they gave up on), so a package installed after startup stays invisible
    # to import until they are dropped — the plugin hot-loader does the same.
    importlib.invalidate_caches()

    try:
        module = importlib.import_module(package)
    except ImportError as e:
        raise EnvironmentUpdateError(
            f"{package} could not be imported after the update: {e}"
        ) from e

    logger.info(f"Imported {package} from {getattr(module, '__file__', None)}")

    return module
