import json

from pluggable_protocol_tree.services.logging.controller import ProtocolLoggingController
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext
import pluggable_protocol_tree.services.logging.listener as L


class _FakeRow:
    uuid = "row-uuid"
    name = "Step A"
    path = (0,)


def _ctx(tmp_path):
    return LoggingDeviceContext(
        experiment_directory=tmp_path,
        device_svg_path=None,
        channel_areas={5: 2.0, 6: 3.0},
        capacitance_per_unit_area=2.0,
    )


def _immediate(controller):
    controller._flush()


def test_start_logging_preview_is_noop(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=True)
    assert c._ingestion is None
    assert L.get_active_logger() is None


def test_actuation_area_summed_from_channel_areas(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5, 6]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    e = c._ingestion.entries[-1]
    assert e["Actuated Area (mm^2)"] == 5.0      # 2.0 + 3.0
    assert e["actuated_channels"] == [5, 6]
    c.stop_logging(completed_steps=1)


def test_flush_writes_artifacts_and_clears_sink(tmp_path):
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=_immediate)
    c.start_logging(_ctx(tmp_path), n_steps=1, preview_mode=False)
    assert L.get_active_logger() is c
    c._on_step_started(_FakeRow())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [5]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 1, "reception_time": 2}))
    c.stop_logging(completed_steps=1)
    assert list((tmp_path / "data").glob("data_*.json"))
    assert list((tmp_path / "data").glob("data_*.csv"))
    assert list((tmp_path / "reports").glob("report_*.html"))
    assert L.get_active_logger() is None
