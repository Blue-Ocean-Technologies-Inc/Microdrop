# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""offer_environment_update: the question names what the update discards
and the plugins it re-adds, Not now does nothing, Update runs the update then
imports the package so the feature carries on, and a failure hands over the
manual commands."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import (
    CANCEL,
    OK,
    escape_html_multiline,
)

# Microdrop utils imports.
from microdrop_utils import environment_update_dialog
from microdrop_utils.environment_update import (
    EnvironmentUpdateError,
    ExternalPlugin,
    IExternalPluginsProvider,
    UpdatePlan,
    manual_update_commands,
)

STEPS = [
    (["git", "reset", "--hard"], Path("launcher")),
    (["git", "pull"], Path("launcher")),
    (["pixi", "add", "heater-microdrop-plugin"], Path("ws")),
    (["pixi", "install"], Path("ws")),
]

PLUGINS = [
    ExternalPlugin(name="heater-microdrop-plugin"),
    ExternalPlugin(name="magnet-microdrop-plugin"),
    ExternalPlugin(name="fluorescence-microdrop-plugin"),
]


class Application:
    """An Envisage application offering ``provider`` as its
    IExternalPluginsProvider service."""

    def __init__(self, provider=None):
        self.provider = provider

    def get_service(self, protocol):
        return self.provider if protocol is IExternalPluginsProvider else None


@pytest.fixture
def flow(monkeypatch):
    """Answer the warning with ``flow["choice"]``, run the update work
    synchronously, and record what the flow did."""
    record = {
        "choice": OK,
        "plugins": PLUGINS,
        "providers": [],
        "questions": [],
        "labels": [],
        "ran": [],
        "imported": [],
        "errors": [],
        "informed": [],
    }

    def run_with_wait(work, *, on_success, on_error, **kwargs):
        try:
            result = work()
        except EnvironmentUpdateError as e:
            on_error(e)
        else:
            on_success(result)

    def warning(parent, message, **kwargs):
        record["questions"].append(message)
        record["labels"].append(kwargs["ok_label"])

        return record["choice"]

    def locate_update(plugins_provider=None):
        record["providers"].append(plugins_provider)

        return UpdatePlan(steps=STEPS, plugins=record["plugins"], branch="main")

    monkeypatch.setattr(environment_update_dialog, "warning", warning)
    monkeypatch.setattr(environment_update_dialog, "locate_update", locate_update)
    monkeypatch.setattr(environment_update_dialog, "run_with_wait", run_with_wait)
    monkeypatch.setattr(
        environment_update_dialog, "run_update_steps", record["ran"].append
    )
    monkeypatch.setattr(
        environment_update_dialog, "make_importable", record["imported"].append
    )
    monkeypatch.setattr(
        environment_update_dialog,
        "information",
        lambda *args, **kwargs: record["informed"].append(args),
    )
    monkeypatch.setattr(
        environment_update_dialog,
        "error",
        lambda parent, message, **kw: record["errors"].append((message, kw)),
    )

    return record


def test_the_question_lists_the_plugins_the_update_re_adds(flow):
    flow["choice"] = CANCEL

    environment_update_dialog.offer_environment_update("X", "pkg")

    [question] = flow["questions"]
    assert "pyproject.toml, pixi.lock" in question
    assert (
        "re-added afterwards:<br><br>"
        "- <strong>heater-microdrop-plugin</strong><br>"
        "- <strong>magnet-microdrop-plugin</strong><br>"
        "- <strong>fluorescence-microdrop-plugin</strong>" in question
    )


def test_the_question_names_the_branch_the_launcher_is_switched_to(flow):
    flow["choice"] = CANCEL

    environment_update_dialog.offer_environment_update("X", "pkg")

    [question] = flow["questions"]
    assert (
        "The <strong>pixi-microdrop</strong> repository will be switched to its "
        "<strong>main</strong> branch and updated." in question
    )


def test_the_question_says_when_no_plugins_need_re_adding(flow):
    flow["choice"] = CANCEL
    flow["plugins"] = []

    environment_update_dialog.offer_environment_update("X", "pkg")

    [question] = flow["questions"]
    assert "no external plugins are installed" in question
    assert "<strong>main</strong> branch" in question


def test_the_plugins_come_from_the_application_provider_service(flow):
    provider = object()
    flow["choice"] = CANCEL

    environment_update_dialog.offer_environment_update(
        "X", "pkg", Application(provider)
    )
    environment_update_dialog.offer_environment_update("X", "pkg")

    assert flow["providers"] == [provider, None]


def test_not_now_runs_nothing(flow):
    flow["choice"] = CANCEL

    assert environment_update_dialog.offer_environment_update("X", "pkg") is False
    assert flow["ran"] == []


def test_update_runs_the_steps_then_imports_the_package(flow):
    ready = environment_update_dialog.offer_environment_update(
        "X", "pkg", Application()
    )

    assert ready is True
    assert flow["labels"] == [environment_update_dialog.UPDATE_LABEL]
    assert flow["ran"] == [STEPS]
    assert flow["imported"] == ["pkg"]

    [(_parent, message)] = flow["informed"]
    assert message == "Update complete. <strong>X</strong> can continue."


def test_a_package_that_will_not_import_asks_for_a_restart(flow, monkeypatch):
    def unimportable(package):
        raise EnvironmentUpdateError(f"{package} could not be imported")

    monkeypatch.setattr(environment_update_dialog, "make_importable", unimportable)

    assert environment_update_dialog.offer_environment_update("X", "pkg") is False

    [(_parent, message)] = flow["informed"]
    assert "Restart MicroDrop" in message


def test_a_failed_update_is_not_ready_and_imports_nothing(flow, monkeypatch):
    def fail(steps):
        raise EnvironmentUpdateError("`git pull` exited with code 1")

    monkeypatch.setattr(environment_update_dialog, "run_update_steps", fail)

    assert environment_update_dialog.offer_environment_update("X", "pkg") is False
    assert len(flow["errors"]) == 1
    assert flow["imported"] == []


def test_a_package_still_missing_gets_the_manual_commands(flow):
    environment_update_dialog.report_package_still_missing("pkg")

    [(message, _kwargs)] = flow["errors"]
    assert "pkg is still not available" in message
    assert "pixi install" in message


def test_a_failed_update_shows_the_manual_commands(flow, monkeypatch):
    def fail(steps):
        raise EnvironmentUpdateError(
            "`pixi install` exited with code 1", "solve failed"
        )

    monkeypatch.setattr(environment_update_dialog, "run_update_steps", fail)

    environment_update_dialog.offer_environment_update("X", "pkg")

    [(message, kwargs)] = flow["errors"]
    commands = escape_html_multiline(manual_update_commands(STEPS))
    assert commands in message
    assert "git reset --hard" in commands
    assert "pixi add heater-microdrop-plugin" in commands
    assert kwargs["detail"] == "solve failed"


def test_an_install_that_cannot_locate_its_checkout_gets_generic_commands(
    flow, monkeypatch
):
    def unlocatable(plugins_provider=None):
        raise EnvironmentUpdateError("No pixi workspace found")

    monkeypatch.setattr(environment_update_dialog, "locate_update", unlocatable)

    environment_update_dialog.offer_environment_update("X", "pkg")

    [question] = flow["questions"]
    [(message, _kwargs)] = flow["errors"]
    assert "will be discarded" not in question
    assert "pixi install" in message
    assert flow["ran"] == []
