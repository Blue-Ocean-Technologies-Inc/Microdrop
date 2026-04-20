from unittest.mock import patch
import pytest

from protocol_grid.services.message_listener import MessageListener
from protocol_grid.models.step_params_commit import StepParamsCommitMessage
from protocol_grid.consts import STEP_PARAMS_COMMIT


@pytest.fixture
def listener():
    with patch(
        "protocol_grid.services.message_listener.generate_class_method_dramatiq_listener_actor"
    ):
        yield MessageListener()


def test_listener_emits_step_params_commit_received(listener):
    msg = StepParamsCommitMessage(
        step_id="uid-1",
        duration=2.0, repetitions=3, repeat_duration=0.0,
        trail_length=2, trail_overlay=1,
        soft_start=True, soft_terminate=False,
    )

    received = []
    listener.signal_emitter.step_params_commit_received.connect(
        lambda m: received.append(m)
    )

    listener.listener_actor_routine(msg.serialize(), STEP_PARAMS_COMMIT)

    assert len(received) == 1
    assert received[0] == msg
