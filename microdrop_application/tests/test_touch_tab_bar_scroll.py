# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Touch mode's drag-to-scroll on tab bars whose tabs overflow them."""

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt.QtCore import QPoint, Qt
from pyface.qt.QtTest import QTest
from pyface.qt.QtWidgets import QApplication, QTabBar

# Microdrop package imports.
from microdrop_application.touch_mode.tab_bar_scroll import (
    TabBarDragScroller,
    overflows,
    scroll_step_px,
)


@pytest.fixture
def scroller(qapp):
    scroller = TabBarDragScroller()
    QApplication.instance().installEventFilter(scroller)

    yield scroller

    QApplication.instance().removeEventFilter(scroller)


def make_tab_bar(width, tabs=8):
    tab_bar = QTabBar()
    tab_bar.setUsesScrollButtons(True)
    tab_bar.setMovable(True)

    for number in range(tabs):
        tab_bar.addTab(f"Settings page {number}")

    tab_bar.resize(width, 40)
    tab_bar.show()
    QApplication.processEvents()

    return tab_bar


def drag(tab_bar, start, distance):
    QTest.mousePress(tab_bar, Qt.LeftButton, Qt.NoModifier, start)

    for travelled in range(0, distance, 10 if distance > 0 else -10):
        QTest.mouseMove(tab_bar, start + QPoint(travelled, 0))

    QTest.mouseRelease(
        tab_bar, Qt.LeftButton, Qt.NoModifier, start + QPoint(distance, 0)
    )


def test_drag_scrolls_the_tabs_without_selecting_or_moving_one(scroller):
    tab_bar = make_tab_bar(300)
    start = tab_bar.tabRect(1).center()

    assert overflows(tab_bar)

    drag(tab_bar, start, -2 * scroll_step_px(tab_bar) - 5)

    assert tab_bar.currentIndex() == 0
    assert tab_bar.tabText(0) == "Settings page 0"
    assert tab_bar.tabRect(0).x() < 0

    tab_bar.close()


def test_tap_still_selects_the_tab(scroller):
    tab_bar = make_tab_bar(300)

    QTest.mouseClick(tab_bar, Qt.LeftButton, Qt.NoModifier, tab_bar.tabRect(1).center())

    assert tab_bar.currentIndex() == 1

    tab_bar.close()


def test_tab_bar_that_fits_is_left_alone(scroller):
    tab_bar = make_tab_bar(3000, tabs=2)

    assert not overflows(tab_bar)

    QTest.mousePress(tab_bar, Qt.LeftButton, Qt.NoModifier, tab_bar.tabRect(1).center())

    assert tab_bar.currentIndex() == 1

    QTest.mouseRelease(
        tab_bar, Qt.LeftButton, Qt.NoModifier, tab_bar.tabRect(1).center()
    )
    tab_bar.close()
