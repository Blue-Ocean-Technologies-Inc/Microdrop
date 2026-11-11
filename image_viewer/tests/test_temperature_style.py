# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The temperature view's style: a row per sensor the loaded log carries."""

# Microdrop package imports.
from image_viewer.analysis.consts import DEFAULT_ROI_COLORS
from image_viewer.analysis.temperature_style import SensorStyle, TemperaturePlotStyle


def test_a_new_sensor_gets_a_default_row_and_unknown_rows_are_kept():
    styled = SensorStyle(sensor="old", color="#123456")
    kept = SensorStyle(sensor="t1", color="#abcdef", visible=False)
    style = TemperaturePlotStyle(sensors=[styled, kept])

    style.show_sensors(["t1", "t2"])

    assert [row.sensor for row in style.shown_sensors] == ["t1", "t2"]
    # The existing row is reused as it was styled.
    assert style.shown_sensors[0] is kept
    # The new one is a default row, coloured by its place in the cycle.
    new = style.shown_sensors[1]
    assert new.visible is True and new.alpha == 35
    assert new.color == DEFAULT_ROI_COLORS[2]
    # A sensor the log no longer carries keeps its row, unshown.
    assert [row.sensor for row in style.sensors] == ["old", "t1", "t2"]


def test_a_fresh_log_reproduces_the_unstyled_colour_cycle():
    style = TemperaturePlotStyle()

    style.show_sensors(["a", "b", "c"])

    assert [row.color for row in style.shown_sensors] == list(DEFAULT_ROI_COLORS[:3])


def test_the_capture_markers_follow_the_bold_line_by_default():
    style = TemperaturePlotStyle(line_color="#ff0000", capture_color="#00ff00")

    assert style.capture_plot_color == "#ff0000"

    style.capture_color_follows_line = False

    assert style.capture_plot_color == "#00ff00"
