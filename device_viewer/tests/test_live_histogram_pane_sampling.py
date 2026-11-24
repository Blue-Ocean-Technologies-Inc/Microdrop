# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Live Histogram samples the camera only while its plot is on screen:
not behind another tab — where pyface still calls the pane visible — and
not before the plot is built on the pane's first show (#1085)."""

# Standard library imports.
import time

# Third-party imports.
import pytest

# Enthought library imports.
from pyface.qt import QtWidgets
from pyface.tasks.api import (
    DockPane,
    PaneItem,
    Tabbed,
    Task,
    TaskLayout,
    TaskPane,
    TaskWindow,
)

# Microdrop package imports.
from device_viewer.views.live_histogram.dock_pane import LiveHistogramDockPane

HISTOGRAM_ID = LiveHistogramDockPane().id

#: Long enough for a paint, a paced turn and its pause.
SETTLE_MS = 400


class OtherPane(DockPane):
    id = "test.other"

    def create_contents(self, parent):
        return QtWidgets.QLabel("other", parent)


class CentralPane(TaskPane):
    def create(self, parent):
        self.control = QtWidgets.QLabel("central", parent)


class ProbeTask(Task):
    id = "test.task"

    def create_central_pane(self):
        return CentralPane()

    def create_dock_panes(self):
        return [LiveHistogramDockPane(), OtherPane()]


def settle(ms=SETTLE_MS):
    deadline = time.perf_counter() + ms / 1000

    while time.perf_counter() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)


@pytest.fixture
def window():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    window = TaskWindow(size=(900, 600))
    window.add_task(
        ProbeTask(
            default_layout=TaskLayout(
                left=Tabbed(
                    PaneItem("test.other"),
                    PaneItem(HISTOGRAM_ID),
                    active_tab="test.other",
                )
            )
        )
    )
    window.open()
    settle()

    yield window

    window.close()


def test_behind_a_tab_it_is_neither_built_nor_sampling(window):
    histogram = window.get_dock_pane(HISTOGRAM_ID)

    assert histogram.visible
    assert not histogram.showing_contents
    assert not histogram.controller.active


def test_it_samples_while_its_tab_is_raised(window):
    histogram = window.get_dock_pane(HISTOGRAM_ID)

    histogram.control.raise_()
    settle()

    assert histogram.controller.active

    window.get_dock_pane("test.other").control.raise_()
    settle()

    assert not histogram.controller.active
