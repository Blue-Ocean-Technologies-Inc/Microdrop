"""Tests for DeviceViewerSyncController."""

from unittest.mock import MagicMock

from device_viewer.consts import (
    DEVICE_VIEWER_STATE_CHANGED,
    DEVICE_VIEWER_GEOMETRY_CHANGED,
    PROTOCOL_RUNNING,
    STEP_PARAMS_COMMIT,
)
from device_viewer.models.step_params_commit import StepParamsCommitMessage
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


def test_actor_subscribed_topics():
    from dropbot_controller.consts import REALTIME_MODE_UPDATED
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    from pluggable_protocol_tree.consts import ACTOR_TOPIC_DICT
    topics = ACTOR_TOPIC_DICT[ctrl.listener_name]
    assert set(topics) == {
        DEVICE_VIEWER_STATE_CHANGED,
        DEVICE_VIEWER_GEOMETRY_CHANGED,
        PROTOCOL_RUNNING,
        REALTIME_MODE_UPDATED,
        STEP_PARAMS_COMMIT,
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


def _make_dv_msg(channels=(), routes=(), step_id=None, id_to_channel=None,
                 execution_params=None):
    from device_viewer.models.messages import DeviceViewerMessageModel
    return DeviceViewerMessageModel(
        channels_activated=set(channels),
        routes=list(routes),
        id_to_channel=id_to_channel or {},
        step_info={"step_id": step_id, "step_label": None,
                   "free_mode": step_id is None},
        execution_params=execution_params,
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
        "execution_params": None,
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
    assert ctrl._free_mode_stash == {
        "electrodes": ["e00"], "routes": [], "execution_params": None,
    }


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
        "execution_params": None,
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
    assert msg.step_label == "Step 1"   # dotted-path id
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
    assert msg.execution_params is None    # DV disables its commit button


# --- DV sidebar route-executor params (issue #435 / PPT-23) ---------------

def _make_params_manager():
    """Manager with every route-execution param column the DV sidebar maps."""
    from pluggable_protocol_tree.builtins.duration_column import (
        make_duration_column,
    )
    from pluggable_protocol_tree.builtins.linear_repeats_column import (
        make_linear_repeats_column,
    )
    from pluggable_protocol_tree.builtins.repeat_duration_column import (
        make_repeat_duration_column,
    )
    from pluggable_protocol_tree.builtins.route_repetitions_column import (
        make_route_repetitions_column,
    )
    from pluggable_protocol_tree.builtins.soft_end_column import (
        make_soft_end_column,
    )
    from pluggable_protocol_tree.builtins.soft_start_column import (
        make_soft_start_column,
    )
    from pluggable_protocol_tree.builtins.trail_length_column import (
        make_trail_length_column,
    )
    from pluggable_protocol_tree.builtins.trail_overlay_column import (
        make_trail_overlay_column,
    )
    return RowManager(columns=[
        make_name_column(),
        make_electrodes_column(),
        make_routes_column(),
        make_duration_column(),
        make_route_repetitions_column(),
        make_repeat_duration_column(),
        make_trail_length_column(),
        make_trail_overlay_column(),
        make_soft_start_column(),
        make_soft_end_column(),
        make_linear_repeats_column(),
    ])


def _commit_msg(step_id, **overrides):
    values = dict(
        step_id=step_id, duration=2.5, repetitions=4, repeat_duration=0,
        trail_length=3, trail_overlay=1, soft_start=True,
        soft_terminate=True, linear_repeats=True,
    )
    values.update(overrides)
    return StepParamsCommitMessage(**values)


def test_step_publish_includes_mapped_execution_params(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_params_manager()
    manager.add_step(values={
        "name": "S1", "duration_s": 2.5, "route_repetitions": 4,
        "repeat_duration": 6.42, "trail_length": 3, "trail_overlay": 1,
        "soft_start": True, "soft_end": True, "linear_repeats": False,
    })
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._publish_for_row(manager.get_row((0,)))

    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    msg = ProtocolTreeDisplayMessage.deserialize(publishes[0][1])
    assert msg.execution_params == {
        "duration": 2.5,
        "repetitions": 4,            # route_repetitions column
        "repeat_duration": 6,        # rounded to the DV integer spinner
        "trail_length": 3,
        "trail_overlay": 1,
        "soft_start": True,
        "soft_terminate": True,      # soft_end column
        "linear_repeats": False,
    }


def test_listener_routine_emits_step_params_committed(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_params_manager())
    spy = MagicMock()
    ctrl.bridge.step_params_committed.connect(spy)
    ctrl._listener_routine("payload", STEP_PARAMS_COMMIT)
    qapp.processEvents()
    spy.assert_called_once_with("payload")


def test_commit_writes_params_and_fires_cell_changed(qapp):
    manager = _make_params_manager()
    manager.add_step(values={"name": "S1"})
    row = manager.get_row((0,))
    ctrl = DeviceViewerSyncController(row_manager=manager)

    changed_cols = []
    manager.observe(
        lambda ev: changed_cols.append(ev.new["col_id"]), "cell_changed",
    )
    ctrl._on_step_params_commit_qt(_commit_msg(row.uuid).serialize())

    assert row.duration_s == 2.5
    assert row.route_repetitions == 4
    assert row.trail_length == 3
    assert row.trail_overlay == 1
    assert row.soft_start is True
    assert row.soft_end is True              # DV soft_terminate
    assert row.linear_repeats is True
    assert set(changed_cols) == {
        "duration_s", "route_repetitions", "trail_length", "trail_overlay",
        "soft_start", "soft_end", "linear_repeats",
    }


def test_commit_count_mode_skips_derived_repeat_duration(qapp):
    """repeat_duration_controls False: Route Reps Dur is derived (the pane
    reconciliation recalculates it) so the commit must not write it."""
    manager = _make_params_manager()
    manager.add_step(values={"name": "S1", "repeat_duration": 9.99})
    row = manager.get_row((0,))
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_step_params_commit_qt(
        _commit_msg(row.uuid, repeat_duration=0).serialize()
    )
    assert row.repeat_duration == 9.99       # untouched
    assert row.route_repetitions == 4


def test_commit_duration_mode_skips_derived_route_repetitions(qapp):
    """repeat_duration_controls True: Route Reps is derived instead."""
    manager = _make_params_manager()
    manager.add_step(values={"name": "S1", "route_repetitions": 7})
    row = manager.get_row((0,))
    row.repeat_duration_controls = True
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_step_params_commit_qt(
        _commit_msg(row.uuid, repetitions=1, repeat_duration=12).serialize()
    )
    assert row.repeat_duration == 12.0
    assert row.route_repetitions == 7        # untouched


def test_commit_for_selected_row_republishes_display_state(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_params_manager()
    manager.add_step(values={"name": "S1"})
    row = manager.get_row((0,))
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._last_selected_uuid = row.uuid
    ctrl._on_step_params_commit_qt(_commit_msg(row.uuid).serialize())

    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    assert len(publishes) == 1               # the rebaseline echo
    msg = ProtocolTreeDisplayMessage.deserialize(publishes[0][1])
    assert msg.step_id == row.uuid
    assert msg.execution_params["duration"] == 2.5


def test_commit_for_unselected_row_does_not_republish(qapp, monkeypatch):
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_params_manager()
    manager.add_step(values={"name": "S1"})
    row = manager.get_row((0,))
    ctrl = DeviceViewerSyncController(row_manager=manager)   # nothing selected
    ctrl._on_step_params_commit_qt(_commit_msg(row.uuid).serialize())
    assert publishes == []
    assert row.duration_s == 2.5             # write still happened


def test_commit_for_unknown_step_is_dropped(qapp):
    manager = _make_params_manager()
    manager.add_step(values={"name": "S1"})
    row = manager.get_row((0,))
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_step_params_commit_qt(_commit_msg("no-such-uuid").serialize())
    assert row.duration_s != 2.5             # untouched


def test_free_mode_stash_carries_sidebar_params(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_params_manager())
    params = {
        "duration": 4.0, "repetitions": 2, "repeat_duration": 0,
        "trail_length": 5, "trail_overlay": 3, "soft_start": True,
        "soft_terminate": False, "linear_repeats": True,
    }
    dv_msg = _make_dv_msg(
        channels=[0], id_to_channel={"e00": 0}, execution_params=params,
    )
    ctrl._on_dv_state_qt(dv_msg.serialize())
    assert ctrl._free_mode_stash["execution_params"] == params


def test_insert_free_mode_step_seeds_execution_params(qapp):
    manager = _make_params_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._free_mode_stash = {
        "electrodes": ["e00"],
        "routes": [["e00", "e01"]],
        "execution_params": {
            "duration": 4.0, "repetitions": 2, "repeat_duration": 1,
            "trail_length": 5, "trail_overlay": 3, "soft_start": True,
            "soft_terminate": True, "linear_repeats": True,
        },
    }
    ctrl._insert_free_mode_as_new_step()
    row = manager.get_row((0,))
    assert row.electrodes == ["e00"]
    assert row.routes == [["e00", "e01"]]
    assert row.duration_s == 4.0
    assert row.route_repetitions == 2        # DV 'repetitions'
    assert row.repeat_duration == 1.0
    assert row.trail_length == 5
    assert row.trail_overlay == 3
    assert row.soft_start is True
    assert row.soft_end is True              # DV 'soft_terminate'
    assert row.linear_repeats is True


def test_insert_free_mode_step_without_params_uses_column_defaults(qapp):
    manager = _make_params_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._free_mode_stash = {
        "electrodes": ["e00"], "routes": [], "execution_params": None,
    }
    ctrl._insert_free_mode_as_new_step()
    row = manager.get_row((0,))
    assert row.duration_s == 1.0             # column default
    assert row.route_repetitions == 1


def test_group_row_emits_free_mode_payload(qapp, monkeypatch):
    """Same handling for an actual GroupRow instance, not just None."""
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    group_path = manager.add_group(name="Group A")
    group = manager.get_row(group_path)
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._publish_for_row(group)
    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    msg = ProtocolTreeDisplayMessage.deserialize(publishes[0][1])
    assert msg.free_mode is True
    assert msg.electrodes == []
    assert msg.step_id is None


def test_protocol_running_does_not_block_publish(qapp, monkeypatch):
    """During a run the executor calls _publish_for_row to update the DV
    on each step transition; user clicks during a run also publish.
    The _protocol_running flag is informational, not a publish gate."""
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
    assert len(publishes) == 1


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


def test_step_click_with_stash_yes_inserts_step(qapp, monkeypatch):
    from microdrop_application.dialogs.pyface_wrapper import YES
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.confirm",
        lambda *a, **kw: YES,
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._free_mode_stash = {
        "electrodes": ["e00", "e01"], "routes": [["e02"]],
    }
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)

    # New step appended at end of root with the stashed values
    assert len(manager.root.children) == 2
    new_row = manager.root.children[1]
    assert new_row.electrodes == ["e00", "e01"]
    assert new_row.routes == [["e02"]]
    assert ctrl._free_mode_stash is None
    # _publish_for_row publishes once. The reentrancy guard
    # (_suppress_publish around add_step) only matters in production
    # where a Qt selection model fires currentChanged on row insert;
    # this test does not wire one, so it cannot exercise the guard.
    assert len(publishes) == 1


def test_step_click_with_stash_no_discards(qapp, monkeypatch):
    from microdrop_application.dialogs.pyface_wrapper import NO
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.confirm",
        lambda *a, **kw: NO,
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._free_mode_stash = {
        "electrodes": ["e00"], "routes": [],
    }
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)

    assert len(manager.root.children) == 1   # no add_step
    assert ctrl._free_mode_stash is None
    assert len(publishes) == 1


def test_no_prompt_when_stash_empty(qapp, monkeypatch):
    publishes = []
    confirms = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.confirm",
        lambda *a, **kw: confirms.append(1),
    )
    manager = _make_manager()
    manager.add_step(values={"name": "S1"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    row = manager.get_row((0,))
    ctrl._publish_for_row(row)
    assert confirms == []                    # dialog never shown
    assert len(publishes) == 1


def test_step_scoped_message_writes_back_to_row(qapp):
    """When the user toggles electrodes on the DV with a step selected,
    the channel/route changes are written back to that row's electrodes
    and routes columns. Mirrors the legacy protocol_grid edit behavior."""
    from device_viewer.models.messages import GeometryChangedMessage
    manager = _make_manager()
    path = manager.add_step(values={
        "name": "S1", "electrodes": ["e00"], "routes": [],
    })
    row = manager.get_row(path)

    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_geometry_qt(
        GeometryChangedMessage(
            id_to_channel={"e00": 0, "e01": 1, "e02": 2}
        ).serialize()
    )

    # DV reports step_id matching this row, with channels [0, 1, 2] and one route
    dv_msg = _make_dv_msg(
        channels=[0, 1, 2],
        routes=[(["e01", "e02"], "blue")],
        step_id=row.uuid,
    )
    ctrl._on_dv_state_qt(dv_msg.serialize())

    assert row.electrodes == ["e00", "e01", "e02"]
    assert row.routes == [["e01", "e02"]]
    # Stash stays clear (we are not in free mode)
    assert ctrl._free_mode_stash is None


def test_step_scoped_write_back_fires_manager_cell_changed(qapp):
    """Regression: DV-driven electrode/route writes go directly to
    ``row.electrodes`` / ``row.routes``, bypassing both
    ``QtTreeModel.setData`` and ``ProtocolItemDelegate.setModelData``.
    The sync controller must fire ``cell_changed`` (with path + col_id)
    after each mutation so the protocol state tracker can update its
    incremental dirty bookkeeping — without this, editing electrodes/
    routes via the device viewer leaves the "unsaved changes" indicator
    off.
    """
    from device_viewer.models.messages import GeometryChangedMessage
    manager = _make_manager()
    path = manager.add_step(values={
        "name": "S1", "electrodes": ["e00"], "routes": [],
    })
    row = manager.get_row(path)

    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_geometry_qt(
        GeometryChangedMessage(
            id_to_channel={"e00": 0, "e01": 1, "e02": 2}
        ).serialize()
    )

    fired = []
    manager.observe(lambda ev: fired.append(ev.new), "cell_changed")

    # Electrode-only change.
    ctrl._on_dv_state_qt(_make_dv_msg(
        channels=[0, 1], step_id=row.uuid,
    ).serialize())
    assert row.electrodes == ["e00", "e01"]
    assert fired == [{"path": path, "col_id": "electrodes"}]

    # Route-only change (same electrodes).
    ctrl._on_dv_state_qt(_make_dv_msg(
        channels=[0, 1], routes=[(["e02"], "blue")], step_id=row.uuid,
    ).serialize())
    assert row.routes == [["e02"]]
    assert fired == [
        {"path": path, "col_id": "electrodes"},
        {"path": path, "col_id": "routes"},
    ]

    # No-op replay: same payload again must NOT re-fire.
    ctrl._on_dv_state_qt(_make_dv_msg(
        channels=[0, 1], routes=[(["e02"], "blue")], step_id=row.uuid,
    ).serialize())
    assert len(fired) == 2


def test_step_scoped_message_with_unknown_step_id_is_noop(qapp):
    """If the DV's step_id doesn't match any row in our tree (e.g. the
    legacy grid is still publishing), don't crash and don't mutate."""
    from device_viewer.models.messages import GeometryChangedMessage
    manager = _make_manager()
    manager.add_step(values={"name": "S1", "electrodes": ["e00"]})
    row = manager.get_row((0,))
    original_electrodes = list(row.electrodes)

    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._on_geometry_qt(
        GeometryChangedMessage(id_to_channel={"e00": 0, "e01": 1}).serialize()
    )

    dv_msg = _make_dv_msg(
        channels=[1], step_id="nonexistent-uuid",
    )
    ctrl._on_dv_state_qt(dv_msg.serialize())

    assert row.electrodes == original_electrodes   # unchanged
    assert ctrl._free_mode_stash is None


def test_deselect_with_stash_also_prompts(qapp, monkeypatch):
    """Spec §4.D: deselect / group click should also resolve the
    free-mode stash via the prompt, not just step clicks."""
    from microdrop_application.dialogs.pyface_wrapper import YES
    publishes = []
    confirm_calls = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.confirm",
        lambda *a, **kw: (confirm_calls.append(1), YES)[1],
    )
    manager = _make_manager()
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._free_mode_stash = {"electrodes": ["e00"], "routes": []}
    ctrl._publish_for_row(None)         # deselect
    assert confirm_calls == [1]         # prompt fired
    assert len(manager.root.children) == 1   # YES => insert-as-new-step
    assert ctrl._free_mode_stash is None
    # Free-mode publish still happens after the resolution
    assert len(publishes) == 1


def test_step_label_uses_dotted_step_id(qapp, monkeypatch):
    """The DV's status bar shows 'Editing: <step_label>' — make the
    label informative ('Step 1', 'Step 2.3') instead of the bare
    row name (which defaults to 'Step')."""
    publishes = []
    monkeypatch.setattr(
        "pluggable_protocol_tree.services.device_viewer_sync.publish_message",
        lambda topic, message: publishes.append((topic, message)),
    )
    manager = _make_manager()
    manager.add_step(values={"name": "Step"})
    manager.add_step(values={"name": "Step"})
    ctrl = DeviceViewerSyncController(row_manager=manager)
    ctrl._publish_for_row(manager.get_row((1,)))   # second step, path (1,)

    from pluggable_protocol_tree.models.display_state import (
        ProtocolTreeDisplayMessage,
    )
    msg = ProtocolTreeDisplayMessage.deserialize(publishes[0][1])
    assert msg.step_label == "Step 2"   # 1-indexed dotted-path id


def test_protocol_running_signal_updates_flag(qapp):
    ctrl = DeviceViewerSyncController(row_manager=_make_manager())
    ctrl._on_protocol_running_qt(True)
    assert ctrl._protocol_running is True
    ctrl._on_protocol_running_qt(False)
    assert ctrl._protocol_running is False
