# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the Qt-free scale-bar maths."""

# Microdrop package imports.
from image_viewer.scale_bar import (
    DEFAULT_UNIT,
    area_unit,
    format_length,
    metres_per_pixel,
    nice_scale,
    pixel_area,
)


def test_default_unit_is_millimetres():
    assert DEFAULT_UNIT == "mm"


def test_metres_per_pixel_from_a_drawn_line():
    # A 200 px line the user calls 2 mm: 10 µm per pixel.
    assert abs(metres_per_pixel(200.0, 2.0, "mm") - 1e-5) < 1e-18


def test_metres_per_pixel_refuses_a_misclick_or_an_empty_value():
    assert metres_per_pixel(2.0, 5.0, "mm") is None
    assert metres_per_pixel(200.0, 0.0, "mm") is None
    assert metres_per_pixel(200.0, -3.0, "mm") is None


def test_nice_scale_snaps_down_to_one_two_or_five():
    # 120 px of bar spans 1.7 mm -> the bar reads 1 mm and shrinks.
    bar_px, label = nice_scale(1.7e-3 / 120.0)
    assert label == "1 mm"
    assert abs(bar_px - 120.0 * (1.0 / 1.7)) < 0.5

    assert nice_scale(6e-3 / 120.0)[1] == "5 mm"
    assert nice_scale(2.4e-3 / 120.0)[1] == "2 mm"


def test_nice_scale_changes_unit_as_the_view_zooms():
    # Same target width, finer and finer pixels.
    assert nice_scale(4e-3 / 120.0)[1] == "2 mm"
    assert nice_scale(4e-4 / 120.0)[1] == "200 µm"
    assert nice_scale(4e-7 / 120.0)[1] == "200 nm"


def test_nice_scale_without_a_calibration():
    assert nice_scale(0.0) is None
    assert nice_scale(float("nan")) is None
    assert nice_scale(-1.0) is None


def test_format_length_picks_the_readable_unit():
    assert format_length(40.0) == "40 m"
    assert format_length(0.5) == "50 cm"
    assert format_length(5e-4) == "500 µm"
    assert format_length(1e-9) == "1 nm"
    # Below a nanometre it clamps rather than reading "0 nm".
    assert format_length(1e-12).endswith("nm")


def test_pixel_area_squares_the_calibration():
    # 10 µm per pixel, reported in mm: (0.01 mm)^2 = 1e-4 mm^2.
    assert abs(pixel_area(1e-5, "mm") - 1e-4) < 1e-12
    # The same calibration in µm: 10 µm x 10 µm = 100 µm^2.
    assert abs(pixel_area(1e-5, "µm") - 100.0) < 1e-9


def test_pixel_area_without_a_calibration_is_one_square_pixel():
    assert pixel_area(0.0, "mm") == 1.0
    assert pixel_area(-1.0, "mm") == 1.0


def test_area_unit_says_pixels_until_calibrated():
    assert area_unit(1e-5, "mm") == "mm²"
    assert area_unit(1e-5, "µm") == "µm²"
    assert area_unit(0.0, "mm") == "px²"
