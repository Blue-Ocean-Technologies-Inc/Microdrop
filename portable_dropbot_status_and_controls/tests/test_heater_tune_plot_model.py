# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The heater auto-tune live plot: the FOPDT simulation matches the
analytic step response, readings are buffered (missing ones skipped, the
oldest dropped past the cap), a run's first progress starts a fresh plot,
and a verify run's outcome is summarised and seeds the next set point.
Qt-free, no Redis."""

# Standard library imports.
import math

# Third-party imports.
import numpy as np
import pytest

# Microdrop package imports.
from portable_dropbot_controller.consts import (
    HEATER_TUNE_MARGIN_C,
    HEATER_TUNE_VERIFY_PHASE,
    HeaterTuneDone,
    HeaterTuneProgress,
    HeaterTuneVerifyDone,
)
from portable_dropbot_status_and_controls.consts import (
    HEATER_TUNE_VERIFY_SETPOINT_STEP_C,
)
from portable_dropbot_status_and_controls.models import heater_tune_plot_model
from portable_dropbot_status_and_controls.models.heater_tune_model import (
    HeaterTuneModel,
)
from portable_dropbot_status_and_controls.models.heater_tune_plot_model import (
    HeaterTunePlot,
    simulate_fopdt,
)

# --------------------------------------------------------------------- #
# The FOPDT simulation                                                   #
# --------------------------------------------------------------------- #


def test_a_step_response_follows_the_analytic_curve():
    times_s = np.arange(0.0, 200.0, 1.0)
    inputs_pct = np.where(times_s >= 10.0, 20.0, 0.0)

    response = simulate_fopdt(times_s, inputs_pct, 0.5, 40.0, 5.0, 25.0)

    # The step lands at 10 s and shows after the 5 s dead time.
    moved = times_s - 15.0
    expected = 25.0 + 0.5 * 20.0 * (1.0 - np.exp(-np.clip(moved, 0, None) / 40.0))

    assert response == pytest.approx(expected, abs=0.05)


def test_the_model_rests_at_its_start_without_an_input_change():
    response = simulate_fopdt([0.0, 1.0, 2.0], [30.0, 30.0, 30.0], 0.5, 40.0, 2.0, 31.0)

    assert response == pytest.approx([31.0, 31.0, 31.0])


def test_too_few_readings_give_the_start_temperature():
    assert simulate_fopdt([0.0], [20.0], 0.5, 40.0, 2.0, 25.0).tolist() == [25.0]


# --------------------------------------------------------------------- #
# The plot's buffer and figure                                          #
# --------------------------------------------------------------------- #


def test_missing_readings_are_skipped_and_the_figure_drawn():
    plot = HeaterTunePlot()

    plot.add_reading(0.0, None, 0.0)

    assert plot.samples == [] and plot.figure is None

    plot.add_reading(1.0, 25.0, 0.0)
    plot.add_reading(2.0, 25.5, 20.0)

    assert plot.samples == [(1.0, 25.0, 0.0), (2.0, 25.5, 20.0)]
    assert plot.figure is not None
    assert list(plot._temperature_line.get_ydata()) == [25.0, 25.5]


def test_the_oldest_readings_drop_past_the_cap(monkeypatch):
    monkeypatch.setattr(heater_tune_plot_model, "HEATER_TUNE_PLOT_MAX_SAMPLES", 3)
    plot = HeaterTunePlot()

    for second in range(5):
        plot.add_reading(float(second), 25.0 + second, 0.0)

    assert [sample[0] for sample in plot.samples] == [2.0, 3.0, 4.0]


def test_begin_clears_the_run_and_keeps_its_set_point():
    plot = HeaterTunePlot()
    plot.add_reading(1.0, 25.0, 0.0)
    plot.add_reading(2.0, 26.0, 20.0)
    plot.overlay_fopdt(0.5, 40.0, 2.0)

    assert plot.model_temperatures_c

    plot.begin(45.0)

    assert plot.samples == [] and plot.model_temperatures_c == []
    assert plot.setpoint_c == 45.0 and plot.figure is None


def test_the_fitted_model_is_drawn_over_the_capture():
    plot = HeaterTunePlot()

    for second in range(30):
        plot.add_reading(float(second), 25.0, 20.0 if second >= 10 else 0.0)

    plot.overlay_fopdt(0.5, 40.0, 2.0, y0_c=24.0)

    assert len(plot.model_temperatures_c) == 30
    assert plot.model_temperatures_c[0] == pytest.approx(24.0)
    assert any(line.get_label() == "Fitted model" for line in plot.figure.axes[0].lines)


# --------------------------------------------------------------------- #
# The tune model's use of it                                             #
# --------------------------------------------------------------------- #


def _progress(elapsed_s, current_c, **fields):
    fields = {"channel": 0, "phase": "step", **fields}

    return HeaterTuneProgress(elapsed_s=elapsed_s, current_c=current_c, **fields)


def test_a_runs_first_progress_starts_a_fresh_plot():
    tune = HeaterTuneModel()
    tune.adopt_progress(_progress(1.0, 25.0))
    tune.adopt_progress(_progress(2.0, 26.0, duty_pct=20))
    tune.adopt_done(HeaterTuneDone(channel=0, ok=False, reason="cancelled"))

    tune.adopt_progress(
        _progress(1.0, 30.0, phase=HEATER_TUNE_VERIFY_PHASE, setpoint_c=40.0)
    )

    assert tune.plot.samples == [(1.0, 30.0, 0.0)]
    assert tune.plot.setpoint_c == 40.0
    assert "to 40 °C" in tune.status


def _verify_done(**fields):
    return HeaterTuneVerifyDone(
        channel=1,
        setpoint_c=40.0,
        band_c=0.5,
        metrics={
            "dead_time_s": 3.0,
            "rise_s": 42.0,
            "overshoot_pct": 1.25,
            "settle_s": 88.0,
            "sse_c": 0.04,
            "settled": True,
        },
        **fields,
    )


def test_a_verify_outcome_is_summarised():
    tune = HeaterTuneModel(running=True)

    tune.adopt_verify_done(_verify_done(ok=True, reason="settled within ±0.5 C"))

    assert not tune.running
    assert tune.verify_display == (
        "ch1 to 40 °C: dead time 3 s, rise 42 s, overshoot 1.2 %, settled in "
        "88 s (±0.5 °C), steady-state error +0.04 °C"
    )
    assert "verify done" in tune.status


def test_a_refused_verify_keeps_the_last_figures():
    tune = HeaterTuneModel(verify_display="earlier")

    tune.adopt_verify_done(HeaterTuneVerifyDone(channel=0, ok=False, reason="ch1 on"))

    assert tune.verify_display == "earlier"
    assert tune.status == "ch0: verify: no result: ch1 on"


@pytest.mark.parametrize(
    "last_c, max_temp_c, expected",
    [
        (28.0, 50.0, 28.0 + HEATER_TUNE_VERIFY_SETPOINT_STEP_C),
        (45.0, 50.0, 50.0 - HEATER_TUNE_MARGIN_C),
    ],
)
def test_the_next_set_point_stays_below_the_cap(last_c, max_temp_c, expected):
    tune = HeaterTuneModel(max_temp_c=max_temp_c)
    tune.adopt_progress(_progress(1.0, last_c))

    tune.adopt_verify_done(_verify_done(ok=True, reason="time limit"))

    assert math.isclose(tune.verify_setpoint_c, expected)
