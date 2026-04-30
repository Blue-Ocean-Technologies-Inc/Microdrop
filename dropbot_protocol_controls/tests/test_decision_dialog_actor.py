"""Tests for DropletCheckDecisionDialogActor.

The actor uses a Qt Signal + QueuedConnection to marshal from the
Dramatiq worker thread to the main thread. Tests bypass that hop by
patching the dispatcher's `request_dialog.emit` to invoke the slot
directly (synchronously, on the test thread). This keeps tests off
the Qt event loop while still exercising the real
`_on_request_dialog` slot logic (confirm + publish).
"""

import json
from unittest.mock import patch

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
def synchronous_dispatch(monkeypatch):
    """Replace `_dispatch_to_main_thread` with a direct call into the
    dispatcher's slot, so tests can read captured_publishes /
    patched_confirm immediately after listener_actor_routine returns
    without needing a Qt event loop. (PySide6 Signal.emit is read-only,
    so we hook one level above the signal instead of patching emit.)"""
    from dropbot_protocol_controls.services.droplet_check_decision_dialog_actor import (
        DropletCheckDecisionDialogActor,
    )

    def _direct_dispatch(self, payload):
        self.dispatcher._on_request_dialog(payload)

    monkeypatch.setattr(
        DropletCheckDecisionDialogActor,
        "_dispatch_to_main_thread",
        _direct_dispatch,
    )


def test_confirm_returning_true_publishes_continue(
    patched_confirm, captured_publishes, synchronous_dispatch,
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
    patched_confirm, captured_publishes, synchronous_dispatch,
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
    patched_confirm, captured_publishes, synchronous_dispatch,
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
    patched_confirm, captured_publishes, synchronous_dispatch,
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
    patched_confirm, captured_publishes, synchronous_dispatch,
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
    patched_confirm, captured_publishes, synchronous_dispatch, caplog,
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
    patched_confirm, captured_publishes, synchronous_dispatch,
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
