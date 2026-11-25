# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The zoomable picture's zoom steps and limits."""

# Third-party imports.
import pytest

# Microdrop utils imports.
from microdrop_utils.picture_zoom import (
    MAX_ZOOM,
    ZOOM_STEP,
    clamped_zoom,
    double_click_zoom,
    fit_zoom,
    is_crisp,
    stepped_zoom,
    zoom_percent,
)


def test_fit_is_the_tighter_side():
    assert fit_zoom(2000, 1000, 1000, 1000) == pytest.approx(0.5)
    assert fit_zoom(100, 400, 800, 800) == pytest.approx(2.0)


def test_zoom_stays_between_fit_and_the_maximum():
    assert clamped_zoom(0.1, 0.25) == pytest.approx(0.25)
    assert clamped_zoom(100, 0.25) == pytest.approx(MAX_ZOOM)
    assert clamped_zoom(100, 12.0) == pytest.approx(12.0)


def test_a_step_multiplies_by_the_zoom_step():
    assert stepped_zoom(2.0, 1, 0.5) == pytest.approx(2.0 * ZOOM_STEP)
    assert stepped_zoom(2.0, -1, 0.5) == pytest.approx(2.0 / ZOOM_STEP)


def test_a_step_lands_on_actual_size_and_fit_when_it_passes_them():
    assert stepped_zoom(0.9, 1, 0.5) == pytest.approx(1.0)
    assert stepped_zoom(1.1, -1, 0.5) == pytest.approx(1.0)
    assert stepped_zoom(0.55, -1, 0.5) == pytest.approx(0.5)


def test_steps_stop_at_the_limits():
    assert stepped_zoom(0.5, -3, 0.5) == pytest.approx(0.5)
    assert stepped_zoom(MAX_ZOOM, 2, 0.5) == pytest.approx(MAX_ZOOM)


def test_double_click_toggles_fit_and_actual_size():
    assert double_click_zoom(0.4, 0.4) == pytest.approx(1.0)
    assert double_click_zoom(3.0, 0.4) == pytest.approx(0.4)


def test_double_click_from_a_fit_above_actual_size_doubles_it():
    assert double_click_zoom(1.5, 1.5) == pytest.approx(3.0)


def test_magnified_pictures_are_crisp_and_the_readout_is_a_percentage():
    assert not is_crisp(1.0)
    assert is_crisp(4.0)
    assert zoom_percent(1.5) == "150 %"
