# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Building the device viewer's model raises in no change handler: its
``electrodes`` are assigned before its ``calibration`` exists, and the
volume estimate waits for both."""

# Enthought library imports.
from traits.api import pop_exception_handler, push_exception_handler

# Microdrop package imports.
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.preferences import DeviceViewerPreferences


def test_building_the_model_raises_in_no_handler():
    push_exception_handler(reraise_exceptions=True)

    try:
        model = DeviceViewMainModel(preferences=DeviceViewerPreferences())

    finally:
        pop_exception_handler()

    assert model.volume_estimate.capacitance_pf == model.calibration.last_capacitance
