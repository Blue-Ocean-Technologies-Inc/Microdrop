# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""offer_environment_update: Not now does nothing, Update and relaunch runs
the update then relaunches, and a failure hands over the manual commands."""

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
    manual_update_commands,
)

STEPS = [(["git", "pull"], Path("launcher")), (["pixi", "install"], Path("ws"))]


@pytest.fixture
def flow(monkeypatch):
    """Answer the warning with ``flow["choice"]``, run the update work
    synchronously, and record what the flow did."""
    record = {
        "choice": OK,
        "ran": [],
        "relaunched": [],
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

    monkeypatch.setattr(
        environment_update_dialog, "warning", lambda *a, **kw: record["choice"]
    )
    monkeypatch.setattr(environment_update_dialog, "locate_update_steps", lambda: STEPS)
    monkeypatch.setattr(environment_update_dialog, "run_with_wait", run_with_wait)
    monkeypatch.setattr(
        environment_update_dialog, "run_update_steps", record["ran"].append
    )
    monkeypatch.setattr(
        environment_update_dialog, "relaunch", record["relaunched"].append
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


def test_not_now_runs_nothing(flow):
    flow["choice"] = CANCEL

    assert environment_update_dialog.offer_environment_update("X", "pkg") is False
    assert flow["ran"] == []
    assert flow["relaunched"] == []


def test_update_runs_the_steps_then_relaunches_the_application(flow):
    application = object()

    started = environment_update_dialog.offer_environment_update(
        "X", "pkg", application
    )

    assert started is True
    assert flow["ran"] == [STEPS]
    assert flow["relaunched"] == [application]


def test_a_failed_update_shows_the_manual_commands_and_does_not_relaunch(
    flow, monkeypatch
):
    def fail(steps):
        raise EnvironmentUpdateError(
            "`pixi install` exited with code 1", "solve failed"
        )

    monkeypatch.setattr(environment_update_dialog, "run_update_steps", fail)

    environment_update_dialog.offer_environment_update("X", "pkg")

    [(message, kwargs)] = flow["errors"]
    assert escape_html_multiline(manual_update_commands(STEPS)) in message
    assert kwargs["detail"] == "solve failed"
    assert flow["relaunched"] == []


def test_an_install_that_cannot_locate_its_checkout_gets_generic_commands(
    flow, monkeypatch
):
    def unlocatable():
        raise EnvironmentUpdateError("No pixi workspace found")

    monkeypatch.setattr(environment_update_dialog, "locate_update_steps", unlocatable)

    environment_update_dialog.offer_environment_update("X", "pkg")

    [(message, _kwargs)] = flow["errors"]
    assert "pixi install" in message
    assert flow["ran"] == []
    assert flow["relaunched"] == []
