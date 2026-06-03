"""Volume-threshold column tests: model + view + factory metadata, and
the handler's per-phase monitor loop (reading calibration + channel areas
from the module-level ``app_globals``, monkeypatched with a plain dict)."""

import json
import threading
import time

from volume_threshold_protocol_controls.consts import (
    VOLUME_THRESHOLD_COL_ID, VOLUME_THRESHOLD_COL_NAME,
    VOLUME_THRESHOLD_DEFAULT,
)
from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
    make_volume_threshold_column,
)
import volume_threshold_protocol_controls.protocol_columns.volume_threshold_column as mod


# --- model / view / factory ---------------------------------------

def test_column_id_name_default():
    col = make_volume_threshold_column()
    assert col.model.col_id == VOLUME_THRESHOLD_COL_ID
    assert col.model.col_name == VOLUME_THRESHOLD_COL_NAME      # "Volume Threshold %"
    assert col.model.default_value == VOLUME_THRESHOLD_DEFAULT  # 0


def test_column_view_hidden_by_default_and_step_only():
    col = make_volume_threshold_column()
    assert col.view.hidden_by_default is True
    assert col.view.renders_on_group is False
    assert col.view.low == 0
    assert col.view.high == 100


def test_column_trait_is_int_with_default_zero():
    from traits.api import Int
    col = make_volume_threshold_column()
    trait = col.model.trait_for_row()
    assert isinstance(trait.handler, Int().handler.__class__)


def test_handler_wait_for_topics_declared():
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
        VolumeThresholdHandler,
    )
    declared = set(VolumeThresholdHandler().wait_for_topics)
    assert CAPACITANCE_UPDATED in declared
    assert ELECTRODES_STATE_CHANGE in declared
    # CALIBRATION_DATA is NO LONGER needed — calibration comes from app_globals.
    from device_viewer.consts import CALIBRATION_DATA
    assert CALIBRATION_DATA not in declared


# --- handler harness ----------------------------------------------

def _make_handler_ctx(monkeypatch, *, threshold=0, preview=False,
                      app_globals=None, stop_event=None):
    """Build a handler + a stubbed ctx whose wait_for is a queue-backed
    stub (feed via the returned _enqueue). The module-level ``app_globals``
    is monkeypatched with `app_globals` (a plain dict, or None).
    """
    from unittest.mock import MagicMock
    from volume_threshold_protocol_controls.protocol_columns.volume_threshold_column import (
        VolumeThresholdHandler,
    )

    monkeypatch.setattr(mod, "app_globals", app_globals)

    handler = VolumeThresholdHandler()
    row = MagicMock()
    row.volume_threshold = threshold

    proto = MagicMock()
    proto.stop_event = stop_event or threading.Event()
    proto.preview_mode = preview

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


def _good_globals():
    """app_globals with calibration + a channel-area map (string keys,
    as Redis JSON round-trip produces). Channel 1 -> 1.0 mm^2."""
    return {
        "liquid_capacitance_over_area": 5.0,
        "channel_electrode_areas_scaled_map": {"1": 1.0},
    }


# --- early-return guards ------------------------------------------

def test_handler_returns_immediately_when_threshold_is_zero(monkeypatch):
    handler, row, ctx, _ = _make_handler_ctx(
        monkeypatch, threshold=0, app_globals=_good_globals())
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_returns_immediately_when_preview_mode(monkeypatch):
    handler, row, ctx, _ = _make_handler_ctx(
        monkeypatch, threshold=50, preview=True, app_globals=_good_globals())
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_returns_when_app_globals_unavailable(monkeypatch):
    handler, row, ctx, _ = _make_handler_ctx(
        monkeypatch, threshold=50, app_globals=None)
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_returns_when_calibration_missing(monkeypatch):
    handler, row, ctx, _ = _make_handler_ctx(
        monkeypatch, threshold=50,
        app_globals={"channel_electrode_areas_scaled_map": {"1": 1.0}})
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_returns_when_channel_areas_missing(monkeypatch):
    handler, row, ctx, _ = _make_handler_ctx(
        monkeypatch, threshold=50,
        app_globals={"liquid_capacitance_over_area": 5.0})
    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


# --- crossing behaviour -------------------------------------------

def test_handler_sets_phase_advance_when_capacitance_crosses_target(monkeypatch):
    """channels [1] -> area 1.0; liquid 5.0; percent 50 -> target=2.5pF.
    A 3.0pF reading crosses. A daemon sets step_phases_done_event so the
    outer loop exits after the crossing (mirrors RoutesHandler finishing)."""
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    handler, row, ctx, enq = _make_handler_ctx(
        monkeypatch, threshold=50, app_globals=_good_globals())
    enq(ELECTRODES_STATE_CHANGE,
        json.dumps({"electrodes": ["e1"], "channels": [1]}))
    enq(CAPACITANCE_UPDATED,
        json.dumps({"capacitance": "3.0pF", "voltage": "100V"}))

    def _done_soon():
        time.sleep(0.05)
        ctx.step_phases_done_event.set()
    threading.Thread(target=_done_soon, daemon=True).start()

    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is True


def test_handler_does_not_set_event_when_below_target(monkeypatch):
    from dropbot_controller.consts import CAPACITANCE_UPDATED
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    handler, row, ctx, enq = _make_handler_ctx(
        monkeypatch, threshold=50, app_globals=_good_globals())
    enq(ELECTRODES_STATE_CHANGE,
        json.dumps({"electrodes": ["e1"], "channels": [1]}))
    enq(CAPACITANCE_UPDATED,
        json.dumps({"capacitance": "2.0pF", "voltage": "100V"}))   # < 2.5

    def _done_soon():
        time.sleep(0.05)
        ctx.step_phases_done_event.set()
    threading.Thread(target=_done_soon, daemon=True).start()

    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_handler_skips_phase_when_actuated_area_is_zero(monkeypatch):
    """Phase actuates a channel with no area entry -> actuated_area 0 ->
    no target computed, no advance."""
    from electrode_controller.consts import ELECTRODES_STATE_CHANGE
    handler, row, ctx, enq = _make_handler_ctx(
        monkeypatch, threshold=50, app_globals=_good_globals())
    enq(ELECTRODES_STATE_CHANGE,
        json.dumps({"electrodes": ["e9"], "channels": [99]}))   # 99 not in map

    def _done_soon():
        time.sleep(0.05)
        ctx.step_phases_done_event.set()
    threading.Thread(target=_done_soon, daemon=True).start()

    handler.on_step(row, ctx)
    assert ctx.phase_advance_event.is_set() is False


def test_plugin_default_lists_the_column():
    from volume_threshold_protocol_controls.plugin import (
        VolumeThresholdProtocolControlsPlugin,
    )
    p = VolumeThresholdProtocolControlsPlugin()
    contribs = p._contributed_protocol_columns_default()
    assert len(contribs) == 1
    assert contribs[0].model.col_id == VOLUME_THRESHOLD_COL_ID
