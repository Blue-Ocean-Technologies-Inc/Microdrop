"""End-to-end Redis-backed round-trip test for the PPT-8 droplet-check column.

Two tests:
  A. DropletDetectionResponder (in "succeed" mode) subscribes to a real
     Redis-backed router, receives DETECT_DROPLETS, and publishes
     DROPLETS_DETECTED with success + the right channel list.

  B. The DropletCheckDecisionDialogActor receives DROPLET_CHECK_DECISION_REQUEST,
     (with confirm mocked to return True and QTimer.singleShot bypassed so the
     Qt main-thread marshal runs synchronously on the worker thread), and
     publishes DROPLET_CHECK_DECISION_RESPONSE with choice="continue".

Skipped automatically by the parent conftest if Redis is not running.
Mirrors PPT-7's test_calibration_round_trip.py in fixture/helper conventions.
"""
import json
import time
from threading import Lock
from unittest.mock import patch

import dramatiq
import pytest

# Strip Prometheus middleware before anything else touches the broker —
# mirrors PPT-7's preamble.
from microdrop_utils.broker_server_helpers import remove_middleware_from_dramatiq_broker
remove_middleware_from_dramatiq_broker(
    middleware_name="dramatiq.middleware.prometheus",
    broker=dramatiq.get_broker(),
)

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from dropbot_controller.consts import DETECT_DROPLETS, DROPLETS_DETECTED
from dropbot_protocol_controls.consts import (
    DROPLET_CHECK_DECISION_REQUEST,
    DROPLET_CHECK_DECISION_RESPONSE,
    DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
)
from dropbot_protocol_controls.demos.droplet_detection_responder import (
    DropletDetectionResponder,
    DEMO_DROPLET_RESPONDER_ACTOR_NAME,
)
# Importing this module registers the @dramatiq.actor singleton at module
# load time (Task 9 pattern). Must happen after the broker is the RedisBroker
# (parent conftest ensures this before collection).
from dropbot_protocol_controls.services import droplet_check_decision_dialog_actor as _dialog_module  # noqa: F401


# ---------------------------------------------------------------------------
# Spy actor — captures (topic, message) pairs for both tests.
# Using a module-level @dramatiq.actor so it registers once per session,
# matching the pattern in test_voltage_frequency_protocol_round_trip.py.
# ---------------------------------------------------------------------------
RECEIVED_EVENTS = []
RECEIVED_LOCK = Lock()
SPY_ACTOR_NAME = "test_ppt8_droplet_check_round_trip_spy"


@dramatiq.actor(actor_name=SPY_ACTOR_NAME, queue_name="default")
def _spy_actor(message: str, topic: str):
    with RECEIVED_LOCK:
        RECEIVED_EVENTS.append((topic, message))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_for(condition_fn, timeout=5.0, poll=0.05):
    """Poll until condition_fn() returns True or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition_fn():
            return True
        time.sleep(poll)
    return False


# ---------------------------------------------------------------------------
# Fixture A: responder round-trip
# ---------------------------------------------------------------------------

@pytest.fixture
def responder_subscription(router_actor):
    """Wire the DropletDetectionResponder (succeed mode) + spy onto the
    real Redis router. Starts a Dramatiq Worker to drain the broker.
    Mirrors calibration_subscription from test_calibration_round_trip.py.
    """
    from dramatiq import Worker

    RECEIVED_EVENTS.clear()
    broker = dramatiq.get_broker()
    broker.flush_all()

    responder = DropletDetectionResponder(mode="succeed")
    # subscribe() wires DETECT_DROPLETS → responder and also wires the
    # executor listener topics — we're testing only the responder here so
    # that's fine; extra subscriptions don't hurt.
    responder.subscribe(router_actor)

    # Spy on DROPLETS_DETECTED so we can assert on the response.
    router_actor.message_router_data.add_subscriber_to_topic(
        topic=DROPLETS_DETECTED,
        subscribing_actor_name=SPY_ACTOR_NAME,
    )

    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        yield router_actor
    finally:
        worker.stop()
        # Remove spy subscription.
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=DROPLETS_DETECTED,
            subscribing_actor_name=SPY_ACTOR_NAME,
        )
        # Remove responder subscription (mirrors calibration cleanup).
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=DETECT_DROPLETS,
            subscribing_actor_name=DEMO_DROPLET_RESPONDER_ACTOR_NAME,
        )
        from dropbot_protocol_controls.consts import DROPLET_CHECK_DECISION_RESPONSE
        for topic in (DROPLETS_DETECTED, DROPLET_CHECK_DECISION_RESPONSE):
            router_actor.message_router_data.remove_subscriber_from_topic(
                topic=topic,
                subscribing_actor_name="pluggable_protocol_tree_executor_listener",
            )
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            subscribing_actor_name=DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        )


# ---------------------------------------------------------------------------
# Fixture B: dialog decision round-trip
# ---------------------------------------------------------------------------

@pytest.fixture
def decision_subscription(router_actor):
    """Wire the dialog actor's subscription + spy for the decision round-trip.
    The dialog actor's @dramatiq.actor was already registered at import time.
    """
    from dramatiq import Worker

    RECEIVED_EVENTS.clear()
    broker = dramatiq.get_broker()
    broker.flush_all()

    router_actor.message_router_data.add_subscriber_to_topic(
        topic=DROPLET_CHECK_DECISION_REQUEST,
        subscribing_actor_name=DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
    )
    router_actor.message_router_data.add_subscriber_to_topic(
        topic=DROPLET_CHECK_DECISION_RESPONSE,
        subscribing_actor_name=SPY_ACTOR_NAME,
    )

    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        yield router_actor
    finally:
        worker.stop()
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            subscribing_actor_name=DROPLET_CHECK_DECISION_LISTENER_ACTOR_NAME,
        )
        router_actor.message_router_data.remove_subscriber_from_topic(
            topic=DROPLET_CHECK_DECISION_RESPONSE,
            subscribing_actor_name=SPY_ACTOR_NAME,
        )


# ---------------------------------------------------------------------------
# Test A
# ---------------------------------------------------------------------------

def test_responder_replies_to_detect_droplets_with_succeed_mode(responder_subscription):
    """Verify the demo responder, when subscribed to a real Redis router,
    receives DETECT_DROPLETS and replies on DROPLETS_DETECTED with
    success=True and detected_channels matching the requested list."""
    publish_message(topic=DETECT_DROPLETS, message=json.dumps([1, 2, 3]))

    assert _wait_for(
        lambda: any(t == DROPLETS_DETECTED for t, _ in RECEIVED_EVENTS),
        timeout=5.0,
    ), "DROPLETS_DETECTED reply never arrived within 5s"

    with RECEIVED_LOCK:
        matches = [(t, m) for t, m in RECEIVED_EVENTS if t == DROPLETS_DETECTED]

    assert len(matches) >= 1
    topic, body = matches[-1]
    assert topic == DROPLETS_DETECTED
    parsed = json.loads(body)
    assert parsed["success"] is True
    assert parsed["detected_channels"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Test B
# ---------------------------------------------------------------------------

def test_decision_round_trip_continue(decision_subscription):
    """Publish DROPLET_CHECK_DECISION_REQUEST → mock confirm → True →
    verify DROPLET_CHECK_DECISION_RESPONSE arrives with choice='continue'."""
    with patch(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.confirm",
        return_value=True,
    ), patch(
        "dropbot_protocol_controls.services.droplet_check_decision_dialog_actor.QTimer.singleShot",
        side_effect=lambda delay, fn: fn(),
    ):
        publish_message(
            topic=DROPLET_CHECK_DECISION_REQUEST,
            message=json.dumps({
                "step_uuid": "test-uuid-42",
                "expected": [1, 2],
                "detected": [1],
                "missing": [2],
            }),
        )

        assert _wait_for(
            lambda: any(t == DROPLET_CHECK_DECISION_RESPONSE for t, _ in RECEIVED_EVENTS),
            timeout=5.0,
        ), "DROPLET_CHECK_DECISION_RESPONSE never arrived within 5s"

    with RECEIVED_LOCK:
        matches = [(t, m) for t, m in RECEIVED_EVENTS
                   if t == DROPLET_CHECK_DECISION_RESPONSE]

    assert len(matches) >= 1
    topic, body = matches[-1]
    assert topic == DROPLET_CHECK_DECISION_RESPONSE
    parsed = json.loads(body)
    assert parsed == {"step_uuid": "test-uuid-42", "choice": "continue"}
