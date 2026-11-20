# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The inline results survive the pub/sub JSON hop: a vendor-shaped result,
made JSON-safe by the backend (``_to_jsonable``: arrays to lists, NaN to
None) and parsed back, still draws its figure and formats its report on the
frontend."""

# Standard library imports.
import json

# Third-party imports.
import matplotlib
import numpy as np
import pytest

# Microdrop utils imports.
from microdrop_utils.json_helpers import restore_nan_from_json_nulls

matplotlib.use("Agg")

st = pytest.importorskip("dropbot_portable.self_test")

#: The vendor's own test names, spelled out so a vendor rename fails here.
VOLTAGE_TEST = "test_voltage"
CALIBRATION_TEST = "test_on_board_feedback_calibration"
CHANNELS_TEST = "test_channels"


def _voltage_result():
    target = np.linspace(40.0, 200.0, 3)
    measured = target + np.array([0.5, -1.0, 2.0])

    return {
        "target_voltage": target.tolist(),
        "vref_set_type": None,
        "setpoint_echo": False,
        "verdict": True,
        "commanded_voltage": [40.0, np.nan, 200.0],
        "measured_voltage": measured.tolist(),
        "measured_voltage_std": [0.1, 0.2, np.nan],
        "measured_voltage_no_load": [39.0, 119.0, np.nan],
        "measured_voltage_no_load_std": [0.1, np.nan, 0.3],
        "reads_per_point": 3,
        "hv_test": {"target": [40, 80, 120, 160, 200], "actual": None},
        "hv_enable_status": 0,
        "alarms": [],
        "delay": 1.0,
        "input_current": [None] * 3,
        "output_current": [None] * 3,
        "input_current_no_load": [None] * 3,
        "output_current_no_load": [None] * 3,
        "input_voltage": None,
        "duration": 12.5,
        "utc_timestamp": "2026-11-20T12:00:00+00:00",
    }


def _calibration_result():
    """The matrix shape, with a refused cell (all NaN) and a skipped one."""
    voltages = [40.0, 80.0]
    fbcs = [0, 2]
    rows = [0.0, 10.0, 100.0, 470.0]
    n_reps = 2
    rng = np.random.default_rng(0)

    iqr = 100.0 + rng.random((len(voltages), len(fbcs), len(rows), n_reps)) * 400.0
    iqr[1, 1, 3, :] = np.nan
    rail = np.zeros((len(voltages), len(fbcs), len(rows)))
    skipped = np.zeros_like(rail, dtype=bool)
    skipped[0, 0, 3] = True
    matrix = {
        "rows": rows,
        "iqr": iqr,
        "rail": rail,
        "volts": np.array(voltages),
        "refused": ["80 V BACK3 470 pF: status 3"],
        "skipped": skipped,
    }
    cfb_nf = {f: st.CFB_NOMINAL_NF[f] for f in fbcs}
    pf, status = st._matrix_cells(matrix, fbcs, cfb_nf)
    copy = pf[0, 1]

    return {
        "c_nominal": rows,
        "cal_caps_nominal": [10.0, 100.0, 470.0],
        "cal_caps": 3,
        "c_measured": copy * st.PF_TO_F,
        "c_measured_pf": copy,
        "c_corrected_pf": copy,
        "voltage": voltages[0],
        "feedback_cap": "BACK3",
        "cfb_nf": st.CFB_NOMINAL_NF[2],
        "cfb_source": "nominal",
        "matrix": {
            "voltages": voltages,
            "volts_measured": np.array([40.2, np.nan]),
            "feedback_caps": [st.FBC_NAMES[f] for f in fbcs],
            "feedback_gain_names": [st.FBC_GAIN_NAMES[f] for f in fbcs],
            "min_counts": 50.0,
            "rail_frac_max": 0.05,
            "cfb_nf": [cfb_nf[f] for f in fbcs],
            "rows_pf": rows,
            "iqr_counts": iqr,
            "c_pf": pf,
            "rail_frac": rail,
            "skipped": skipped,
            "status": status.tolist(),
            "refused": matrix["refused"],
        },
        "method_kind": "matrix",
        "n_reads": 8,
        "samples_per_read": 64,
        "tolerance_pct": 25.0,
        "tolerance_pf": 3.0,
        "verdict": False,
        "cap_calibrate": {"cfb_back1_nf": 1001.0, "iqr_b1_r10": 12},
        "cap_calibrate_saved": False,
        "hv_enable_status": 2,
        "duration": 40.0,
        "utc_timestamp": "2026-11-20T12:01:00+00:00",
    }


def _channels_result():
    """Four channels x two repeats: one shorted (zeros), one not measured
    (NaN), one below the threshold."""
    raw = np.array([[18.0, 18.5], [0.0, 0.0], [np.nan, np.nan], [9.0, 9.2]])
    baseline = 8.0
    corrected = np.where(np.isfinite(raw) & (raw != 0), raw - baseline, raw)

    return {
        "test_channels": [0, 1, 2, 3],
        "shorts": [1],
        "c": raw * st.PF_TO_F,
        "c_pf": raw,
        "c_corrected_pf": corrected,
        "corrected_by": "host baseline",
        "baseline_pf": baseline,
        "tare_capture": {"ok": True, "saved": False, "raw_before_tare": True},
        "voltage": 100.0,
        "hv_enable_status": 0,
        "thresholds_pf": [5.0, 5.0, 5.0, 5.0],
        "threshold_default_pf": 5.0,
        "not_in_chip": [4, 5],
        "duration": 30.0,
        "utc_timestamp": "2026-11-20T12:02:00+00:00",
    }


SYNTHETIC_RESULTS = {
    VOLTAGE_TEST: _voltage_result,
    CALIBRATION_TEST: _calibration_result,
    CHANNELS_TEST: _channels_result,
}


def _over_the_wire(result):
    """What the frontend holds: the backend's JSON-safe copy, parsed back
    and with its missing values restored as the model does."""
    received = json.loads(json.dumps(st._to_jsonable(result)))

    return restore_nan_from_json_nulls(received)


def test_every_plottable_test_has_a_synthetic_result():
    assert set(SYNTHETIC_RESULTS) == set(st.PLOTTABLE_TESTS)


@pytest.mark.parametrize("name", st.PLOTTABLE_TESTS)
def test_figure_draws_from_the_received_result(name):
    result = _over_the_wire(SYNTHETIC_RESULTS[name]())

    for view in st._FIGURE_VIEWS.get(name, ("calibrated",)):
        assert st.draw_test_figure(name, result, view=view) is not None


@pytest.mark.parametrize("name", st.PLOTTABLE_TESTS)
def test_report_formats_from_the_received_result(name):
    result = _over_the_wire(SYNTHETIC_RESULTS[name]())

    report = st.generate_report({name: result})

    assert st._TEST_TITLES[name] in report
    assert "report formatting failed" not in report


def test_report_of_a_whole_run_formats():
    results = {
        name: _over_the_wire(build()) for name, build in SYNTHETIC_RESULTS.items()
    }

    report = st.generate_report(results)

    assert "**Overall**" in report
    assert all(st._TEST_TITLES[name] in report for name in results)


def test_restore_nan_from_json_nulls_leaves_non_numeric_lists_alone():
    received = {"alarms": [], "shorts": [1], "names": ["a", None], "x": [None, None]}

    assert restore_nan_from_json_nulls(received) == received


def test_restore_nan_from_json_nulls_turns_null_numbers_back_into_nan():
    restored = restore_nan_from_json_nulls({"m": [[1.0, None], [None, 2]]})

    assert np.isnan(restored["m"][0][1]) and np.isnan(restored["m"][1][0])
    assert restored["m"][1][1] == 2
