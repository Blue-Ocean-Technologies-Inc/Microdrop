# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Build a tree's item widgets once their rows come into view (#1086).

An item widget — a section's header row, a row's spinners and dropdowns —
costs a millisecond or so to make, and the ROI table lists every plotted
experiment, so building them all on each rebuild froze the window for
hundreds of milliseconds. Each row's widgets are registered here instead and
built the first time the row is shown: inside the viewport, under expanded
parents. A rebuild then costs about a page of widgets, whatever the length
of the list, and scrolling builds the rows it reveals before they paint.
"""

# Enthought library imports.
from pyface.qt.QtCore import QEvent, QObject, QPoint


class LazyItemWidgets(QObject):
    """Item widget builders of a ``QTreeWidget``, run as their rows show."""

    def __init__(self, tree):
        super().__init__(tree)
        self._tree = tree

        #: The builder of each row whose widgets are not made yet. Keyed by
        #: the item: PySide hands back the same wrapper while it is held.
        self._pending = {}

        tree.verticalScrollBar().valueChanged.connect(self.build_visible)
        tree.itemExpanded.connect(self.build_visible)
        tree.viewport().installEventFilter(self)

    def defer(self, item, build):
        """Run ``build()`` — which sets ``item``'s widgets — once ``item``
        is shown; a later call for the same item replaces the earlier."""
        self._pending[item] = build

    def forget(self):
        """Drop every builder still waiting: the tree is being cleared."""
        self._pending = {}

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.build_visible()

        return False

    def build_visible(self, *args):
        """Build the widgets of every waiting row now in the viewport.
        Not while the tree's updates are off: it is being filled, and
        each look at where its rows are would lay it all out again."""
        if not self._pending or not self._tree.updatesEnabled():
            return

        tree = self._tree
        bottom = tree.viewport().height()
        item = tree.itemAt(QPoint(0, 0))

        while item is not None and tree.visualItemRect(item).top() < bottom:
            build = self._pending.pop(item, None)

            if build is not None:
                build()

            item = tree.itemBelow(item)
