"""End-to-end Redis round-trip tests for DeviceViewerSyncController.

Design notes
------------
The Dramatiq actor registered for SYNC_LISTENER_NAME is session-scoped:
Dramatiq raises ValueError on duplicate actor names, and
generate_class_method_dramatiq_listener_actor() silently skips re-registration
(returning None) when the name is already taken. Therefore we create ONE
controller + actor for the session and reset its mutable state between tests.
"""

import time

import dramatiq
import pytest
from dramatiq import Worker

from device_viewer.consts import (
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    DEVICE_VIEWER_STATE_CHANGED,
    PROTOCOL_RUNNING,
)
from device_viewer.models.messages import (
    DeviceViewerMessageModel, GeometryChangedMessage,
)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import (
    DeviceViewerSyncController,
    SYNC_ACTOR_TOPIC_DICT,
    SYNC_LISTENER_NAME,
)


def _make_manager():
    return RowManager(columns=[
        make_name_column(),
        make_electrodes_column(),
        make_routes_column(),
    ])


@pytest.fixture(scope="session")
def dv_sync_ctrl():
    """One DeviceViewerSyncController + actor for the whole session.

    The actor is registered against SYNC_LISTENER_NAME exactly once. Bridge
    signals are wired directly (no tree_widget needed) so the Qt-thread
    handlers fire when a Dramatiq worker dispatches a message.
    """
    manager = _make_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    # Wire bridge signals directly (attach() is for the full widget lifecycle).
    ctrl.bridge.geometry_changed.connect(ctrl._on_geometry_qt)
    ctrl.bridge.dv_state_received.connect(ctrl._on_dv_state_qt)
    ctrl.bridge.protocol_running_changed.connect(ctrl._on_protocol_running_qt)
    return ctrl


@pytest.fixture(autouse=True)
def reset_ctrl_state(dv_sync_ctrl):
    """Reset mutable controller state before each test."""
    dv_sync_ctrl._free_mode_stash = None
    dv_sync_ctrl._protocol_running = False
    dv_sync_ctrl._channel_to_id_cache = {}
    dv_sync_ctrl.row_manager.protocol_metadata.clear()
    yield


@pytest.fixture
def subscribed_router(router_actor):
    """Subscribe the sync controller's actor to the router for this test."""
    for topic in SYNC_ACTOR_TOPIC_DICT[SYNC_LISTENER_NAME]:
        router_actor.message_router_data.add_subscriber_to_topic(
            topic=topic, subscribing_actor_name=SYNC_LISTENER_NAME,
        )
    yield router_actor
    for topic in SYNC_ACTOR_TOPIC_DICT[SYNC_LISTENER_NAME]:
        try:
            router_actor.message_router_data.remove_subscriber_from_topic(
                topic=topic, subscribing_actor_name=SYNC_LISTENER_NAME,
            )
        except Exception:
            pass


@pytest.fixture
def worker():
    """Start a Dramatiq worker for the duration of each test so that
    messages published to Redis are actually consumed and dispatched to
    the registered actors."""
    broker = dramatiq.get_broker()
    broker.flush_all()
    w = Worker(broker, worker_timeout=100)
    w.start()
    yield w
    w.stop()


def test_geometry_round_trip_to_protocol_metadata(
    qapp, dv_sync_ctrl, subscribed_router, worker,
):
    """Redis: publishing GEOMETRY_CHANGED reaches the controller and
    populates protocol_metadata."""
    manager = dv_sync_ctrl.row_manager
    msg = GeometryChangedMessage(id_to_channel={"e00": 0, "e01": 1})
    publish_message(
        topic=DEVICE_VIEWER_GEOMETRY_CHANGED, message=msg.serialize(),
    )

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if manager.protocol_metadata.get("electrode_to_channel"):
            break
        time.sleep(0.05)

    assert manager.protocol_metadata["electrode_to_channel"] == {
        "e00": 0, "e01": 1,
    }


def test_dv_state_to_stash_round_trip(
    qapp, dv_sync_ctrl, subscribed_router, worker,
):
    """Redis: publishing DEVICE_VIEWER_STATE_CHANGED reaches the
    controller and populates _free_mode_stash."""
    ctrl = dv_sync_ctrl
    publish_message(
        topic=DEVICE_VIEWER_GEOMETRY_CHANGED,
        message=GeometryChangedMessage(
            id_to_channel={"e00": 0, "e01": 1}
        ).serialize(),
    )
    # Wait for geometry to land first (needed so channel->id cache is built).
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if ctrl.row_manager.protocol_metadata.get("electrode_to_channel"):
            break
        time.sleep(0.05)

    publish_message(
        topic=DEVICE_VIEWER_STATE_CHANGED,
        message=DeviceViewerMessageModel(
            channels_activated={0, 1},
            routes=[],
            id_to_channel={"e00": 0, "e01": 1},
            step_info={"step_id": None, "step_label": None,
                       "free_mode": True},
        ).serialize(),
    )

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if ctrl._free_mode_stash:
            break
        time.sleep(0.05)

    assert ctrl._free_mode_stash == {
        "electrodes": ["e00", "e01"], "routes": [],
    }


def test_protocol_running_round_trip(
    qapp, dv_sync_ctrl, subscribed_router, worker,
):
    """Redis: PROTOCOL_RUNNING True/False reaches the controller and
    flips _protocol_running."""
    ctrl = dv_sync_ctrl
    publish_message(topic=PROTOCOL_RUNNING, message="True")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if ctrl._protocol_running:
            break
        time.sleep(0.05)
    assert ctrl._protocol_running is True

    publish_message(topic=PROTOCOL_RUNNING, message="False")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        if not ctrl._protocol_running:
            break
        time.sleep(0.05)
    assert ctrl._protocol_running is False
