# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The panel's own look, apart from the application's.

Each top-level part of the panel (the drawer, a toast, the settings
window) is an isolated root: it carries the panel's text font, handed down
to everything inside without a font of its own (contributed sections
included), and a style sheet scoped to its object name that gives the
panel's own values for whatever the application style sheet sets app-wide.
Only the theme (light or dark) still follows the application, from its
palette."""

# Enthought library imports.
from pyface.qt import QtCore, QtWidgets

# Microdrop style imports.
from microdrop_style.panel_theme import isolated_style_sheet, theme_palette
from microdrop_style.typography import BODY_TEXT, role_font

#: Widgets that never hold others, so need no watching for children.
_LEAVES = (QtWidgets.QLabel, QtWidgets.QAbstractButton)


def isolate(widget, name):
    """Make ``widget`` an isolated root named ``name`` (its object name,
    which its style sheet is scoped to)."""
    widget.setObjectName(name)
    widget.setFont(role_font(BODY_TEXT))
    widget.installEventFilter(_Restyle(widget))
    _HandDownFont(widget).watch(widget)
    _style(widget)


def _style(widget):
    widget.setStyleSheet(isolated_style_sheet(widget.objectName(), theme_palette()))


class _Restyle(QtCore.QObject):
    """Restyles its root for the new theme."""

    def eventFilter(self, watched, event):

        if event.type() == QtCore.QEvent.Type.ApplicationPaletteChange:
            _style(watched)

        return False


class _HandDownFont(QtCore.QObject):
    """Gives each widget under its root its parent's font, unless it has one
    of its own, as it is first polished.

    Qt hands a parent's font down only while no style sheet is in force;
    under the application's style sheet every widget starts from the
    application font, whatever its parent's."""

    def watch(self, widget):
        """Watch ``widget`` for children being polished, and those it
        already has."""
        widget.installEventFilter(self)

        for child in widget.findChildren(
            QtWidgets.QWidget, options=QtCore.Qt.FindChildOption.FindDirectChildrenOnly
        ):
            self._adopt(child)

    def eventFilter(self, watched, event):

        if event.type() == QtCore.QEvent.Type.ChildPolished:
            child = event.child()

            if child.isWidgetType() and not child.isWindow():
                self._adopt(child)

        return False

    def _adopt(self, widget):

        if not widget.testAttribute(QtCore.Qt.WidgetAttribute.WA_SetFont):
            widget.setFont(widget.parentWidget().font())

        if not isinstance(widget, _LEAVES):
            self.watch(widget)
