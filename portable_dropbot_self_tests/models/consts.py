# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Constants of the self-test hub's models: the vendor test names the hub
gives parameters or figures to, the parameter bounds, and the words the
panel shows. The test catalogue itself (order, titles, pad needs, default
repeats) comes from ``dropbot_portable.self_test``."""

# Local imports.
from ..consts import UNSAVED_CALIBRATION, UNSAVED_TARE

VOLTAGE_TEST = "test_voltage"
CALIBRATION_TEST = "test_on_board_feedback_calibration"
CHANNELS_TEST = "test_channels"

#: Tests that collect information only, so "no verdict" is their normal end.
INFO_TESTS = ("system_info", "test_system_metrics", "test_boards")

# Parameter bounds, as the vendor's self-test tab sets its spin boxes (the
# run time grows linearly with the repeat counts).
VOLTAGE_POINTS_BOUNDS = (2, 20)
CALIBRATION_REPLICATES_BOUNDS = (1, 50)
CHANNELS_REPLICATES_BOUNDS = (1, 20)
CHANNELS_THRESHOLD_PF_BOUNDS = (0.5, 100.0)
CALIBRATION_MIN_COUNTS_BOUNDS = (1.0, 2000.0)
CALIBRATION_MAX_RAIL_PCT_BOUNDS = (0.0, 50.0)

#: The pads label of a test, keyed by the vendor's TEST_PADS values.
PADS_LABELS = {"any": "either", "up": "up", "down": "pressed"}

# Outcome words of a test row.
OUTCOME_NONE = "–"
OUTCOME_QUEUED = "queued"
OUTCOME_RUNNING = "running..."
OUTCOME_NOT_RUN = "not run"
OUTCOME_PASS = "pass"
OUTCOME_FAIL = "FAIL"
OUTCOME_ERROR = "ERROR"
OUTCOME_STOPPED = "stopped"
OUTCOME_INFO_DONE = "done (no verdict)"
OUTCOME_NO_VERDICT = "n/a"

#: How the panel names each RAM-only calibration part.
UNSAVED_PART_LABELS = {
    UNSAVED_CALIBRATION: "feedback-cap calibration",
    UNSAVED_TARE: "electrode tare (STATUS chip_cap baseline)",
}

#: Figure views of the tests that have more than one, as EnumEditor values
#: (the "N:" prefixes order the choices). The first is the default.
PLOT_VIEW_LABELS = {
    CHANNELS_TEST: {
        "calibrated": "1:Corrected (baseline removed)",
        "raw": "2:Raw (firmware value)",
    },
    CALIBRATION_TEST: {
        "all": "1:All tested points",
        "valid": "2:Valid points only",
        "raw": "3:Raw (none not subtracted)",
    },
}

#: The figure view of a test with a single figure.
DEFAULT_PLOT_VIEW = "calibrated"

#: The hub's output views; a run opens the Report (vendor rule).
OUTPUT_VIEW_REPORT = "Report"
OUTPUT_VIEW_PLOTS = "Plots"

#: The backend's refusal reason for a request while disconnected; a preflight
#: reply carrying it pauses the polling.
PREFLIGHT_DISCONNECTED_ERROR = "Portable Dropbot is disconnected"

#: Report files saved as Markdown; any other suffix gets the HTML report.
MARKDOWN_REPORT_SUFFIXES = (".md", ".markdown", ".txt")
