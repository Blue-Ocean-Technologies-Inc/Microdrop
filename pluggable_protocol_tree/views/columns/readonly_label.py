# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Non-editable text column. Used for type, id, and any derived cells."""

from pyface.qt.QtCore import Qt
from traits.api import provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class ReadOnlyLabelColumnView(BaseColumnView):
    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable   # no editable flag

    def create_editor(self, parent, context):
        return None
