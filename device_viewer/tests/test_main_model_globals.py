# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Loading a device publishes its SVG path and the repo dir to app globals —
and, under test, into the conftest's dict rather than a running app's Redis."""

# Standard library imports.
from pathlib import Path

# Microdrop package imports.
from device_viewer.consts import DEVICE_REPO_DIR_KEY, DEVICE_SVG_PATH_KEY
from device_viewer.models import main_model
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences

BUNDLED_2X3 = (
    Path(__file__).resolve().parents[1] / "resources" / "devices" / "2x3device.svg"
)


def test_device_load_publishes_into_isolated_globals():
    preferences = DeviceViewerPreferences()
    model = DeviceViewMainModel(preferences=preferences)

    model.electrodes.set_electrodes_from_svg_file(str(BUNDLED_2X3))

    assert main_model.app_globals == {
        DEVICE_SVG_PATH_KEY: str(BUNDLED_2X3),
        DEVICE_REPO_DIR_KEY: str(preferences.DEVICE_REPO_DIR),
    }
