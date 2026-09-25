# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!


"""Sidebar section: liquid and filler capacitance calibration."""

# Enthought library imports.
from traits.api import Instance

# Local imports.
from ..calibration_view.widget import CalibrationController, CalibrationWidget
from .section import SidebarSection


class CalibrationSection(SidebarSection):
    """The Calibration section and the controller driving its widget."""

    #: Wires the calibration widget to the calibration model.
    calibration_controller = Instance(CalibrationController)


def build_calibration(calibration_model):
    """Build the Calibration section for the calibration model."""
    calibration_view = CalibrationWidget()
    calibration_controller = CalibrationController(
        model=calibration_model, view=calibration_view
    )

    return CalibrationSection(
        title="Calibration",
        widget=calibration_view,
        calibration_controller=calibration_controller,
    )
