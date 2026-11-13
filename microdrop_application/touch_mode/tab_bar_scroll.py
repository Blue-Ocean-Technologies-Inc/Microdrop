# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Drag along a tab bar whose tabs overflow it to scroll the tabs.

QTabBar has no public scroll offset: it scrolls one tab per click of its own
arrow buttons. A drag therefore clicks those as it travels, one click per
average tab width, so the strip follows the finger. A tab bar selects (and
starts moving) a tab on the press, so the press is held back until the
gesture is known: a drag never selects or moves a tab, and a tap is
replayed to the bar as a press and release, selecting the tab as usual.
Tab bars whose tabs all fit are left alone.
"""

# Enthought library imports.
from pyface.qt.QtCore import QEvent, QObject, Qt
from pyface.qt.QtWidgets import QApplication, QTabBar, QToolButton


def scroll_arrows(tab_bar):
    """The tab bar's (left, right) scroll buttons."""
    arrows = {
        button.arrowType(): button
        for button in tab_bar.findChildren(QToolButton)
        if button.parentWidget() is tab_bar
    }

    return arrows.get(Qt.ArrowType.LeftArrow), arrows.get(Qt.ArrowType.RightArrow)


def overflows(tab_bar):
    """Whether the tabs overflow the bar, which then shows its arrows."""
    return any(
        arrow is not None and arrow.isVisible() for arrow in scroll_arrows(tab_bar)
    )


def scroll_step_px(tab_bar):
    """Drag travel that scrolls the strip by one tab: the average tab width."""
    widths = [tab_bar.tabRect(index).width() for index in range(tab_bar.count())]

    return max(1, sum(widths) // max(1, len(widths)))


class TabBarDragScroller(QObject):
    """Application event filter turning drags along overflowing tab bars
    into scrolling; installed only while Touch mode is on."""

    def __init__(self, parent=None):
        super().__init__(parent)

        #: The tab bar a held-back press landed on, until its release.
        self._tab_bar = None

        #: A copy of that press, replayed if the gesture turns out a tap.
        self._press = None

        #: Global x where the drag last scrolled (or started).
        self._anchor_x = 0.0

        #: Whether the held-back press has turned into a drag.
        self._dragging = False

        #: Set while replaying a tap, so the replay passes through.
        self._replaying = False

    def eventFilter(self, watched, event):
        event_type = event.type()

        if self._replaying:
            return False

        if event_type == QEvent.Type.MouseButtonPress:
            return self._hold_press(watched, event)

        if self._tab_bar is None or watched is not self._tab_bar:
            return False

        if event_type == QEvent.Type.MouseMove:
            self._follow(event.globalPosition().x())

            return True

        if event_type == QEvent.Type.MouseButtonRelease:
            self._finish(event)

            return True

        return False

    def _hold_press(self, watched, event):
        is_overflowing_tab_bar = isinstance(watched, QTabBar) and overflows(watched)

        if not is_overflowing_tab_bar or event.button() != Qt.MouseButton.LeftButton:
            return False

        self._tab_bar = watched
        self._press = event.clone()
        self._anchor_x = event.globalPosition().x()
        self._dragging = False

        return True

    def _follow(self, global_x):
        """Scroll one tab for each average tab width the finger travelled;
        moving left reveals the tabs to the right, as content follows a
        finger."""
        travel = global_x - self._anchor_x

        if not self._dragging and abs(travel) < QApplication.startDragDistance():
            return

        self._dragging = True
        step = scroll_step_px(self._tab_bar)
        left, right = scroll_arrows(self._tab_bar)

        while abs(travel) >= step:
            arrow = right if travel < 0 else left

            if arrow is not None and arrow.isEnabled():
                arrow.click()

            self._anchor_x += step if travel > 0 else -step
            travel = global_x - self._anchor_x

    def _finish(self, release):
        tab_bar, press = self._tab_bar, self._press
        self._tab_bar = self._press = None

        if self._dragging:
            return

        self._replaying = True

        try:
            QApplication.sendEvent(tab_bar, press)
            QApplication.sendEvent(tab_bar, release.clone())
        finally:
            self._replaying = False
