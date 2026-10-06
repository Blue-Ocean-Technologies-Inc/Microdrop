# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Package-level constants for video_protocol_controls.

Topic constants live in device_viewer/consts.py — this plugin
imports them. See PPT-6 spec section 2 for the layering reasoning.
"""

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

# Executor-scratch key carrying the active experiment directory; read by
# the capture/record handlers to aim media at the experiment folder.
EXPERIMENT_DIR_SCRATCH_KEY = "experiment_dir"


class StepTime:
    """Values of the Capture column's per-step capture_at cell. Plain str
    constants, NOT a Python enum — they are persisted in protocol JSON and
    compared as bare strings."""

    END = "Step End"
    START = "Step Start"
