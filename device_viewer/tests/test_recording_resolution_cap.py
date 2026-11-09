# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Recording resolution cap: streams larger than full HD downscale with the
aspect ratio kept and even sides; smaller streams record unchanged."""

# Third-party imports.
import pytest

# Microdrop package imports.
from device_viewer.consts import MAX_RECORDING_RESOLUTION
from device_viewer.utils.recording.base import fit_recording_resolution


@pytest.mark.parametrize(
    "stream, expected",
    [
        ((4608, 2592), (1920, 1080)),
        ((2048, 1536), (1440, 1080)),
        ((1600, 1200), (1440, 1080)),
        ((1280, 720), (1280, 720)),
        (MAX_RECORDING_RESOLUTION, MAX_RECORDING_RESOLUTION),
    ],
)
def test_fit_recording_resolution(stream, expected):
    assert fit_recording_resolution(*stream) == expected


def test_capped_sides_are_even():
    width, height = fit_recording_resolution(2593, 1945)

    assert width % 2 == 0 and height % 2 == 0
    assert width <= MAX_RECORDING_RESOLUTION[0]
    assert height <= MAX_RECORDING_RESOLUTION[1]
