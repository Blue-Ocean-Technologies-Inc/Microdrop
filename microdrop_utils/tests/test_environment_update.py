# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""environment_update: locating the launcher checkout, the update commands,
their failure reporting, and the relaunch command line."""

# Standard library imports.
import sys

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils import environment_update
from microdrop_utils.environment_update import (
    EnvironmentUpdateError,
    find_git_repository,
    find_pixi_workspace,
    locate_update_steps,
    manual_update_commands,
    pixi_environment_name,
    relaunch,
    relaunch_command,
    run_update_steps,
)


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

    assert find_pixi_workspace(prefix) == workspace
    assert find_git_repository(workspace) == repository
    assert pixi_environment_name(prefix) == "prod"
    assert locate_update_steps(prefix) == [
        (["git", "pull", "--ff-only", "--autostash"], repository),
        (["pixi", "install", "--environment", "prod"], workspace),
    ]


def test_a_pyproject_without_a_pixi_table_is_not_a_workspace(tmp_path):
    _repository, _workspace, prefix = _launcher(tmp_path, manifest="[project]\n")

    assert find_pixi_workspace(prefix) is None

    with pytest.raises(EnvironmentUpdateError, match="No pixi workspace"):
        locate_update_steps(prefix)


def test_a_workspace_outside_a_git_checkout_cannot_update(tmp_path):
    repository, _workspace, prefix = _launcher(tmp_path)
    (repository / ".git").rmdir()

    with pytest.raises(EnvironmentUpdateError, match="not inside a git checkout"):
        locate_update_steps(prefix)


def test_manual_commands_name_every_step_and_folder(tmp_path):
    repository, workspace, prefix = _launcher(tmp_path)

    commands = manual_update_commands(locate_update_steps(prefix))

    assert commands.splitlines() == [
        f'cd "{repository}" && git pull --ff-only --autostash',
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
