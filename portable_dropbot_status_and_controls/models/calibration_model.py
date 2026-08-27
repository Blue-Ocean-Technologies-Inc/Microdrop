# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.api import Bool, Button, Enum, Range, Str

from portable_dropbot_controller.consts import (
    CAL_CAPS_CHOICES, DEFAULT_ELECTRODE_GAIN_PERMILLE,
    ELECTRODE_GAIN_PERMILLE_BOUNDS,
)
from template_status_and_controls.base_model import BaseStatusModel

from ..consts import PORTABLE_DROPBOT_IMAGE


class PortableDropbotCalibrationModel(BaseStatusModel):
    """Qt-free state for the calibration pane: the validated ML
    calibration macro plus the ML-path/gain/cal-caps provisioning
    around it. Mutated only on the GUI thread."""

    DEFAULT_ICON_PATH = PORTABLE_DROPBOT_IMAGE

    run_calibration_button = Button("Run ML Calibration")
    calibration_status = Str("-", desc="Last macro stage / outcome")

    ml_realtime = Bool(False, desc="ML-fitted realtime capacitance "
                                   "path (off = legacy path)")

    electrode_gain = Range(*ELECTRODE_GAIN_PERMILLE_BOUNDS,
                           DEFAULT_ELECTRODE_GAIN_PERMILLE,
                           mode="spinner",
                           desc="Electrode-path gain (permille), "
                                "EF-persisted on the board")
    read_gain_button = Button("Read")
    apply_gain_button = Button("Apply")

    cal_caps = Enum(*CAL_CAPS_CHOICES,
                    desc="Reference-cap count: 3 = 10/100/470 pF "
                         "board, 5 = new board adds 1000/2200 pF")
    read_cal_caps_button = Button("Read")
    apply_cal_caps_button = Button("Apply")
