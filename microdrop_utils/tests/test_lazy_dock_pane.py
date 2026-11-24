# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""A lazy dock pane builds its contents once it is on screen — shown at
launch, its tab raised, opened from the View menu, floated, swapped in
for a placeholder that was shown — and not while it sits behind a tab, is
hidden, or a window layout is applied around it. The layout saves and
restores with panes never built."""

# Standard library imports.
import pickle
import time
from unittest.mock import patch

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
from traits.api import HasTraits, Instance, Int, Str

# Microdrop utils imports.
from microdrop_utils.deferred_content import CONTENT_BUILT, CONTENT_FAILED
from microdrop_utils.lazy_dock_pane import LazyContentDockPane
from microdrop_utils.plugin_load_status import LOAD_FAILED, PluginLoadStatus
from microdrop_utils.tasks_runtime_helpers import add_dock_pane_live

#: Long enough for a paint, a paced turn and its pause.
SETTLE_MS = 400


class LazyPane(LazyContentDockPane, DockPane):
    #: How many times the contents were built.
    builds = Int(0)

    def create_contents(self, parent):
        self.builds += 1

        return QtWidgets.QLabel(f"contents of {self.id}", parent)


class BrokenPane(LazyPane):
    def create_contents(self, parent):
        raise RuntimeError("no contents")


class LabelPane(DockPane):
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
            LazyPane(id=pane_id, name=pane_id) for pane_id in ("a", "b", "c", "hidden")
        ] + [BrokenPane(id="broken", name="Broken"), LabelPane(id="ph", name="ph")]


class FakeApplication(HasTraits):
    plugin_load_status = Instance(PluginLoadStatus, ())


LAYOUT = TaskLayout(
    left=Tabbed(PaneItem("a"), PaneItem("b"), active_tab="a"),
    right=VSplitter(PaneItem("c"), PaneItem("ph")),
)


def settle(ms=SETTLE_MS):
    deadline = time.perf_counter() + ms / 1000

    while time.perf_counter() < deadline:
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)


@pytest.fixture
def window():
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    window = TaskWindow(size=(900, 600))
    window.application = FakeApplication()
    window.add_task(ProbeTask(default_layout=LAYOUT.clone_traits()))
    window.open()
    settle()

    yield window

    window.close()


def pane(window, pane_id):
    return window.get_dock_pane(pane_id)


def built(window, pane_id):
    return pane(window, pane_id).deferred_contents.state == CONTENT_BUILT


def shown_text(dock_pane):
    """The text of what the pane's dock shows: its status line or label."""
    return dock_pane.control.widget().currentWidget().text()


def test_panes_shown_at_launch_build_and_the_others_do_not(window):
    assert built(window, "a") and built(window, "c")
    assert not built(window, "b")
    assert not built(window, "hidden")
    assert shown_text(pane(window, "b")) == "Loading b…"

    # Qt (and so pyface) calls a tab behind another visible.
    assert pane(window, "b").control.isVisible()


def test_each_pane_builds_once(window):
    pane(window, "b").control.raise_()
    settle()
    pane(window, "a").control.raise_()
    settle()
    pane(window, "b").control.raise_()
    settle()

    assert [pane(window, pane_id).builds for pane_id in "abc"] == [1, 1, 1]


def test_raising_a_tab_builds_it(window):
    pane(window, "b").control.raise_()
    settle()

    assert built(window, "b")
    assert shown_text(pane(window, "b")) == "contents of b"


def test_opening_a_hidden_pane_builds_it(window):
    pane(window, "hidden").visible = True
    settle()

    assert built(window, "hidden")


def test_opening_a_floating_pane_builds_it(window):
    hidden = pane(window, "hidden")
    hidden.floating = True
    hidden.visible = True
    settle()

    assert built(window, "hidden")
    assert hidden.showing_contents


def test_applying_a_layout_does_not_build_a_tab_it_leaves_behind(window):
    window.set_layout(LAYOUT.clone_traits())
    settle()

    assert not built(window, "b")


def test_a_layout_that_shows_a_pane_builds_it(window):
    window.set_layout(
        TaskLayout(
            left=Tabbed(PaneItem("a"), PaneItem("b"), active_tab="a"),
            right=VSplitter(PaneItem("c"), PaneItem("hidden")),
        )
    )
    settle()

    assert built(window, "hidden")
    assert not built(window, "b")


def _shape(item):
    """A layout item's arrangement of pane ids, without sizes."""
    if item is None or isinstance(item, PaneItem):
        return getattr(item, "id", None)

    active_tab = getattr(item, "active_tab", None)

    return type(item).__name__, active_tab, [_shape(sub) for sub in item.items]


def test_the_layout_saves_and_restores_with_panes_never_built(window):
    # As at exit: the layout pickled with tab "b" never built.
    saved = pickle.loads(pickle.dumps(window.get_layout()))

    assert not built(window, "b")
    assert _shape(saved.left) == ("Tabbed", "a", ["a", "b"])

    # As at the next launch: a window laid out from the saved layout.
    restarted = TaskWindow(size=(900, 600))
    restarted.add_task(ProbeTask(default_layout=saved))
    restarted.open()
    settle()

    try:
        restored = restarted.get_layout()

        assert _shape(restored.left) == _shape(saved.left)
        assert _shape(restored.right) == _shape(saved.right)
        assert not built(restarted, "b")

    finally:
        restarted.close()


def test_a_lazy_pane_swapped_in_behind_a_tab_waits_until_shown(window):
    task = window.active_task
    window.set_layout(
        TaskLayout(left=Tabbed(PaneItem("a"), PaneItem("ph"), active_tab="a"))
    )
    settle()

    swapped = add_dock_pane_live(window, task, lambda **t: LazyPane(id="ph", **t))
    settle()

    assert swapped.builds == 0

    swapped.control.raise_()
    settle()

    assert swapped.builds == 1


def test_a_lazy_pane_swapped_in_where_shown_builds(window):
    task = window.active_task

    swapped = add_dock_pane_live(window, task, lambda **t: LazyPane(id="ph", **t))
    settle()

    assert swapped.builds == 1


def test_showing_contents_follows_the_tab_not_pyface_visible(window):
    a, b = pane(window, "a"), pane(window, "b")

    assert a.showing_contents and not b.showing_contents

    b.control.raise_()
    settle()

    assert b.showing_contents and not a.showing_contents
    assert a.visible


def test_ensure_built_builds_a_hidden_pane_and_callbacks_follow(window):
    hidden = pane(window, "hidden")
    received = []
    hidden.when_content_built(received.append)

    hidden.ensure_built()

    assert hidden.builds == 1
    assert received[0].text() == "contents of hidden"
    assert not hidden.control.isVisible()


def test_a_failed_build_says_why_and_is_recorded_under_the_pane_id(window):
    broken = pane(window, "broken")

    with patch("microdrop_utils.deferred_content.logger"):
        broken.ensure_built()

    record = window.application.plugin_load_status.get_record("broken")

    assert broken.deferred_contents.state == CONTENT_FAILED
    assert shown_text(broken).startswith("Broken could not be loaded: no contents")
    assert record.state == LOAD_FAILED
    assert record.name == "Broken pane"
    assert "RuntimeError: no contents" in record.traceback


def test_a_pane_destroyed_before_its_build_never_builds(window):
    b = pane(window, "b")
    b.control.raise_()
    b.destroy()
    settle()

    assert b.builds == 0
