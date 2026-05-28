"""Manual end-to-end test for the protocol data logger (#421).

Drives the REAL logging stack — ProtocolLoggingController + LoggingIngestion
+ LoggingPersistence + LoggingReport — through a small two-step protocol,
feeding exactly the messages the dramatiq listener forwards at runtime
(CALIBRATION_DATA, per-phase ELECTRODES_STATE_CHANGE, CAPACITANCE_UPDATED).
No Redis, no DropBot, no GUI required.

Run:
    pixi run python -m pluggable_protocol_tree.demos.run_logging_manual_test

It writes the artifacts under ./logging_manual_test_output/ :
    data/data_<t>.json   (columnar)
    data/data_<t>.csv
    reports/report_<t>.html
then reads the data file back and checks it against the known-expected
columnar content, printing PASS/FAIL. Open the .html in a browser to eyeball
the report (summary table + per-step plotly bars; no heatmap here since no
device SVG is supplied).

The protocol exercised:
    Step 1 "Walk route"  (uuid step-walk): a 3-phase loop 1 -> 2 -> back to 1
    Step 2 "Hold pad"    (uuid step-hold): static actuation of channels 5+6
Calibration: liquid=5.0, filler=3.0  ->  capacitance/area = 2.0 pF/mm^2
so Force = 0.5 * 2.0 * V^2  (10000 at 100V, 14400 at 120V).
"""

import json
import shutil
import sys
from pathlib import Path

from pluggable_protocol_tree.services.logging.controller import (
    ProtocolLoggingController,
)
from pluggable_protocol_tree.services.logging.models import LoggingDeviceContext


OUT_DIR = Path("logging_manual_test_output")

# channel -> area mm^2 (what the dock pane would read from the device viewer)
CHANNEL_AREAS = {1: 1.0, 2: 2.0, 5: 1.5, 6: 1.5}


class _Row:
    """Minimal stand-in for a protocol step row (the controller only reads
    .uuid). In the live app these are real RowManager step rows."""
    def __init__(self, uuid):
        self.uuid = uuid
        self.path = (0,)
        self.name = uuid


def _cap(cap_pf, volt_v, instr_us, recv_s):
    return json.dumps({
        "capacitance": f"{cap_pf}pF", "voltage": f"{volt_v}V",
        "instrument_time_us": instr_us, "reception_time": recv_s,
    })


def _act(channels):
    return json.dumps({"electrodes": [f"e{c}" for c in channels],
                       "channels": channels})


EXPECTED_COLUMNS = [
    "step_idx", "utc_time", "instrument_time_us", "step_id",
    "Capacitance (pF)", "Voltage (V)", "Force Over Unit Area (mN/mm^2)",
    "Actuated Area (mm^2)", "actuated_channels",
]
EXPECTED_DATA = [
    [1, 1, 1, 2],                                          # step_idx
    [1700000001, 1700000002, 1700000003, 1700000004],     # utc_time
    [1000, 2000, 3000, 4000],                             # instrument_time_us
    ["step-walk", "step-walk", "step-walk", "step-hold"],  # step_id
    [12.0, 14.0, 12.5, 20.0],                             # Capacitance (pF)
    [100.0, 100.0, 100.0, 120.0],                         # Voltage (V)
    [10000.0, 10000.0, 10000.0, 14400.0],                 # Force Over Unit Area
    [1.0, 2.0, 1.0, 3.0],                                 # Actuated Area (mm^2)
    [[1], [2], [1], [5, 6]],                              # actuated_channels
]


def main() -> int:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    # Absolute path so the report's Experiment Directory metadata can render
    # as a clickable file:// anchor (Path.as_uri requires absolute paths).
    ctx = LoggingDeviceContext(
        experiment_directory=OUT_DIR.resolve(),
        device_svg_path=None,            # supply a real .svg to get a heatmap
        channel_areas=CHANNEL_AREAS,
        capacitance_per_unit_area=None,  # arrives via calibration below
    )
    # settling 0 + synchronous flush so the script is deterministic.
    c = ProtocolLoggingController(settling_provider=lambda: 0.0,
                                  flush_scheduler=lambda ctrl: ctrl._flush())

    c.start_logging(ctx, n_steps=2, preview_mode=False)
    c.on_calibration(json.dumps({"liquid_capacitance_over_area": 5.0,
                                 "filler_capacitance_over_area": 3.0}))

    # Step 1 — loop route walked 1 -> 2 -> back to 1 (3 phases).
    c._on_step_started(_Row("step-walk"))
    c.on_actuation(_act([1])); c.on_capacitance(_cap(12.0, 100, 1000, 1700000001))
    c.on_actuation(_act([2])); c.on_capacitance(_cap(14.0, 100, 2000, 1700000002))
    c.on_actuation(_act([1])); c.on_capacitance(_cap(12.5, 100, 3000, 1700000003))

    # Step 2 — static hold of channels 5 + 6 at 120 V.
    c._on_step_started(_Row("step-hold"))
    c.on_actuation(_act([5, 6])); c.on_capacitance(_cap(20.0, 120, 4000, 1700000004))

    c.stop_logging()

    # --- read back + verify ---
    data_files = sorted((OUT_DIR / "data").glob("data_*.json"))
    csv_files = sorted((OUT_DIR / "data").glob("data_*.csv"))
    report_files = sorted((OUT_DIR / "reports").glob("report_*.html"))
    print(f"Artifacts written under {OUT_DIR.resolve()}:")
    for p in data_files + csv_files + report_files:
        print(f"  {p.relative_to(OUT_DIR)}")

    if not (data_files and csv_files and report_files):
        print("\nFAIL: missing artifact(s).")
        return 1

    payload = json.loads(data_files[0].read_text())
    ok = (payload["columns"] == EXPECTED_COLUMNS
          and payload["data"] == EXPECTED_DATA)
    print("\n--- data file content ---")
    print(json.dumps(payload, indent=2))
    if ok:
        print("\nALL CHECKS PASS — columns + rows match expected "
              "(force, per-phase channels/area, calibration all correct).")
        return 0
    print("\nFAIL: data file did not match expected.")
    print("expected columns:", EXPECTED_COLUMNS)
    print("expected data:   ", EXPECTED_DATA)
    return 1


if __name__ == "__main__":
    sys.exit(main())
