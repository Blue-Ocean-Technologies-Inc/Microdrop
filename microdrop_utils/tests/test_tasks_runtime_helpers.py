# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A pane mounted live under an id already in the window replaces that pane
in place: same tab group, current tab, size and visibility, and pyface's
own pane list points at the new pane."""

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
    VSplitter,
)
from traits.api import Str

# Microdrop utils imports.
from microdrop_utils.tasks_runtime_helpers import add_dock_pane_live


class LabelPane(DockPane):
    #: What the pane shows, to tell the placeholder from the real pane.
    label = Str()

    def create_contents(self, parent):
        return QtWidgets.QLabel(self.label, parent)


class CentralPane(TaskPane):
    def create(self, parent):
        self.control = QtWidgets.QLabel("central", parent)


class ProbeTask(Task):
    id = "test.task"

    def create_central_pane(self):
        return CentralPane()

    def create_dock_panes(self):
        return [
            LabelPane(id=pane_id, name=pane_id, label=f"placeholder {pane_id}")
            for pane_id in ("a", "b", "c", "hidden")
        ]


@pytest.fixture
def window():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    task = ProbeTask(
        default_layout=TaskLayout(
            left=Tabbed(PaneItem("a"), PaneItem("b"), active_tab="a"),
            right=VSplitter(PaneItem("c")),
        )
    )
    window = TaskWindow(size=(900, 600))
    window.add_task(task)
    window.open()
    QtWidgets.QApplication.processEvents()

    yield window

    window.close()


def _placement(window, pane_id):
    main_window = window.control
    dock_widget = window.get_dock_pane(pane_id).control
    shown = not dock_widget.visibleRegion().isEmpty()

    return {
        "area": main_window.dockWidgetArea(dock_widget),
        # A tab behind another keeps whatever size its contents asked for.
        "geometry": dock_widget.geometry() if shown else None,
        "visible": dock_widget.isVisible(),
        "tabbed_with": [
            widget.objectName()
            for widget in main_window.tabifiedDockWidgets(dock_widget)
        ],
        "current_tab": shown,
    }


@pytest.mark.parametrize("pane_id", ["a", "b", "c", "hidden"])
def test_a_same_id_pane_takes_the_placeholders_place(window, pane_id):
    task = window.active_task
    before = _placement(window, pane_id)
    placeholder = window.get_dock_pane(pane_id)

    def real_pane(**traits):
        return LabelPane(id=pane_id, name=pane_id, label=f"real {pane_id}", **traits)

    pane = add_dock_pane_live(window, task, real_pane)
    QtWidgets.QApplication.processEvents()

    assert _placement(window, pane_id) == before
    assert window.get_dock_pane(pane_id) is pane
    assert pane.control.widget().text() == f"real {pane_id}"
    assert placeholder.control is None
    assert [p.id for p in window.dock_panes] == ["a", "b", "c", "hidden"]
