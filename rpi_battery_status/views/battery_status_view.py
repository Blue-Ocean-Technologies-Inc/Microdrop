# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The battery icon for the app status bar: fill glyph plus percent text.

A left click (or touch tap) on the icon calls an injected callback, which
the plugin uses to open the details panel.

Runs standalone against just the model:
``BatteryStatus().edit_traits(view=BatteryStatusIconView)``.
"""

# Enthought library imports.
from pyface.qt import QtCore, QtGui, QtWidgets
from traitsui.api import Handler, HGroup, TextEditor, UItem, View

# Microdrop package imports.
from microdrop_status_bar.consts import ICON_PRIORITY_LEFTMOST

# Microdrop style imports.
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE

# Local imports.
from ..consts import LEVEL_COLORS

# Plain labels let presses through to the clickable host widget; selectable
# ones would swallow them.
_UNSELECTABLE_TEXT = TextEditor(readonly_allow_selection=False)


class _ClickableIcon(QtWidgets.QWidget):
    """Status-bar host widget that calls ``on_click`` on a left press.

    Qt synthesises a left press from an unhandled touch tap, so a tap on
    the touch panel counts as a click.
    """

    def __init__(self, on_click=None):
        super().__init__()
        self._on_click = on_click

        if on_click is not None:
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        """Call ``on_click`` for a left press; pass anything else on."""
        if self._on_click is None or event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        event.accept()
        self._on_click()


class BatteryStatusIconHandler(Handler):
    """Render the icon: glyph font, level colour, and tooltip.

    The ``object_<trait>_changed`` hooks run once at init and on every
    change, and TraitsUI unhooks them when the UI is disposed.
    """

    def init(self, info):
        """Set the glyph font and drop the panel margins."""
        font = QtGui.QFont(ICON_FONT_FAMILY)
        font.setPointSize(STATUSBAR_ICON_POINT_SIZE)
        info.glyph.control.setFont(font)

        layout = info.ui.control.layout()

        if layout is not None:
            layout.setContentsMargins(0, 0, 0, 0)

        return True

    def object_level_changed(self, info):
        """Grey or red for the levels that have a colour, else text colour."""
        color = LEVEL_COLORS.get(info.object.level)
        style = "" if color is None else f"color: {color};"

        info.glyph.control.setStyleSheet(style)
        info.percent_text.control.setStyleSheet(style)

    def object_tooltip_changed(self, info):
        """Show the details on hover anywhere over the icon."""
        info.ui.control.setToolTip(info.object.tooltip)


BatteryStatusIconView = View(
    HGroup(
        UItem("glyph", style="readonly", editor=_UNSELECTABLE_TEXT),
        UItem("percent_text", style="readonly", editor=_UNSELECTABLE_TEXT),
    ),
    handler=BatteryStatusIconHandler,
)


def build_status_bar_icon(model, on_click=None):
    """Return the battery icon widget for ``model`` and its TraitsUI UI.

    The widget is what the status bar takes, placed leftmost. TraitsUI only
    builds a bare subpanel (no dialog) inside a parent, so the widget hosts
    the UI's control. Dispose the UI when the icon is withdrawn so its
    handler stops observing the model.

    ``on_click``, a zero-argument callable, runs on each left click or tap.
    """
    icon = _ClickableIcon(on_click)
    icon.status_bar_icon_priority = ICON_PRIORITY_LEFTMOST

    ui = model.edit_traits(view=BatteryStatusIconView, parent=icon, kind="subpanel")

    layout = QtWidgets.QHBoxLayout(icon)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(ui.control)

    return icon, ui
