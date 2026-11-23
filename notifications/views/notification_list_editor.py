# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The notifications list: a TraitsUI editor over a NotificationCenter.

TraitsUI has no editor for a list of painted cards with inline expansion and
buttons, hence a Qt list view with a delegate inside a small TraitsUI editor.
The editor writes the user's clicks back as the context object's
``dismiss`` and ``run_action`` events and the entry's ``expanded`` flag; it
holds no other logic.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traits.api import Any, Instance
from traitsui.api import BasicEditorFactory
from traitsui.qt.editor import Editor

# Local imports.
from ..consts import TIME_REFRESH_MS
from .notification_delegate import NotificationDelegate
from .notification_list_model import (
    ENTRY_ROLE,
    NotificationListBridge,
    NotificationListModel,
)

#: Shown in an empty list.
EMPTY_LIST_TEXT = "Nothing new"


class NotificationListView(QtWidgets.QListView):
    """Cards in a pixel-scrolled list; an expanded card's detail viewer is
    opened as its persistent editor and closed when it collapses."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.viewport().setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        # Unfilled: the cards lie on whatever is behind the list, which the
        # notifications drawer paints translucent.
        self.viewport().setAutoFillBackground(False)

        #: Repaints the relative times; runs only while the list is shown.
        self._time_refresh = QtCore.QTimer(self)
        self._time_refresh.setInterval(TIME_REFRESH_MS)
        self._time_refresh.timeout.connect(self.viewport().update)

    def setModel(self, model):
        super().setModel(model)

        model.rowsInserted.connect(self._follow_inserted_rows)
        model.modelReset.connect(self._follow_all_rows)
        model.dataChanged.connect(self._follow_changed_rows)

    def showEvent(self, event):
        """Keep the times current while shown: the pane opened or its tab
        raised."""
        super().showEvent(event)

        self.viewport().update()
        self._time_refresh.start()

    def hideEvent(self, event):
        """Nothing runs while the pane is hidden or behind another tab."""
        super().hideEvent(event)

        self._time_refresh.stop()

    def paintEvent(self, event):
        """Say the list is empty rather than show nothing."""

        if self.model() is not None and self.model().rowCount():
            super().paintEvent(event)

            return

        painter = QtGui.QPainter(self.viewport())
        painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.PlaceholderText))
        painter.drawText(
            self.viewport().rect(), QtCore.Qt.AlignmentFlag.AlignCenter, EMPTY_LIST_TEXT
        )

    def _follow_inserted_rows(self, parent, first, last):
        self._follow_expansion(first, last)

    def _follow_all_rows(self):
        self._follow_expansion(0, self.model().rowCount() - 1)

    def _follow_changed_rows(self, top_left, bottom_right, roles=()):
        self._follow_expansion(top_left.row(), bottom_right.row())

        # A change can grow or shrink the card. Delayed, so a burst of
        # changes lays the list out once; the delegate's sizeHintChanged
        # would lay it all out again for each.
        self.scheduleDelayedItemsLayout()

    def _follow_expansion(self, first, last):
        """Open or close each row's detail viewer to match its entry."""

        for row in range(first, last + 1):
            index = self.model().index(row)
            expanded = index.data(ENTRY_ROLE).expanded
            open_ = self.isPersistentEditorOpen(index)

            if expanded and not open_:
                self.openPersistentEditor(index)

            elif open_ and not expanded:
                self.closePersistentEditor(index)


class _NotificationListEditor(Editor):
    """Shows the edited NotificationCenter as a NotificationListView."""

    #: Keeps the Qt model in step with the center.
    _bridge = Instance(NotificationListBridge)

    #: The view's delegate, held for its signals.
    _delegate = Any()

    def init(self, parent):
        self.control = view = NotificationListView()
        qt_model = NotificationListModel(view)

        view.setModel(qt_model)

        self._delegate = delegate = NotificationDelegate(view)
        view.setItemDelegate(delegate)

        delegate.dismiss_requested.connect(self._request_dismiss)
        delegate.action_requested.connect(self._request_action)
        delegate.expand_toggled.connect(self._toggle_expanded)

        self._bridge = NotificationListBridge(qt_model=qt_model, center=self.value)

    def update_editor(self):
        """The center was replaced."""

        if self._bridge is not None:
            self._bridge.center = self.value

    def dispose(self):
        """Detach from the center, which outlives the pane."""

        if self._bridge is not None:
            self._bridge.center = None
            self._bridge = None

        super().dispose()

    def _request_dismiss(self, entry):
        self.object.dismiss = entry

    def _request_action(self, entry):
        self.object.run_action = entry

    def _toggle_expanded(self, entry):
        entry.expanded = not entry.expanded


class NotificationListEditor(BasicEditorFactory):
    """Edit a NotificationCenter trait as a list of notification cards;
    the context object needs ``dismiss`` and ``run_action`` events."""

    klass = _NotificationListEditor
