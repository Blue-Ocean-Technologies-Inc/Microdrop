"""Tests for DeviceViewerSyncController."""

from unittest.mock import MagicMock

from device_viewer.consts import (
    DEVICE_VIEWER_STATE_CHANGED,
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    PROTOCOL_RUNNING,
)
from pluggable_protocol_tree.builtins.electrodes_column import (
    make_electrodes_column,
)
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.routes_column import make_routes_column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.services.device_viewer_sync import (
    DeviceViewerSyncController,
)


def _make_manager():
    return RowManager(columns=[
        make_name_column(),
        make_electrodes_column(),
        make_routes_column(),
    ])


def test_listener_routine_emits_dv_state_signal_on_state_topic(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    spy = MagicMock()
    ctrl.bridge.dv_state_received.connect(spy)
    ctrl._listener_routine("payload-1", DEVICE_VIEWER_STATE_CHANGED)
    qapp.processEvents()
    spy.assert_called_once_with("payload-1")


def test_listener_routine_emits_geometry_signal_on_geometry_topic(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    spy = MagicMock()
    ctrl.bridge.geometry_changed.connect(spy)
    ctrl._listener_routine("geom-payload", DEVICE_VIEWER_GEOMETRY_CHANGED)
    qapp.processEvents()
    spy.assert_called_once_with("geom-payload")


def test_listener_routine_emits_protocol_running_bool(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    spy = MagicMock()
    ctrl.bridge.protocol_running_changed.connect(spy)
    ctrl._listener_routine("True", PROTOCOL_RUNNING)
    ctrl._listener_routine("False", PROTOCOL_RUNNING)
    qapp.processEvents()
    spy.assert_any_call(True)
    spy.assert_any_call(False)


def test_actor_subscribes_to_three_topics():
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    from pluggable_protocol_tree.services.device_viewer_sync import (
        SYNC_ACTOR_TOPIC_DICT,
    )
    topics = SYNC_ACTOR_TOPIC_DICT[ctrl.listener_name]
    assert set(topics) == {
        DEVICE_VIEWER_STATE_CHANGED,
        DEVICE_VIEWER_GEOMETRY_CHANGED,
        PROTOCOL_RUNNING,
    }
