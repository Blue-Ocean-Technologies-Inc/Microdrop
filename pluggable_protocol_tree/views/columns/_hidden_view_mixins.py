# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tiny ``hidden_by_default = True`` overrides of the PPT-1 base views.

Used by the 6 trail/loop/ramp config columns shipped in PPT-3 — those
columns are sometimes-needed knobs, not always-visible columns. The
ProtocolTreeWidget reads ``view.hidden_by_default`` after model
attach and calls ``tree.setColumnHidden(idx, True)`` for any column
where it's True.
"""

from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.columns.spinbox import (
    DoubleSpinBoxColumnView, IntSpinBoxColumnView,
)


class HiddenIntSpinBoxColumnView(IntSpinBoxColumnView):
    hidden_by_default = True


class HiddenDoubleSpinBoxColumnView(DoubleSpinBoxColumnView):
    hidden_by_default = True


class HiddenCheckboxColumnView(CheckboxColumnView):
    hidden_by_default = True
