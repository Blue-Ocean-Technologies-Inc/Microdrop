# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The hub controller's requests: one run per Start, an abort that stops
whatever runs, and the confirm before the motor test moves axes."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.api import NO, YES

# Local imports.
from ..consts import SelfTestAbortRequest, SelfTestPreflight, SelfTestProgress
from ..controllers import self_tests_controller
from ..models.self_tests_model import SelfTestHubModel

pytest.importorskip("dropbot_portable.self_test")

SHORTS_TEST = "test_shorts"
MOTORS_TEST = "test_motors"


class RecordingPublisher:
    """Stands in for a ValidatedTopicPublisher, validating like it does."""

    def __init__(self, validator_class):
        self.validator_class = validator_class
        self.published = []

    def publish(self, message):
        self.published.append(self.validator_class(**message))


@pytest.fixture
def publishers(monkeypatch):
    from ..consts import SelfTestRunRequest

    run = RecordingPublisher(SelfTestRunRequest)
    abort = RecordingPublisher(SelfTestAbortRequest)
    monkeypatch.setattr(self_tests_controller, "self_test_run_publisher", run)
    monkeypatch.setattr(self_tests_controller, "self_test_abort_publisher", abort)

    return run, abort


@pytest.fixture
def model():
    model = SelfTestHubModel()
    model.request_preflight([SHORTS_TEST])
    model.apply_preflight(SelfTestPreflight(tray_in=True, board_detected=True))

    return model


@pytest.fixture
def controller(model):
    """The controller, held for the test: its observers die with it."""
    return self_tests_controller.SelfTestHubController(model=model)


def test_a_repeated_start_publishes_one_run(controller, publishers):
    run, _abort = publishers
    model = controller.model

    model.preflight.start_button = True
    model.preflight.start_button = True

    assert [request.run_id for request in run.published] == [model.run_id]


def test_abort_publishes_an_empty_run_id(controller, publishers):
    _run, abort = publishers
    model = controller.model
    model.preflight.start_button = True
    model.apply_progress(SelfTestProgress(run_id=model.run_id, phase="start", total=1))

    model.abort_button = True

    assert [request.run_id for request in abort.published] == [""]
    assert model.aborting


@pytest.fixture
def answers(monkeypatch):
    """Answer the motor-moves confirm with each queued reply in turn."""
    queued = []
    asked = []

    def confirm(parent, message, title=""):
        asked.append(title)

        return queued.pop(0)

    monkeypatch.setattr(self_tests_controller, "confirm", confirm)

    return queued, asked


@pytest.mark.parametrize("answer, preflight", [(YES, True), (NO, False)])
def test_motor_moves_ask_first(answers, answer, preflight):
    queued, asked = answers
    queued.append(answer)
    model = SelfTestHubModel()
    controller = self_tests_controller.SelfTestHubController(model=model)
    model.parameters.motors_moves = True

    for row in model.rows:
        row.selected = row.name == MOTORS_TEST

    model.run_selected_button = True

    assert asked and controller.model.preflight_pending is preflight


def test_a_read_only_motor_test_does_not_ask(answers):
    _queued, asked = answers
    model = SelfTestHubModel()
    controller = self_tests_controller.SelfTestHubController(model=model)

    model.run_all_button = True

    assert not asked and controller.model.preflight_pending
