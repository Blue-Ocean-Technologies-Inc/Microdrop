# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Editable line-edit column view for Str-typed columns."""

from pyface.qt.QtCore import Qt
from pyface.qt.QtWidgets import QLineEdit
from traits.api import provides

from pluggable_protocol_tree.interfaces.i_column import IColumnView
from pluggable_protocol_tree.views.columns.base import BaseColumnView


@provides(IColumnView)
class StringEditColumnView(BaseColumnView):
    def get_flags(self, row):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def create_editor(self, parent, context):
        return QLineEdit(parent)

    def set_editor_data(self, editor, value):
        editor.setText("" if value is None else str(value))

    def get_editor_data(self, editor):
        return editor.text()
