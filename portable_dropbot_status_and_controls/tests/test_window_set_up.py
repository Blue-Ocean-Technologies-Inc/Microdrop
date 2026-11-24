# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The kiosk set-up (fullscreen, touch flick scrolling) runs once, whether the
plugin starts with the launch or after the window is already open, and panes
mounted after it flick-scroll too (#1062)."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences import package_globals
from envisage.ui.tasks.api import TasksApplication, TaskWindow
from pyface.tasks.api import DockPane

# Microdrop package imports.
from portable_dropbot_status_and_controls.plugin import (
    PortableDropbotStatusAndControlsPlugin,
)


@pytest.fixture
def qapp():
    from pyface.qt.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def set_ups(monkeypatch):
    """The windows each set-up step ran on, in order."""
    calls = []

    monkeypatch.setattr(
        PortableDropbotStatusAndControlsPlugin,
        "_go_fullscreen_on_rpi",
        staticmethod(lambda window: calls.append(("fullscreen", window))),
    )
    monkeypatch.setattr(
        PortableDropbotStatusAndControlsPlugin,
        "_enable_touch_flick_scrolling_on_rpi",
        staticmethod(lambda window: calls.append(("flick scrolling", window))),
    )

    return calls


@pytest.fixture
def application(monkeypatch, tmp_path, qapp):
    # An envisage Application installs its preferences as the process-wide
    # default node; restore it so later PreferencesHelper tests don't share it.
    monkeypatch.setattr(package_globals, "_default_preferences", None)

    return TasksApplication(home=str(tmp_path))


def _started_plugin(application):
    plugin = PortableDropbotStatusAndControlsPlugin()
    application.add_plugin(plugin)
    plugin.start()

    return plugin


def test_launch_start_sets_up_the_window_once_it_is_initialized(application, set_ups):
    plugin = _started_plugin(application)
    window = TaskWindow()

    assert set_ups == []

    application.windows.append(window)
    application.active_window = window
    application.application_initialized = application

    assert set_ups == [("fullscreen", window), ("flick scrolling", window)]

    plugin.stop()


def test_late_start_sets_up_the_open_window_once(application, set_ups):
    window = TaskWindow()
    application.windows.append(window)
    application.active_window = window

    plugin = _started_plugin(application)

    assert set_ups == [("fullscreen", window), ("flick scrolling", window)]

    # A later initialized event, or window switch, does not repeat it.
    application.application_initialized = application
    application.active_window = TaskWindow()

    assert set_ups == [("fullscreen", window), ("flick scrolling", window)]

    plugin.stop()


def test_panes_mounted_after_the_set_up_get_flick_scrolling(application, set_ups):
    window = TaskWindow()
    application.windows.append(window)
    application.active_window = window
    plugin = _started_plugin(application)

    window.dock_panes.append(DockPane(id="test.deferred_pane"))

    assert set_ups == [
        ("fullscreen", window),
        ("flick scrolling", window),
        ("flick scrolling", window),
    ]

    plugin.stop()


def test_panes_mounted_before_the_set_up_wait_for_it(application, set_ups):
    plugin = _started_plugin(application)
    window = TaskWindow()
    application.windows.append(window)
    application.active_window = window

    window.dock_panes.append(DockPane(id="test.launch_pane"))

    assert set_ups == []

    plugin.stop()
