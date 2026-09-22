# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""PMT and fluorescence capture are exclusive per step: a step drives either
the PMT (fluorescence LED dark, PMT stream) or the camera with the
fluorescence LED lit, never both. The capture panes stop the operator from
setting both up; this is the run-time guard for a protocol that has them
anyway (hand-edited or older)."""

# Local imports.
from .consts import FLUORESCENCE_CAPTURE_COLUMN_ID, PMT_CAPTURE_COLUMN_ID

#: The per-step capture columns, of which a step may set only one.
CAPTURE_COLUMN_IDS = (PMT_CAPTURE_COLUMN_ID, FLUORESCENCE_CAPTURE_COLUMN_ID)


def check_single_capture(row):
    """Refuse a step that sets more than one capture column (a stored
    capture cell is None when empty)."""
    if all(getattr(row, col_id, None) for col_id in CAPTURE_COLUMN_IDS):
        raise RuntimeError(
            f"Step {row.dotted_path()} sets both PMT and fluorescence capture; "
            "a step can run only one — clear one of them"
        )
