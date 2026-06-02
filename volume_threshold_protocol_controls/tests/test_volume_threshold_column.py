"""Volume-threshold column smoke tests.

This file grows over Tasks 5 and 6 — Task 5 adds model + view + factory
metadata tests, Task 6 adds handler behaviour tests."""

from volume_threshold_protocol_controls.consts import (
    VOLUME_THRESHOLD_COL_ID, VOLUME_THRESHOLD_COL_NAME,
    VOLUME_THRESHOLD_DEFAULT,
)
from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
    make_volume_threshold_column,
)


def test_column_id_name_default():
    col = make_volume_threshold_column()
    assert col.model.col_id == VOLUME_THRESHOLD_COL_ID
    assert col.model.col_name == VOLUME_THRESHOLD_COL_NAME
    assert col.model.default_value == VOLUME_THRESHOLD_DEFAULT


def test_column_view_hidden_by_default_and_step_only():
    """Step-only column (no value on a group row); hidden by default
    in the column header — same posture as droplet_check and the trail
    /loop knobs. Surfaces via header right-click."""
    col = make_volume_threshold_column()
    assert col.view.hidden_by_default is True
    assert col.view.renders_on_group is False


def test_column_trait_is_int_with_default_zero():
    """trait_for_row must return an Int trait — the column is a 0-100
    percent."""
    from traits.api import Int
    col = make_volume_threshold_column()
    trait = col.model.trait_for_row()
    assert isinstance(trait.handler, Int().handler.__class__)


def test_plugin_default_lists_the_column():
    """Task 5 wired the factory into the plugin's contribution list."""
    from volume_threshold_protocol_controls.plugin import (
        VolumeThresholdProtocolControlsPlugin,
    )
    p = VolumeThresholdProtocolControlsPlugin()
    contribs = p._contributed_protocol_columns_default()
    assert len(contribs) == 1
    assert contribs[0].model.col_id == VOLUME_THRESHOLD_COL_ID


def _make_handler_ctx(*, threshold=0.0, preview=False, electrode_areas=None,
                      stop_event=None):
    """Build a minimal handler + ctx pair for unit tests. The ctx's
    wait_for is a queue-backed stub — feed it items via the returned
    _enqueue(topic, payload) using the REAL topic constants."""
    import threading
    from unittest.mock import MagicMock

    from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
        VolumeThresholdHandler,
    )

    handler = VolumeThresholdHandler()
    row = MagicMock()
    row.volume_threshold = threshold

    proto = MagicMock()
    proto.stop_event = stop_event or threading.Event()
    proto.preview_mode = preview
    proto.scratch = {}
    if electrode_areas is not None:
        proto.scratch["electrode_areas"] = electrode_areas

    ctx = MagicMock()
    ctx.protocol = proto
    ctx.phase_advance_event = threading.Event()
    ctx.step_phases_done_event = threading.Event()

    queues = {}
    def _wait_for(topic, timeout=5.0, predicate=None):
        q = queues.setdefault(topic, [])
        while q:
            item = q.pop(0)
            if predicate is None or predicate(item):
                return item
        raise TimeoutError(topic)
    ctx.wait_for = _wait_for

    def _enqueue(topic, payload):
        queues.setdefault(topic, []).append(payload)

    return handler, row, ctx, _enqueue


def test_handler_returns_immediately_when_threshold_is_zero():
    handler, row, ctx, _ = _make_handler_ctx(threshold=0.0)
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_returns_immediately_when_preview_mode():
    handler, row, ctx, _ = _make_handler_ctx(threshold=50, preview=True,
                                              electrode_areas={"e1": 1.0})
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_returns_immediately_when_electrode_areas_missing():
    handler, row, ctx, _ = _make_handler_ctx(threshold=50,
                                              electrode_areas=None)
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_sets_phase_advance_event_when_capacitance_crosses_target():
    """electrodes ["e1"] -> area 1.0; liquid_capacitance_over_area=5.0;
    percent=50 -> full=5.0, target=0.50*5.0=2.5pF. A reading of 3.0pF
    crosses the target and triggers advance.
    A daemon sets step_phases_done_event so the per-phase outer loop
    exits after the crossing (mirrors RoutesHandler finishing its
    phases in a real run)."""
    import json
    import threading
    import time
    from device_viewer.consts import CALIBRATION_DATA
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    handler, row, ctx, enq = _make_handler_ctx(
        threshold=50, electrode_areas={"e1": 1.0},
    )
    enq(CALIBRATION_DATA,
        json.dumps({"liquid_capacitance_over_area": 5.0,
                    "filler_capacitance_over_area": 3.0}))
    enq(ELECTRODES_STATE_CHANGE,
        json.dumps({"electrodes": ["e1"], "channels": [1]}))
    enq(CAPACITANCE_UPDATED,
        json.dumps({"capacitance": "3.0pF", "voltage": "100V"}))

    def _set_done_soon():
        time.sleep(0.05)
        ctx.step_phases_done_event.set()
    threading.Thread(target=_set_done_soon, daemon=True).start()

    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is True


def test_handler_does_not_set_event_when_below_target():
    import json
    import threading
    from device_viewer.consts import CALIBRATION_DATA
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    handler, row, ctx, enq = _make_handler_ctx(
        threshold=50, electrode_areas={"e1": 1.0},
    )
    enq(CALIBRATION_DATA,
        json.dumps({"liquid_capacitance_over_area": 5.0,
                    "filler_capacitance_over_area": 3.0}))
    enq(ELECTRODES_STATE_CHANGE,
        json.dumps({"electrodes": ["e1"], "channels": [1]}))
    enq(CAPACITANCE_UPDATED,
        json.dumps({"capacitance": "2.0pF", "voltage": "100V"}))
    # Simulate Routes finishing so the outer loop exits.
    def _set_done_soon():
        import time
        time.sleep(0.05)
        ctx.step_phases_done_event.set()
    threading.Thread(target=_set_done_soon, daemon=True).start()
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_skips_phase_when_actuated_area_is_zero():
    import json
    import threading
    from device_viewer.consts import CALIBRATION_DATA
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    handler, row, ctx, enq = _make_handler_ctx(
        threshold=50, electrode_areas={"e1": 1.0},
    )
    enq(CALIBRATION_DATA,
        json.dumps({"liquid_capacitance_over_area": 5.0,
                    "filler_capacitance_over_area": 3.0}))
    enq(ELECTRODES_STATE_CHANGE,
        json.dumps({"electrodes": ["unknown"], "channels": [99]}))
    def _set_done_soon():
        import time
        time.sleep(0.05)
        ctx.step_phases_done_event.set()
    threading.Thread(target=_set_done_soon, daemon=True).start()
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_wait_for_topics_declared():
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from device_viewer.consts import CALIBRATION_DATA
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
        VolumeThresholdHandler,
    )
    # Instance-level access — that's how the executor reads it
    # (col.handler.wait_for_topics in _build_step_ctx).
    declared = set(VolumeThresholdHandler().wait_for_topics)
    assert CAPACITANCE_UPDATED in declared
    assert ELECTRODES_STATE_CHANGE in declared
    assert CALIBRATION_DATA in declared
