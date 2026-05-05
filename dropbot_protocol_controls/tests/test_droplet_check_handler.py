"""Tests for DropletCheckHandler.on_post_step.

We mock ctx.wait_for and intercept publish_message via monkeypatch so the
tests don't need a real broker/listener. Round-trip via real Dramatiq is
covered in tests_with_redis_server_need/test_droplet_check_round_trip.py.
"""

import json
from unittest.mock import MagicMock

import pytest
from traits.api import Bool, HasTraits, List, Str

from dropbot_protocol_controls.protocol_columns.droplet_check_column import (
    DropletCheckHandler,
)


# ---------- fixtures ----------

class _FakeRow(HasTraits):
    uuid                 = Str("step-uuid-1")
    check_droplets       = Bool(True)
    electrodes = List(Str)
    routes               = List


class _FakePauseEvent:
    """Stand-in for pluggable_protocol_tree.execution.events.PauseEvent."""
    def __init__(self):
        self._set = False
    def set(self): self._set = True
    def is_set(self): return self._set
    def clear(self): self._set = False


class _FakeProtocolCtx:
    def __init__(self, electrode_to_channel=None, pause_event=None,
                 qsignals=None):
        self.scratch = {"electrode_to_channel": electrode_to_channel or {}}
        # Mirrors the real ProtocolContext traits the executor populates.
        self.pause_event = pause_event if pause_event is not None else _FakePauseEvent()
        self.qsignals = qsignals  # None for tests that don't care about UI signals


class _FakeStepCtx:
    def __init__(self, protocol):
        self.protocol = protocol
        # wait_for tests set this to a function returning the next ack.
        self._wait_responses = []  # list of (topic, payload-or-exception)
        self.wait_for_calls = []   # for inspection

    def wait_for(self, topic, timeout=5.0, predicate=None):
        self.wait_for_calls.append((topic, timeout, predicate))
        if not self._wait_responses:
            raise AssertionError(f"unexpected wait_for({topic!r})")
        next_topic, value = self._wait_responses.pop(0)
        assert next_topic == topic, (
            f"test expected wait_for({next_topic!r}) but got wait_for({topic!r})"
        )
        if isinstance(value, Exception):
            raise value
        # Apply predicate filter if test set one (matches real wait_for).
        if predicate is not None:
            assert predicate(value), (
                f"predicate rejected payload {value!r} — test setup mismatch"
            )
        return value


@pytest.fixture
def published(monkeypatch):
    """Intercepts publish_message; returns a list of (topic, message) tuples
    captured during the test."""
    calls = []
    def _capture(topic, message):
        calls.append((topic, message))
    monkeypatch.setattr(
        "dropbot_protocol_controls.protocol_columns.droplet_check_column.publish_message",
        _capture,
    )
    return calls


# ---------- short-circuit paths ----------

def test_column_off_short_circuits_without_publishing(published):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=False, electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))

    result = handler.on_post_step(row, ctx)

    assert result is None
    assert published == []                  # no publish at all
    assert ctx.wait_for_calls == []         # no wait_for either


def test_no_expected_channels_short_circuits_without_publishing(published):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True)     # no electrodes/routes
    ctx = _FakeStepCtx(_FakeProtocolCtx({}))

    result = handler.on_post_step(row, ctx)

    assert result is None
    assert published == []
    assert ctx.wait_for_calls == []


def test_missing_electrode_to_channel_in_scratch_treated_as_empty(published):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True, electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx())  # no scratch entry

    result = handler.on_post_step(row, ctx)

    # 'e1' can't map to a channel → expected is empty → short-circuit.
    assert result is None
    assert published == []


# ---------- happy path ----------

def test_happy_path_publishes_detect_and_returns_on_success_match(published):
    handler = DropletCheckHandler()
    row = _FakeRow(
        check_droplets=True,
        electrodes=["e1", "e2"],
    )
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e2": 2}))
    ctx._wait_responses = [(
        # backend returns BOTH expected channels → no failure path
        "dropbot/signals/drops_detected",
        json.dumps({"success": True, "detected_channels": [1, 2], "error": ""}),
    )]

    result = handler.on_post_step(row, ctx)

    assert result is None
    # one publish: the DETECT_DROPLETS request
    assert len(published) == 1
    topic, payload = published[0]
    assert topic == "dropbot/requests/detect_droplets"
    assert json.loads(payload) == [1, 2]
    # one wait_for, on the response topic, with backend timeout
    assert ctx.wait_for_calls == [(
        "dropbot/signals/drops_detected", 12.0, None
    )]


def test_detect_payload_is_list_of_int_channels_not_electrode_ids(published):
    # Critical wire-format check: backend expects List[int].
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True, electrodes=["e3", "e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e3": 3}))
    ctx._wait_responses = [(
        "dropbot/signals/drops_detected",
        json.dumps({"success": True, "detected_channels": [1, 3], "error": ""}),
    )]

    handler.on_post_step(row, ctx)

    sent = json.loads(published[0][1])
    assert sent == [1, 3]                   # sorted, ints
    assert all(isinstance(c, int) for c in sent)


# ---------- timeout / error paths ----------

def test_backend_error_surfaces_through_failure_dialog(published, caplog):
    """Backend success=False is surfaced to the user via the same
    decision dialog as a missing-channel failure: the error message
    becomes the `detected` payload entry so it shows up in the dialog
    body. The user can then choose Continue or Stay Paused. (Earlier
    behavior was to silently log + return; user-visible was preferred.)"""
    from dropbot_protocol_controls.consts import DROPLET_CHECK_DECISION_RESPONSE
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True, electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": False, "detected_channels": [], "error": "no proxy"})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "continue"})),
    ]

    with caplog.at_level("WARNING"):
        handler.on_post_step(row, ctx)

    # Logs the error.
    assert any("no proxy" in r.message.lower() for r in caplog.records), \
        f"expected error in log; got: {[r.message for r in caplog.records]}"
    # Publishes DETECT_DROPLETS and DECISION_REQUEST (with error in `detected`).
    assert len(published) == 2
    request_body = json.loads(published[1][1])
    assert any("no proxy" in str(d) for d in request_body["detected"]), \
        f"expected backend error in dialog payload's `detected`; got {request_body['detected']!r}"


def test_wait_for_timeout_logs_and_returns(published, caplog):
    handler = DropletCheckHandler()
    row = _FakeRow(check_droplets=True, electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))
    ctx._wait_responses = [(
        "dropbot/signals/drops_detected",
        TimeoutError("simulated 12s timeout"),
    )]

    with caplog.at_level("WARNING"):
        result = handler.on_post_step(row, ctx)

    assert result is None
    # The detect was published before the wait timed out.
    assert len(published) == 1
    assert any("timed out" in r.message.lower() for r in caplog.records), \
        f"expected timeout log; got: {[r.message for r in caplog.records]}"


# ---------- failure path: UI round-trip ----------

import pytest
from dropbot_protocol_controls.consts import (
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
)


def test_missing_channels_publishes_decision_request_with_payload(published):
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True,
                   electrodes=["e1", "e2", "e3"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e2": 2, "e3": 3}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [1, 3], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "continue"})),
    ]

    handler.on_post_step(row, ctx)

    assert len(published) == 2
    detect_topic, _      = published[0]
    request_topic, body  = published[1]
    assert detect_topic  == "dropbot/requests/detect_droplets"
    assert request_topic == DROPLET_CHECK_DECISION_REQUEST

    parsed = json.loads(body)
    assert parsed["step_uuid"] == "abc"
    assert parsed["expected"]  == [1, 2, 3]
    assert parsed["detected"]  == [1, 3]
    assert parsed["missing"]   == [2]


def test_user_chooses_continue_returns_normally(published):
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True,
                   electrodes=["e1", "e2"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e2": 2}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [1], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "continue"})),
    ]

    result = handler.on_post_step(row, ctx)

    assert result is None                       # no exception, no return value
    assert len(ctx.wait_for_calls) == 2         # one for ack, one for decision


def test_user_chooses_pause_sets_pause_event_and_returns(published):
    """'pause' must set the executor's pause_event (effective at the
    next step boundary) and return normally — NOT raise AbortError,
    which would tear down the protocol entirely. This step's lifecycle
    completes cleanly; the next step is what gets blocked."""
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True,
                   electrodes=["e1", "e2"])
    pause_event = _FakePauseEvent()
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1, "e2": 2},
                                         pause_event=pause_event))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [1], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "pause"})),
    ]

    # Returns normally (no exception).
    result = handler.on_post_step(row, ctx)
    assert result is None
    # pause_event was set — the executor will block at the next step.
    assert pause_event.is_set() is True


def test_user_chooses_pause_with_no_pause_event_returns_silently(published):
    """Defensive: if pause_event isn't on the protocol context (older
    framework version, custom test fixture), 'pause' just returns
    without crashing. Better to over-continue than to crash mid-protocol."""
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True,
                   electrodes=["e1", "e2"])
    proto_ctx = _FakeProtocolCtx({"e1": 1, "e2": 2})
    proto_ctx.pause_event = None  # explicitly absent
    ctx = _FakeStepCtx(proto_ctx)
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [1], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "pause"})),
    ]

    result = handler.on_post_step(row, ctx)
    assert result is None


def test_decision_wait_uses_predicate_filtering_by_step_uuid(published):
    # Confirm the predicate accepts matching step_uuid and rejects others.
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="THIS_STEP", check_droplets=True,
                   electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "THIS_STEP", "choice": "continue"})),
    ]

    handler.on_post_step(row, ctx)

    # Inspect the predicate used for the second wait_for call.
    _, _, predicate = ctx.wait_for_calls[1]
    assert predicate is not None
    # Matching uuid → True; mismatched → False.
    assert predicate(json.dumps({"step_uuid": "THIS_STEP", "choice": "x"})) is True
    assert predicate(json.dumps({"step_uuid": "OTHER_STEP", "choice": "x"})) is False


def test_decision_wait_uses_24h_timeout(published):
    handler = DropletCheckHandler()
    row = _FakeRow(uuid="abc", check_droplets=True, electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx({"e1": 1}))
    ctx._wait_responses = [
        ("dropbot/signals/drops_detected",
         json.dumps({"success": True, "detected_channels": [], "error": ""})),
        (DROPLET_CHECK_DECISION_RESPONSE,
         json.dumps({"step_uuid": "abc", "choice": "continue"})),
    ]

    handler.on_post_step(row, ctx)

    _, timeout, _ = ctx.wait_for_calls[1]
    assert timeout == 86_400.0                  # spec § 4 design note
