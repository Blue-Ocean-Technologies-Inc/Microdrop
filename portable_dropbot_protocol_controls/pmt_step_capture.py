# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The PMT step-capture value contract: the pmt_capture column's cell, a
`PmtStepCapture` (see step_capture.py for the shared parse/normalize/summary
rules and the start/end phases)."""

# Microdrop package imports.
from portable_dropbot_controller.consts import PmtStepCapture

# Local imports.
from .step_capture import StepCaptureCodec

#: The pmt_capture cell's codec; the names below are its public API.
_codec = StepCaptureCodec(model=PmtStepCapture, kind="PMT", noun="spot")

parse_step_capture = _codec.parse
normalize_step_capture = _codec.normalize
summary_text = _codec.summary_text
