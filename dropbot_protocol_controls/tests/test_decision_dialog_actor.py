"""Tests for DropletCheckDecisionDialogActor.

We patch QTimer.singleShot to invoke immediately (no Qt event loop in
tests) and patch pyface_wrapper.confirm to return a controllable bool."""

import json
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def patched_confirm():
    with patch(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.confirm"
    ) as mock_confirm:
        yield mock_confirm


@pytest.fixture
def captured_publishes(monkeypatch):
    calls = []
    def _capture(topic, message):
        calls.append((topic, message))
    monkeypatch.setattr(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.publish_message",
        _capture,
    )
    return calls


@pytest.fixture
def immediate_singleshot(monkeypatch):
    """Replace QTimer.singleShot(delay, fn) with an immediate fn() call so
    tests don't need a running Qt event loop."""
    monkeypatch.setattr(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.QTimer",
        MagicMock(singleShot=lambda delay, fn: fn()),
    )


def test_confirm_returning_true_publishes_continue(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    from dropbot_protocol_controls.consts import DROPLET_CHECK_DECISION_RESPONSE

    patched_confirm.return_value = True

    actor = DropletCheckDecisionDialogActor()
    payload = {"step_uuid": "abc", "expected": [1, 2], "detected": [1], "missing": [2]}
    actor.listener_actor_routine(json.dumps(payload), topic="ignored")

    assert len(captured_publishes) == 1
    topic, body = captured_publishes[0]
    assert topic == DROPLET_CHECK_DECISION_RESPONSE
    parsed = json.loads(body)
    assert parsed == {"step_uuid": "abc", "choice": "continue"}


def test_confirm_returning_false_publishes_pause(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    from dropbot_protocol_controls.consts import DROPLET_CHECK_DECISION_RESPONSE

    patched_confirm.return_value = False

    actor = DropletCheckDecisionDialogActor()
    payload = {"step_uuid": "abc", "expected": [1, 2], "detected": [], "missing": [1, 2]}
    actor.listener_actor_routine(json.dumps(payload), topic="ignored")

    topic, body = captured_publishes[0]
    parsed = json.loads(body)
    assert parsed == {"step_uuid": "abc", "choice": "pause"}


def test_dialog_message_includes_expected_detected_missing(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    patched_confirm.return_value = True

    actor = DropletCheckDecisionDialogActor()
    payload = {"step_uuid": "abc", "expected": [1, 2, 3], "detected": [1, 3], "missing": [2]}
    actor.listener_actor_routine(json.dumps(payload), topic="ignored")

    # Inspect the message string passed to confirm()
    args, kwargs = patched_confirm.call_args
    message = kwargs.get("message") or (args[1] if len(args) >= 2 else "")
    assert "1, 2, 3" in message    # expected
    assert "1, 3"    in message    # detected
    assert "2"       in message    # missing


def test_step_uuid_round_trips_through_dialog(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    patched_confirm.return_value = True

    actor = DropletCheckDecisionDialogActor()
    actor.listener_actor_routine(
        json.dumps({"step_uuid": "step-xyz-789",
                    "expected": [1], "detected": [], "missing": [1]}),
        topic="ignored",
    )

    parsed = json.loads(captured_publishes[0][1])
    assert parsed["step_uuid"] == "step-xyz-789"


def test_listener_name_is_pptN_free():
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    actor = DropletCheckDecisionDialogActor()
    assert actor.listener_name == "droplet_check_decision_listener"


def test_payload_missing_step_uuid_is_dropped_no_dialog_shown(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    """Schema guard: a JSON-valid payload missing 'step_uuid' must be
    dropped (warning logged, no dialog, no response published). Otherwise
    the worker would crash on payload['step_uuid'] and the column
    handler's wait_for would hang for 24h."""
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )

    actor = DropletCheckDecisionDialogActor()
    # Valid JSON, but no 'step_uuid' key.
    actor.listener_actor_routine(
        json.dumps({"expected": [1, 2], "detected": [], "missing": [1, 2]}),
        topic="ignored",
    )

    # No dialog opened, no response published.
    patched_confirm.assert_not_called()
    assert captured_publishes == []


def test_payload_missing_other_required_key_is_dropped(
    patched_confirm, captured_publishes, immediate_singleshot, caplog,
):
    """Same guard for other required keys (expected/detected/missing).
    Verifies the warning log mentions which key is missing."""
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )
    import logging

    actor = DropletCheckDecisionDialogActor()
    with caplog.at_level(logging.WARNING):
        # Valid JSON, has step_uuid but missing 'missing'.
        actor.listener_actor_routine(
            json.dumps({"step_uuid": "abc", "expected": [1], "detected": []}),
            topic="ignored",
        )

    patched_confirm.assert_not_called()
    assert captured_publishes == []
    # Warning should mention the missing key.
    assert any("missing" in r.message for r in caplog.records), (
        f"expected log to mention missing key; got: {[r.message for r in caplog.records]}"
    )


def test_malformed_json_is_dropped_no_dialog_shown(
    patched_confirm, captured_publishes, immediate_singleshot,
):
    """Pre-existing JSON guard verified end-to-end: not just no crash,
    but no Qt scheduling and no response."""
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )

    actor = DropletCheckDecisionDialogActor()
    actor.listener_actor_routine("{not valid json", topic="ignored")

    patched_confirm.assert_not_called()
    assert captured_publishes == []
