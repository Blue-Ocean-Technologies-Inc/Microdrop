# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications as a Qt list model, kept in step row by row.

A new entry inserts one row and an updated one repaints its row, so the
list never rebuilds as notifications arrive; rows are painted by a delegate,
so no row owns a widget.
"""

# Enthought library imports.
from pyface.qt import QtCore
from traits.api import Any, HasTraits, Instance, observe

# Local imports.
from ..models.notification_center import NotificationCenter

#: Data role returning a row's Notification.
ENTRY_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1


class NotificationListModel(QtCore.QAbstractListModel):
    """Rows mirroring a NotificationCenter's entries."""

    def __init__(self, parent=None):
        super().__init__(parent)

        #: The rows' entries; changed only between begin/end row calls.
        self._entries = []

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.isValid():
            return 0

        return len(self._entries)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        entry = self._entries[index.row()]

        if role == ENTRY_ROLE:
            return entry

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return entry.title

        return None

    def reset_entries(self, entries):
        """Show ``entries`` in place of every row."""
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def insert_entries(self, row, entries):
        if not entries:
            return

        self.beginInsertRows(QtCore.QModelIndex(), row, row + len(entries) - 1)
        self._entries[row:row] = entries
        self.endInsertRows()

    def remove_entries(self, row, count):
        if not count:
            return

        self.beginRemoveRows(QtCore.QModelIndex(), row, row + count - 1)
        del self._entries[row : row + count]
        self.endRemoveRows()

    def entry_changed(self, entry):
        """Repaint ``entry``'s row."""

        for row, listed in enumerate(self._entries):
            if listed is entry:
                index = self.index(row)
                self.dataChanged.emit(index, index)

                return


class NotificationListBridge(HasTraits):
    """Forwards a NotificationCenter's changes to a NotificationListModel."""

    #: The notifications shown; None detaches the bridge.
    center = Instance(NotificationCenter)

    #: The Qt model kept in step.
    qt_model = Any()

    @observe("center")
    def _show_center(self, event):
        if self.qt_model is None:
            return

        self.qt_model.reset_entries([] if event.new is None else event.new.entries)

    @observe("center:entries")
    def _show_replaced_entries(self, event):
        self.qt_model.reset_entries(event.new)

    @observe("center:entries:items")
    def _show_entry_rows(self, event):
        self.qt_model.remove_entries(event.index, len(event.removed))
        self.qt_model.insert_entries(event.index, event.added)

    @observe("center:entries:items:changed")
    def _repaint_entry(self, event):
        self.qt_model.entry_changed(event.object)
