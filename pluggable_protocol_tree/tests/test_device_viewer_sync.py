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


def test_geometry_message_writes_to_protocol_metadata(qapp):
    from device_viewer.models.messages import GeometryChangedMessage
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    msg = GeometryChangedMessage(
        id_to_channel={"e00": 0, "e01": 1, "e02": None}
    )
    ctrl._on_geometry_qt(msg.serialize())
    assert ctrl.row_manager.protocol_metadata["electrode_to_channel"] == {
        "e00": 0, "e01": 1, "e02": None,
    }
    assert ctrl._channel_to_id_cache == {0: "e00", 1: "e01"}


def test_geometry_replace_overwrites_metadata_and_rebuilds_cache(qapp):
    from device_viewer.models.messages import GeometryChangedMessage
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0}).serialize()
    )
    ctrl._on_geometry_qt(
        GeometryChangedMessage(
            id_to_channel={"e00": 5, "e01": 6}
        ).serialize()
    )
    assert ctrl.row_manager.protocol_metadata["electrode_to_channel"] == {
        "e00": 5, "e01": 6,
    }
    assert ctrl._channel_to_id_cache == {5: "e00", 6: "e01"}


def test_no_per_step_id_to_channel_storage(qapp):
    """Invariant: id_to_channel lives ONLY in protocol_metadata; never
    on individual rows. Legacy protocol_grid duplicated on each step;
    we deliberately do not."""
    from device_viewer.models.messages import GeometryChangedMessage
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    manager.add_step(values={"name": "S2"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0}).serialize()
    )
    for path, row in manager._walk():
        assert not hasattr(row, "id_to_channel")


def test_protocol_metadata_round_trip(qapp):
    """Mapping persists through to_json / from_json without per-step
    duplication."""
    from device_viewer.models.messages import GeometryChangedMessage
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0}).serialize()
    )
    data = manager.to_json()
    restored = RowManager.from_json(data, columns=list(manager.columns))
    assert restored.protocol_metadata["electrode_to_channel"] == {"e00": 0}


def _make_dv_msg(channels=(), routes=(), step_id=None, id_to_channel=None):
    from device_viewer.models.messages import DeviceViewerMessageModel
    return DeviceViewerMessageModel(
        channels_activated=set(channels),
        routes=list(routes),
        id_to_channel=id_to_channel or {},
        step_info={"step_id": step_id, "step_label": None,
                   "free_mode": step_id is None},
    )


def test_free_mode_message_stashes_electrodes(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    # Pre-seed metadata so reverse-lookup works
    from device_viewer.models.messages import GeometryChangedMessage
    ctrl._on_geometry_qt(
        GeometryChangedMessage(
            id_to_channel={"e00": 0, "e01": 1, "e02": 2}
        ).serialize()
    )
    dv_msg = _make_dv_msg(channels=[1, 2])
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash == {
        "electrodes": ["e01", "e02"], "routes": [],
    }


def test_step_scoped_message_clears_stash(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._free_mode_stash = {"electrodes": ["x"], "routes": []}
    dv_msg = _make_dv_msg(channels=[1], step_id="abc")
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash is None


def test_empty_message_clears_stash(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._free_mode_stash = {"electrodes": ["x"], "routes": []}
    dv_msg = _make_dv_msg(channels=[], routes=[])
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash is None


def test_state_seeds_metadata_when_empty_cold_start(qapp):
    """Phase-1 cold start: if no GEOMETRY_CHANGED seen yet, take the
    inline mapping from the first state message."""
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    assert ctrl.id_to_channel == {}
    dv_msg = _make_dv_msg(
        channels=[0], id_to_channel={"e00": 0, "e01": 1}
    )
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl.row_manager.protocol_metadata["electrode_to_channel"] == {
        "e00": 0, "e01": 1,
    }
    assert ctrl._free_mode_stash == {"electrodes": ["e00"], "routes": []}


def test_state_uses_metadata_for_reverse_lookup(qapp):
    """Once metadata is populated, reverse-lookup uses it - state msgs
    that omit id_to_channel still resolve correctly."""
    from device_viewer.models.messages import GeometryChangedMessage
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0, "e01": 1}).serialize()
    )
    dv_msg = _make_dv_msg(channels=[0, 1], id_to_channel={})
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash == {
        "electrodes": ["e00", "e01"], "routes": [],
    }


def test_step_click_publishes_display_state(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    manager.add_step(values={
        "name": "S1", "electrodes": ["e00", "e01"], "routes": [["e02"]],
    })
    ctrl = DeviceViewerSyncController(row_manager=manager)
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)

    assert len(publishes) == 1
    from pluggable_protocol_tree.consts import PROTOCOL_TREE_DISPLAY_STATE
    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    topic, payload = publishes[0]
    assert topic == PROTOCOL_TREE_DISPLAY_STATE
    msg = ProtocolTreeDisplayMessage.deserialize(payload)
    assert msg.electrodes == ["e00", "e01"]
    assert msg.routes == [["e02"]]
    assert msg.step_id == row.uuid
    assert msg.step_label == "S1"
    assert msg.free_mode is False


def test_group_click_emits_free_mode_payload(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._publish_for_row(None)        # treats None as deselect/group
    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    msg = ProtocolTreeDisplayMessage.deserialize(publishes[0][1])
    assert msg.free_mode is True
    assert msg.electrodes == []
    assert msg.routes == []
    assert msg.step_id is None


def test_protocol_running_blocks_publish(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1", "electrodes": ["e00"]})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._protocol_running = True
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)
    assert publishes == []


def test_suppress_publish_blocks_publish(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1", "electrodes": ["e00"]})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._suppress_publish = True
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)
    assert publishes == []
