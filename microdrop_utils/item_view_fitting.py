# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Grow the lists and tables inside a widget to show all their rows, so the
widget can sit in an outer scroll area at its natural height with no inner
scroll bars."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets


def fit_item_views(widget):
    """Grow every list and table in ``widget`` to all its rows, and again
    whenever its rows change or it is resized (rows can rewrap).

    Row changes come as inserts and removals, a reset, or a layout change:
    a TraitsUI table, for one, re-filters its proxy model when the list it
    shows grows, which reports only ``layoutChanged``."""

    for view in widget.findChildren(QtWidgets.QAbstractItemView):
        # A table's headers are item views too, but sized by their table:
        # fitted as views of no rows they were fixed 2 px tall, hiding the
        # column titles and leaving the rows past the first drawn blank.
        if isinstance(view, QtWidgets.QHeaderView):
            continue

        fit_item_view(view)

        # Fitted again once shown: an unshown header has no height yet.
        view.installEventFilter(_RefitOnResize(view))

        model = view.model()

        if model is None:
            continue

        signals = (
            model.rowsInserted,
            model.rowsRemoved,
            model.modelReset,
            model.layoutChanged,
        )

        # A table's rows can also grow after it is fitted, when a style or
        # font applied later changes their height.
        if isinstance(view, QtWidgets.QTableView):
            signals += (view.verticalHeader().sectionResized,)

        for signal in signals:
            signal.connect(lambda *args, view=view: _fit_later(view))


def fit_item_view(view):
    """Fix ``view``'s height to its rows, its header and its frame."""

    try:
        if isinstance(view, QtWidgets.QTableView):
            rows = view.verticalHeader().length()
            header = view.horizontalHeader()

            # Its size hint: its height is not set until the view is shown.
            header = 0 if header.isHidden() else header.sizeHint().height()

        else:
            rows = max(view.sizeHintForRow(0), 0) * view.model().rowCount()
            header = 0

    # Deleted with its parent before the deferred fit ran.
    except RuntimeError:
        return

    view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setFixedHeight(rows + header + 2 * view.frameWidth() + 2)


def _fit_later(view):
    QtCore.QTimer.singleShot(0, lambda: fit_item_view(view))


class _RefitOnResize(QtCore.QObject):
    """Fits its view again, once things settle, when its width changes or
    it is first shown."""

    def __init__(self, view):
        super().__init__(view)

        self._width = None

    def eventFilter(self, watched, event):
        resized = event.type() == QtCore.QEvent.Type.Resize

        if resized and event.size().width() != self._width:
            self._width = event.size().width()
            _fit_later(watched)

        return False
