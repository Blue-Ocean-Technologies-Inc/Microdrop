"""End-to-end test: a 3-step Video/Capture/Record protocol publishes
the expected sequence of camera-active / screen-capture / screen-recording
messages to the demo responder, and the responder echoes the expected
synthetic media_captured acks.

Requires a running Redis server on localhost:6379.
"""
import json
import time
from threading import Lock

import dramatiq
import pytest

# Strip Prometheus middleware before importing anything that uses the broker.
from microdrop_utils.broker_server_helpers import remove_middleware_from_dramatiq_broker
remove_middleware_from_dramatiq_broker(
    middleware_name="dramatiq.middleware.prometheus",
    broker=dramatiq.get_broker(),
)

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.execution.executor import ProtocolExecutor
from pluggable_protocol_tree.models.row_manager import RowManager

from device_viewer.consts import (
    DEVICE_VIEWER_CAMERA_ACTIVE,
    DEVICE_VIEWER_SCREEN_CAPTURE,
    DEVICE_VIEWER_SCREEN_RECORDING,
    DEVICE_VIEWER_MEDIA_CAPTURED,
)
from video_protocol_controls.protocol_columns import (
    make_video_column, make_record_column, make_capture_column,
)
from video_protocol_controls.demos.camera_responder import (
    DEMO_CAMERA_RESPONDER_ACTOR_NAME, subscribe_demo_responder,
)


# ---------------------------------------------------------------------------
# Spy actor — records every relevant (timestamp, topic, message) triple.
# Module-level so the @dramatiq.actor decorator only fires once per session.
# ---------------------------------------------------------------------------

EVENT_LOG = []
EVENT_LOG_LOCK = Lock()
SPY_ACTOR_NAME = "test_ppt6_round_trip_spy"


@dramatiq.actor(actor_name=SPY_ACTOR_NAME, queue_name="default")
def _record_event(message: str, topic: str, timestamp: float = None):
    with EVENT_LOG_LOCK:
        EVENT_LOG.append((time.monotonic(), topic, message))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def setup_responder_and_spy(router_actor):
    """Subscribe the camera demo responder + spy; clean up after.

    Subscribes:
      - DEMO_CAMERA_RESPONDER_ACTOR_NAME to the three request topics
        (via subscribe_demo_responder, which mirrors the demo window's
        routing_setup).
      - SPY_ACTOR_NAME to all four topics (3 requests + 1 ack) so we
        can assert both directions of the demo conversation.

    PPT-6 is fire-and-forget — no executor-listener subscription is
    needed (unlike PPT-4's voltage/frequency columns which use wait_for).
    """
    from dramatiq import Worker

    EVENT_LOG.clear()

    broker = dramatiq.get_broker()
    broker.flush_all()

    router = router_actor

    # Wire the three request topics to the in-process demo responder.
    subscribe_demo_responder(router)

    # Spy on all four topics so we can assert both the outbound publishes
    # and the responder's inbound acks.
    spy_topics = (
        DEVICE_VIEWER_CAMERA_ACTIVE,
        DEVICE_VIEWER_SCREEN_CAPTURE,
        DEVICE_VIEWER_SCREEN_RECORDING,
        DEVICE_VIEWER_MEDIA_CAPTURED,
    )
    for topic in spy_topics:
        router.message_router_data.add_subscriber_to_topic(
            topic=topic,
            subscribing_actor_name=SPY_ACTOR_NAME,
        )

    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        yield router
    finally:
        worker.stop()
        # Unsubscribe everything to avoid subscription bleed into next test.
        for topic in spy_topics:
            router.message_router_data.remove_subscriber_from_topic(
                topic=topic,
                subscribing_actor_name=SPY_ACTOR_NAME,
            )
        for topic in (
            DEVICE_VIEWER_CAMERA_ACTIVE,
            DEVICE_VIEWER_SCREEN_CAPTURE,
            DEVICE_VIEWER_SCREEN_RECORDING,
        ):
            router.message_router_data.remove_subscriber_from_topic(
                topic=topic,
                subscribing_actor_name=DEMO_CAMERA_RESPONDER_ACTOR_NAME,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_columns():
    """Return the standard column set for PPT-6 integration tests."""
    return [
        make_type_column(),
        make_id_column(),
        make_name_column(),
        make_duration_column(),
        make_video_column(),
        make_record_column(),
        make_capture_column(),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_three_step_video_protocol_publishes_expected_sequence(
    setup_responder_and_spy,
):
    """A 3-step Video/Capture/Record protocol produces the exact publish
    sequence described in PPT-6 Task 9:

    Step 1 (Video=on, Capture=off, Record=off)
        → 1 camera-active publish ("true")
    Step 2 (Video=on, Capture=on, Record=on)   [Video unchanged — no publish]
        → 1 screen-capture publish (JSON with step metadata)
        → 1 screen-recording publish (action="start", JSON with step metadata)
    Step 3 (all off)
        → 1 camera-active publish ("false")
        → 1 screen-recording publish (action="stop")   [no capture publish]

    Total: 5 control publishes on the three request topics.

    The demo responder also echoes:
        → 1 media_captured ack (type="image") for the capture publish
        → 1 media_captured ack (type="video") for the record-stop publish

    Total: 2 ack publishes on DEVICE_VIEWER_MEDIA_CAPTURED.
    """
    rm = RowManager(columns=_build_columns())
    rm.add_step(values={
        "name": "S1",
        "duration_s": 0.05,
        "video": True,
        "capture": False,
        "record": False,
    })
    rm.add_step(values={
        "name": "S2",
        "duration_s": 0.05,
        "video": True,
        "capture": True,
        "record": True,
    })
    rm.add_step(values={
        "name": "S3",
        "duration_s": 0.05,
        "video": False,
        "capture": False,
        "record": False,
    })

    executor = ProtocolExecutor(row_manager=rm)
    executor.start()
    finished = executor.wait(timeout=15.0)
    assert finished, "Executor did not finish within 15 s"

    # Brief settle so any in-flight ack messages (responder → Redis → spy)
    # have time to land before we read the log.
    time.sleep(0.3)

    with EVENT_LOG_LOCK:
        events = list(EVENT_LOG)

    # Group messages by topic for easy assertions.
    by_topic: dict[str, list[str]] = {}
    for _, topic, message in events:
        by_topic.setdefault(topic, []).append(message)

    # --- Camera: exactly "true" then "false" ---
    cam = by_topic.get(DEVICE_VIEWER_CAMERA_ACTIVE, [])
    assert cam == ["true", "false"], (
        f"Expected camera-active publishes ['true', 'false'], got: {cam}"
    )

    # --- Capture: one publish in Step 2 only ---
    capture = by_topic.get(DEVICE_VIEWER_SCREEN_CAPTURE, [])
    assert len(capture) == 1, (
        f"Expected exactly 1 screen-capture publish, got: {capture}"
    )
    capture_payload = json.loads(capture[0])
    assert capture_payload["step_description"] == "S2", (
        f"Capture payload step_description should be 'S2', got: {capture_payload}"
    )

    # --- Record: start (Step 2) then stop (Step 3) ---
    record = by_topic.get(DEVICE_VIEWER_SCREEN_RECORDING, [])
    assert len(record) == 2, (
        f"Expected 2 screen-recording publishes (start + stop), got: {record}"
    )
    start_payload = json.loads(record[0])
    stop_payload = json.loads(record[1])
    assert start_payload["action"] == "start", (
        f"First record publish should be action='start', got: {start_payload}"
    )
    assert start_payload["step_description"] == "S2", (
        f"Start payload step_description should be 'S2', got: {start_payload}"
    )
    assert stop_payload == {"action": "stop"}, (
        f"Stop payload should be exactly {{action: stop}}, got: {stop_payload}"
    )

    # --- Media-captured acks from the demo responder ---
    # Responder publishes one image ack (for screen-capture) and one video ack
    # (for record-stop). Order is non-deterministic so we assert on the set.
    acks = by_topic.get(DEVICE_VIEWER_MEDIA_CAPTURED, [])
    assert len(acks) == 2, (
        f"Expected 2 media_captured acks from the demo responder, got: {acks}"
    )
    ack_types = sorted(json.loads(a)["type"] for a in acks)
    assert ack_types == ["image", "video"], (
        f"Expected ack types ['image', 'video'], got: {ack_types}"
    )


def test_video_only_protocol_publishes_no_capture_or_record(
    setup_responder_and_spy,
):
    """A single-step protocol with Video=on only must publish exactly one
    camera-active='true' (at step start) and one camera-active='false'
    (at protocol end from on_protocol_end cleanup), with no capture or
    record publishes and no media_captured acks from the responder."""
    rm = RowManager(columns=_build_columns())
    rm.add_step(values={
        "name": "VideoOnly",
        "duration_s": 0.05,
        "video": True,
        "capture": False,
        "record": False,
    })

    executor = ProtocolExecutor(row_manager=rm)
    executor.start()
    finished = executor.wait(timeout=15.0)
    assert finished, "Executor did not finish within 15 s"

    time.sleep(0.3)

    with EVENT_LOG_LOCK:
        events = list(EVENT_LOG)

    by_topic: dict[str, list[str]] = {}
    for _, topic, message in events:
        by_topic.setdefault(topic, []).append(message)

    # Camera on then off (on_protocol_end cleans up).
    cam = by_topic.get(DEVICE_VIEWER_CAMERA_ACTIVE, [])
    assert cam == ["true", "false"], (
        f"Expected ['true', 'false'] for camera-active, got: {cam}"
    )

    # No capture or record publishes.
    assert DEVICE_VIEWER_SCREEN_CAPTURE not in by_topic, (
        f"No capture publish expected, got: {by_topic.get(DEVICE_VIEWER_SCREEN_CAPTURE)}"
    )
    assert DEVICE_VIEWER_SCREEN_RECORDING not in by_topic, (
        f"No record publish expected, got: {by_topic.get(DEVICE_VIEWER_SCREEN_RECORDING)}"
    )

    # No acks from the responder (camera-only produces none).
    assert DEVICE_VIEWER_MEDIA_CAPTURED not in by_topic, (
        f"No media_captured ack expected, got: {by_topic.get(DEVICE_VIEWER_MEDIA_CAPTURED)}"
    )
