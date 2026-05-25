"""Integration test: drive ProtocolLoggingController as the executor +
listener would, and assert that per-phase channel attribution and
artifacts are produced correctly."""

import json
from pathlib import Path

from pluggable_protocol_tree.services.logging.controller import ProtocolLoggingController
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext


def test_two_phase_run_produces_artifacts_with_per_phase_channels(tmp_path):
    """Drive the controller as the executor + listener would: step start,
    phase A actuation + capacitance, phase B actuation + capacitance,
    finish. Assert artifacts + per-phase attribution."""
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=lambda ctrl: ctrl._flush())
    ctx = LoggingDeviceContext(experiment_directory=tmp_path, device_svg_path=None,
                               channel_areas={1: 1.0, 2: 2.0, 3: 3.0},
                               capacitance_per_unit_area=2.0)
    c.start_logging(ctx, n_steps=1, preview_mode=False)

    class _Row:
        uuid = "r1"; name = "S"; path = (0,)
    c._on_step_started(_Row())
    c.on_actuation(json.dumps({"electrodes": ["a"], "channels": [1]}))
    c.on_capacitance(json.dumps({"capacitance": "10pF", "voltage": "100V",
                                 "instrument_time_us": 5, "reception_time": 1}))
    c.on_actuation(json.dumps({"electrodes": ["b", "c"], "channels": [2, 3]}))
    c.on_capacitance(json.dumps({"capacitance": "20pF", "voltage": "100V",
                                 "instrument_time_us": 6, "reception_time": 2}))
    c.stop_logging(completed_steps=1)

    data_json = list((tmp_path / "data").glob("data_*.json"))
    assert data_json and list((tmp_path / "data").glob("data_*.csv"))
    assert list((tmp_path / "reports").glob("report_*.html"))
    payload = json.loads(data_json[0].read_text())
    chan_col = payload["data"][payload["columns"].index("actuated_channels")]
    assert chan_col == [[1], [2, 3]]            # per-phase attribution
