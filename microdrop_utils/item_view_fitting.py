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
    whenever their rows change."""

    for view in widget.findChildren(QtWidgets.QAbstractItemView):
        fit_item_view(view)

        model = view.model()

        if model is None:
            continue

        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset):
            signal.connect(lambda *args, view=view: _fit_later(view))


def fit_item_view(view):
    """Fix ``view``'s height to its rows, its header and its frame."""

    try:
        if isinstance(view, QtWidgets.QTableView):
            rows = view.verticalHeader().length()
            header = view.horizontalHeader().height()

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
