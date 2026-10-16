# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""environment_update: locating the launcher checkout, the update commands
(reset, default-branch checkout, pull, re-adding the installed plugins),
their failure reporting, and the relaunch command line."""

# Standard library imports.
import subprocess
import sys

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils import environment_update
from microdrop_utils.environment_update import (
    EnvironmentUpdateError,
    ExternalPlugin,
    default_branch,
    find_git_repository,
    find_pixi_workspace,
    locate_update,
    manual_update_commands,
    pixi_environment_name,
    relaunch,
    relaunch_command,
    run_update_steps,
)

CHANNEL = "https://prefix.dev/microdrop-plugins"

PLUGINS = [
    ExternalPlugin(name="heater-microdrop-plugin", channel=CHANNEL),
    ExternalPlugin(name="magnet-microdrop-plugin", version="1.2.0", channel=CHANNEL),
    ExternalPlugin(name="gamepad-microdrop-plugin", channel=CHANNEL),
]


class FakePluginsProvider:
    """An IExternalPluginsProvider reporting ``plugins`` (or raising
    ``failure``), re-adding each the way package_installer does."""

    def __init__(self, plugins=(), failure=None):
        self.plugins = list(plugins)
        self.failure = failure
        self.asked = []

    def installed_external_plugins(self, workspace):
        self.asked.append(workspace)

        if self.failure is not None:
            raise self.failure

        return self.plugins

    def reinstall_arguments(self, plugin):
        spec = f"{plugin.name}=={plugin.version}" if plugin.version else plugin.name

        return [["workspace", "channel", "add", plugin.channel], ["add", spec]]


@pytest.fixture(autouse=True)
def pixi_on_path(monkeypatch):
    """Locating the update checks pixi is installed; pretend it is."""
    monkeypatch.setattr(environment_update.shutil, "which", lambda name: f"/bin/{name}")


def _fake_git(monkeypatch, returncode, stdout=""):
    """Answer every ``subprocess.run`` with ``returncode`` and ``stdout``,
    recording the argv lists asked."""
    asked = []

    def run(argv, **kwargs):
        asked.append(list(argv))

        return subprocess.CompletedProcess(argv, returncode, stdout, "")

    monkeypatch.setattr(environment_update.subprocess, "run", run)

    return asked


@pytest.fixture(autouse=True)
def no_origin_head(monkeypatch):
    """The fake launcher checkouts record no origin/HEAD."""
    _fake_git(monkeypatch, returncode=1)


def _launcher(root, manifest="[tool.pixi.workspace]\n"):
    """A pixi-microdrop-shaped tree; returns (repository, workspace, prefix)."""
    repository = root / "pixi-microdrop"
    workspace = repository / "microdrop-py"
    prefix = workspace / ".pixi" / "envs" / "prod"
    prefix.mkdir(parents=True)
    (repository / ".git").mkdir()
    (workspace / "pyproject.toml").write_text(manifest)

    return repository, workspace, prefix


def test_locates_the_launcher_checkout_and_environment(tmp_path):
    repository, workspace, prefix = _launcher(tmp_path)
    provider = FakePluginsProvider()

    assert find_pixi_workspace(prefix) == workspace
    assert find_git_repository(workspace) == repository
    assert pixi_environment_name(prefix) == "prod"
    plan = locate_update(prefix, provider)

    assert plan.steps == [
        (["git", "status", "--porcelain"], repository),
        (["git", "reset", "--hard", "--no-recurse-submodules"], repository),
        (["git", "checkout", "master"], repository),
        (["git", "pull", "--ff-only", "--no-recurse-submodules"], repository),
        (["pixi", "install", "--environment", "prod"], workspace),
    ]
    assert plan.plugins == []
    assert plan.branch == "master"
    assert provider.asked == [workspace]


def test_the_installed_plugins_are_re_added_between_the_pull_and_install(
    tmp_path,
):
    repository, workspace, prefix = _launcher(tmp_path)

    plan = locate_update(prefix, FakePluginsProvider(PLUGINS))

    assert plan.plugins == PLUGINS
    assert plan.steps == [
        (["git", "status", "--porcelain"], repository),
        (["git", "reset", "--hard", "--no-recurse-submodules"], repository),
        (["git", "checkout", "master"], repository),
        (["git", "pull", "--ff-only", "--no-recurse-submodules"], repository),
        # One channel registration covers every plugin from that channel.
        (["pixi", "workspace", "channel", "add", CHANNEL], workspace),
        (["pixi", "add", "heater-microdrop-plugin"], workspace),
        (["pixi", "add", "magnet-microdrop-plugin==1.2.0"], workspace),
        (["pixi", "add", "gamepad-microdrop-plugin"], workspace),
        (["pixi", "install", "--environment", "prod"], workspace),
    ]


def test_the_reset_keeps_untracked_files_and_the_submodule(tmp_path):
    _repository, _workspace, prefix = _launcher(tmp_path)

    steps = locate_update(prefix, FakePluginsProvider(PLUGINS)).steps
    git_commands = [argv for argv, _cwd in steps if argv[0] == "git"]

    assert ["git", "reset", "--hard", "--no-recurse-submodules"] in git_commands
    assert not any("clean" in argv for argv in git_commands)
    assert not any("--recurse-submodules" in argv for argv in git_commands)


def test_the_default_branch_is_checked_out_before_the_pull(tmp_path, monkeypatch):
    repository, _workspace, prefix = _launcher(tmp_path)
    asked = _fake_git(monkeypatch, returncode=0, stdout="origin/main\n")

    plan = locate_update(prefix, FakePluginsProvider())
    git_commands = [argv for argv, _cwd in plan.steps if argv[0] == "git"]

    assert plan.branch == "main"
    assert git_commands[1:4] == [
        ["git", "reset", "--hard", "--no-recurse-submodules"],
        ["git", "checkout", "main"],
        ["git", "pull", "--ff-only", "--no-recurse-submodules"],
    ]
    assert asked == [list(environment_update.GIT_DEFAULT_BRANCH_COMMAND)]


def test_default_branch_strips_the_remote_name(tmp_path, monkeypatch):
    _fake_git(monkeypatch, returncode=0, stdout="origin/main\n")

    assert default_branch(tmp_path) == "main"


def test_default_branch_falls_back_to_master_without_origin_head(tmp_path):
    assert default_branch(tmp_path) == "master"


def test_default_branch_falls_back_to_master_without_git(tmp_path, monkeypatch):
    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(environment_update.subprocess, "run", missing_git)

    assert default_branch(tmp_path) == "master"


def test_a_plugin_detection_failure_stops_before_anything_runs(tmp_path, monkeypatch):
    _repository, _workspace, prefix = _launcher(tmp_path)

    def must_not_run(*args, **kwargs):
        pytest.fail("nothing may run when the installed plugins are unknown")

    monkeypatch.setattr(environment_update.subprocess, "Popen", must_not_run)
    failure = EnvironmentUpdateError("manifest unreadable")

    with pytest.raises(EnvironmentUpdateError, match="manifest unreadable"):
        locate_update(prefix, FakePluginsProvider(failure=failure))


def test_without_a_plugins_provider_the_update_refuses_to_reset(tmp_path):
    _repository, _workspace, prefix = _launcher(tmp_path)

    with pytest.raises(EnvironmentUpdateError, match="would be lost"):
        locate_update(prefix)


def test_without_pixi_the_update_refuses_to_reset(tmp_path, monkeypatch):
    _repository, _workspace, prefix = _launcher(tmp_path)
    monkeypatch.setattr(environment_update.shutil, "which", lambda name: None)

    with pytest.raises(EnvironmentUpdateError, match="pixi is not on the PATH"):
        locate_update(prefix, FakePluginsProvider(PLUGINS))


def test_a_pyproject_without_a_pixi_table_is_not_a_workspace(tmp_path):
    _repository, _workspace, prefix = _launcher(tmp_path, manifest="[project]\n")

    assert find_pixi_workspace(prefix) is None

    with pytest.raises(EnvironmentUpdateError, match="No pixi workspace"):
        locate_update(prefix, FakePluginsProvider())


def test_a_workspace_outside_a_git_checkout_cannot_update(tmp_path):
    repository, _workspace, prefix = _launcher(tmp_path)
    (repository / ".git").rmdir()

    with pytest.raises(EnvironmentUpdateError, match="not inside a git checkout"):
        locate_update(prefix, FakePluginsProvider())


def test_manual_commands_name_every_step_and_folder(tmp_path):
    repository, workspace, prefix = _launcher(tmp_path)
    steps = locate_update(prefix, FakePluginsProvider(PLUGINS[:2])).steps

    commands = manual_update_commands(steps)

    assert commands.splitlines() == [
        f'cd "{repository}" && git status --porcelain',
        f'cd "{repository}" && git reset --hard --no-recurse-submodules',
        f'cd "{repository}" && git checkout master',
        f'cd "{repository}" && git pull --ff-only --no-recurse-submodules',
        f'cd "{workspace}" && pixi workspace channel add {CHANNEL}',
        f'cd "{workspace}" && pixi add heater-microdrop-plugin',
        f'cd "{workspace}" && pixi add magnet-microdrop-plugin==1.2.0',
        f'cd "{workspace}" && pixi install --environment prod',
    ]


def test_a_failing_step_stops_the_update_with_its_output(tmp_path):
    never_run = tmp_path / "never_run"
    steps = [
        ([sys.executable, "-c", "print('pulled')"], tmp_path),
        ([sys.executable, "-c", "print('lock broken'); raise SystemExit(3)"], tmp_path),
        ([sys.executable, "-c", f"open({str(never_run)!r}, 'w')"], tmp_path),
    ]

    with pytest.raises(EnvironmentUpdateError, match="exited with code 3") as raised:
        run_update_steps(steps)

    assert raised.value.output == "lock broken"
    assert not never_run.exists()


def test_a_missing_program_is_an_update_error(tmp_path):
    steps = [(["definitely-not-a-real-program-xyz"], tmp_path)]

    with pytest.raises(EnvironmentUpdateError, match="could not start"):
        run_update_steps(steps)


def test_relaunch_reuses_the_interpreter_and_original_arguments(monkeypatch):
    monkeypatch.setattr(
        sys, "orig_argv", ["python", "-m", "examples.run_device_viewer_pluggable"]
    )

    assert relaunch_command() == [
        sys.executable,
        "-m",
        "examples.run_device_viewer_pluggable",
    ]


def test_a_vetoed_exit_cancels_the_relaunch(monkeypatch):
    class VetoingApplication:
        def exit(self):
            return False

    def must_not_spawn(*args, **kwargs):
        pytest.fail("a vetoed exit must not start a new process")

    monkeypatch.setattr(environment_update.subprocess, "Popen", must_not_spawn)
    monkeypatch.setattr(environment_update.os, "execv", must_not_spawn)

    assert relaunch(VetoingApplication()) is False
