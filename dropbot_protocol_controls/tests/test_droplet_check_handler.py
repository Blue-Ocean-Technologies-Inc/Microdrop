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
    activated_electrodes = List(Str)
    routes               = List


class _FakeProtocolCtx:
    def __init__(self, electrode_to_channel=None):
        self.scratch = {"electrode_to_channel": electrode_to_channel or {}}


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
    row = _FakeRow(check_droplets=False, activated_electrodes=["e1"])
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
    row = _FakeRow(check_droplets=True, activated_electrodes=["e1"])
    ctx = _FakeStepCtx(_FakeProtocolCtx())  # no scratch entry

    result = handler.on_post_step(row, ctx)

    # 'e1' can't map to a channel → expected is empty → short-circuit.
    assert result is None
    assert published == []
