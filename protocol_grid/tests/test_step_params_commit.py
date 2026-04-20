import pytest
from pydantic import ValidationError

from protocol_grid.models.step_params_commit import StepParamsCommitMessage


def _valid_kwargs():
    return dict(
        step_id="abc123",
        duration=1.5,
        repetitions=3,
        repeat_duration=0.0,
        trail_length=2,
        trail_overlay=1,
        soft_start=True,
        soft_terminate=False,
    )


def test_step_params_commit_roundtrip():
    msg = StepParamsCommitMessage(**_valid_kwargs())
    rebuilt = StepParamsCommitMessage.deserialize(msg.serialize())
    assert rebuilt == msg


def test_step_params_commit_rejects_missing_field():
    kwargs = _valid_kwargs()
    del kwargs["duration"]
    with pytest.raises(ValidationError):
        StepParamsCommitMessage(**kwargs)
