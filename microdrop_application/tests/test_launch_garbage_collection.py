# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Automatic garbage collection is off from the pause until the deferred
plugins have loaded or the application stops, and never stays off."""

# Standard library imports.
import gc

# Third-party imports.
import pytest

# Enthought library imports.
from envisage.api import Application
from traits.api import Event

# Microdrop package imports.
from microdrop_application import launch_garbage_collection
from microdrop_application.launch_garbage_collection import (
    LAUNCH_GC_PAUSE_LIMIT_MS,
    LaunchGarbageCollectionPause,
)


class FakeApplication(Application):
    extra_plugins_loaded = Event()


class FakeGUI:
    """Records ``invoke_after`` calls instead of running them."""

    def __init__(self):
        self.after = []

    def invoke_after(self, millisecs, callable, *args):
        self.after.append((millisecs, callable))


@pytest.fixture
def gui(monkeypatch):
    fake = FakeGUI()
    monkeypatch.setattr(launch_garbage_collection, "GUI", fake)

    yield fake

    gc.unfreeze()
    gc.enable()


@pytest.mark.parametrize("event", ["extra_plugins_loaded", "stopped"])
def test_collection_is_off_until_the_launch_is_over(tmp_path, gui, event):
    application = FakeApplication(home=str(tmp_path))
    launch_pause = LaunchGarbageCollectionPause(application=application)

    launch_pause.pause()

    assert not gc.isenabled()
    assert [millisecs for millisecs, _ in gui.after] == [LAUNCH_GC_PAUSE_LIMIT_MS]

    # Fired with None: ``stopped`` takes an ApplicationEvent or None.
    setattr(application, event, None)

    assert gc.isenabled()
    assert gc.get_freeze_count() > 0
    assert not launch_pause.paused


def test_the_time_limit_turns_collection_back_on(tmp_path, gui):
    launch_pause = LaunchGarbageCollectionPause(
        application=FakeApplication(home=str(tmp_path))
    )

    launch_pause.pause()
    _, resume = gui.after[0]
    resume()

    assert gc.isenabled()

    # Resuming twice is harmless.
    resume()

    assert gc.isenabled()


def test_a_collector_already_off_is_left_to_its_owner(tmp_path, gui):
    gc.disable()
    launch_pause = LaunchGarbageCollectionPause(
        application=FakeApplication(home=str(tmp_path))
    )

    launch_pause.pause()
    launch_pause.resume()

    assert not gc.isenabled()
    assert gui.after == []
