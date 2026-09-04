# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Pure-logic tests for the SELF_TESTS_RESULTS payload and its results-file
round trip (#611): serialise a raw test result to JSON, validate the
`SelfTestResultsSignal` payload pointing at it, load the file back through
`load_self_test_results` (the same function the results dialog calls), and
confirm the restored dict still plots.
"""

# Standard library imports.
import json

# Third-party imports.
import matplotlib

matplotlib.use("Agg")

import numpy as np
from dropbot.self_test import (
    _generate_test_channels_results,
    plot_test_channels_results,
    plot_test_voltage_results,
)

from dropbot_controller.models.self_tests import (
    SelfTestResultsSignal,
    load_self_test_results,
    serialise_test_results,
)


def test_channels_results_round_trip(tmp_path):
    raw_results = _generate_test_channels_results()

    results_path = tmp_path / "test_channels_results.json"
    results_path.write_text(json.dumps(serialise_test_results(raw_results)))

    signal = SelfTestResultsSignal(
        test_name="test_channels",
        title="Test Channels Results",
        results_path=str(results_path),
        failed_channels=[1, 2],
    )
    round_tripped = SelfTestResultsSignal.model_validate_json(signal.model_dump_json())
    assert round_tripped.results_path == str(results_path)

    restored = load_self_test_results(round_tripped.results_path)
    assert isinstance(restored["c"], np.ndarray)
    assert restored["c"].shape == (len(raw_results["test_channels"]), 3)
    assert np.issubdtype(restored["c"].dtype, np.floating)

    _, fig = plot_test_channels_results(restored, return_fig=True)
    assert fig is not None


def test_voltage_results_round_trip(tmp_path):
    # Shape mirrors dropbot.hardware_test.test_voltage's return dict.
    raw_results = {
        "target_voltage": np.linspace(30, 150, 5),
        "measured_voltage": [31.2, 62.5, 93.1, 121.4, 149.8],
        "input_current": [0.01, 0.02, 0.03, 0.04, 0.05],
        "output_current": [0.005, 0.01, 0.015, 0.02, 0.025],
        "measured_voltage_no_load": [0.0, 0.0, 0.0, 0.0, 0.0],
        "input_current_no_load": [0.0, 0.0, 0.0, 0.0, 0.0],
        "output_current_no_load": [0.0, 0.0, 0.0, 0.0, 0.0],
        "input_voltage": np.float64(12.0),
        "delay": 0.1,
    }

    results_path = tmp_path / "test_voltage_results.json"
    results_path.write_text(json.dumps(serialise_test_results(raw_results)))

    signal = SelfTestResultsSignal(
        test_name="test_voltage",
        title="Test Voltage Results",
        results_path=str(results_path),
    )
    round_tripped = SelfTestResultsSignal.model_validate_json(signal.model_dump_json())

    restored = load_self_test_results(round_tripped.results_path)
    assert isinstance(restored["target_voltage"], np.ndarray)
    np.testing.assert_allclose(
        restored["target_voltage"], raw_results["target_voltage"]
    )
    np.testing.assert_allclose(
        restored["measured_voltage"], raw_results["measured_voltage"]
    )

    _, fig = plot_test_voltage_results(restored, return_fig=True)
    assert fig is not None


def test_load_self_test_results_missing_file_returns_none(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"

    assert load_self_test_results(str(missing_path)) is None
