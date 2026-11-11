# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The battery details panel the status-bar icon opens when clicked.

A live view, so the open panel follows every poll. TraitsUI's Qt backend
does not implement the ``popup`` / ``popover`` / ``info`` kinds, so the
handler turns the ``live`` dialog into a Qt popup: frameless, anchored to
the icon, closed by a click (or tap) anywhere outside it or by Escape.

Runs standalone against just the model:
``BatteryStatus().edit_traits(view=BatteryDetailsView)``.
"""

# Enthought library imports.
from pyface.qt import QtCore
from traitsui.api import Handler, Item, NoButtons, UItem, VGroup, View


class _IconPressReplayBlocker(QtCore.QObject):
    """Keep the press that closes the panel from reopening it.

    Qt replays a press that closes a popup to the widget underneath, so a
    second click on the icon would close the panel and open a fresh one;
    a press on the anchor itself is not replayed, making the icon a toggle.
    """

    def eventFilter(self, watched, event):
        """Mark presses on the anchor widget as not to be replayed."""
        anchor = watched.parentWidget()

        if anchor is not None and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            point = anchor.mapFromGlobal(event.globalPosition().toPoint())

            if anchor.rect().contains(point):
                watched.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoMouseReplay)

        return False


class BatteryDetailsHandler(Handler):
    """Show the live dialog as a popup anchored to its parent widget."""

    def init(self, info):
        """Make the panel a popup: frameless, closed by a click outside."""
        panel = info.ui.control
        panel.setWindowFlags(QtCore.Qt.WindowType.Popup)
        panel.installEventFilter(_IconPressReplayBlocker(panel))

        return True

    def position(self, info):
        """Open just above the anchor, or below it without room, on screen."""
        panel = info.ui.control
        anchor = panel.parentWidget()

        if anchor is None:
            return

        size = panel.sizeHint()
        anchor_top_left = anchor.mapToGlobal(QtCore.QPoint(0, 0))
        screen = anchor.screen().availableGeometry()

        x = anchor_top_left.x()
        y = anchor_top_left.y() - size.height()

        if y < screen.top():
            y = anchor_top_left.y() + anchor.height()

        x = max(screen.left(), min(x, screen.right() - size.width()))

        panel.move(x, y)


BatteryDetailsView = View(
    VGroup(
        UItem("headline", style="readonly", visible_when="headline"),
        VGroup(
            Item("charge_text", label="Charge", style="readonly"),
            Item(
                "state_text", label="State", style="readonly", visible_when="state_text"
            ),
            Item("time_text", label="Time", style="readonly", visible_when="time_text"),
            Item(
                "voltage_text",
                label="Voltage",
                style="readonly",
                visible_when="voltage_text",
            ),
            Item(
                "current_text",
                label="Current",
                style="readonly",
                visible_when="current_text",
            ),
            Item(
                "power_text", label="Power", style="readonly", visible_when="power_text"
            ),
            Item("pack_text", label="Pack", style="readonly", visible_when="pack_text"),
            Item(
                "source_text",
                label="Estimate",
                style="readonly",
                visible_when="source_text",
            ),
            visible_when="not headline",
        ),
        label="Battery",
        show_border=True,
    ),
    title="Battery",
    kind="live",
    resizable=False,
    buttons=NoButtons,
    handler=BatteryDetailsHandler,
)


def show_battery_details(model, parent, details_ui=None):
    """Open the details panel for ``model`` anchored to ``parent``.

    Pass the UI a previous call returned as ``details_ui``: while that
    panel is still open it is raised and returned instead of stacking a
    second one. The panel disposes its UI when it closes.

    Returns
    -------
    UI
        The open panel's TraitsUI UI.
    """
    if details_ui is not None and details_ui.control is not None:
        details_ui.control.raise_()

        return details_ui

    return model.edit_traits(view=BatteryDetailsView, parent=parent, kind="live")
