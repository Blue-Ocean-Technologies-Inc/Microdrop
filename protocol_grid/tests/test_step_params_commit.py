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


from protocol_grid.protocol_grid_helpers import extract_execution_params


def test_extract_execution_params_happy_path():
    parameters = {
        "Duration": "1.5",
        "Repetitions": "3",
        "Repeat Duration": "0.0",
        "Trail Length": "2",
        "Trail Overlay": "1",
        "Ramp Up": "1",
        "Ramp Dn": "0",
        "Voltage": "100",  # should be ignored
    }
    result = extract_execution_params(parameters)
    assert result == {
        "duration": 1.5,
        "repetitions": 3,
        "repeat_duration": 0.0,
        "trail_length": 2,
        "trail_overlay": 1,
        "soft_start": True,
        "soft_terminate": False,
    }


def test_extract_execution_params_missing_keys_use_defaults():
    # If a key is absent, fall back to step_defaults string, then cast.
    result = extract_execution_params({})
    assert result["duration"] == 1.0
    assert result["repetitions"] == 1
    assert result["repeat_duration"] == 1.0
    assert result["trail_length"] == 1
    assert result["trail_overlay"] == 0
    assert result["soft_start"] is False
    assert result["soft_terminate"] is False
