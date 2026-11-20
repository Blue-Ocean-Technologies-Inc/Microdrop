# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The launch check's start and gate: it starts once, never raises into
startup, and touches git only on a managed checkout without the skip
variable. The plugin runs without an application; its preferences are in
memory."""

# Standard library imports.
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences import package_globals
from apptools.preferences.api import Preferences
from envisage.ui.tasks.api import TasksApplication

# Microdrop utils imports.
from microdrop_utils.source_version import DEVELOPMENT, MANAGED, NO_GIT

# Local imports.
from .. import plugin as plugin_module
from ..consts import POLICY_LATEST, POLICY_STAY
from ..plugin import AppUpdatesPlugin


@pytest.fixture
def plugin(monkeypatch):
    """The plugin of an application whose preferences are in memory.

    The preferences come through the application: Envisage's
    ``Plugin._anytrait_changed`` reads a trait's old value on every set, so
    setting ``preferences`` directly resolves its default without one."""
    # An envisage application installs its preferences as the process-wide
    # default node; restore it so later PreferencesHelper tests don't share it.
    monkeypatch.setattr(package_globals, "_default_preferences", None)

    return AppUpdatesPlugin(application=TasksApplication(preferences=Preferences()))


@pytest.fixture
def started_checks(monkeypatch):
    """Replace the plugin's threads with ones that record the arguments of
    each started check instead of running it."""
    started = []

    class RecordingThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            started.append(self.kwargs["args"])

    monkeypatch.setattr(
        plugin_module, "threading", SimpleNamespace(Thread=RecordingThread)
    )

    return started


@pytest.fixture
def fetches(monkeypatch):
    """Record every fetch, and leave no release tags to decide on."""
    fetched = []

    monkeypatch.setattr(plugin_module, "fetch_tags", fetched.append)
    monkeypatch.setattr(plugin_module, "list_release_tags", lambda root: [])
    monkeypatch.setattr(plugin_module, "current_release", lambda root: None)

    return fetched


def _checkout(monkeypatch, state, skip_variable_set):
    monkeypatch.setattr(plugin_module, "checkout_state", lambda root: (state, "why"))
    monkeypatch.setattr(
        plugin_module, "skip_variable_is_set", lambda: skip_variable_set
    )


# --- start -------------------------------------------------------------------


def test_the_check_starts_once_with_the_saved_preferences(plugin, started_checks):
    plugin.preferences.auto_update = False
    plugin.preferences.last_announced_version = "v1.46.0"

    plugin._check_for_updates_on_launch(None)
    plugin._check_for_updates_on_launch(None)

    assert started_checks == [(POLICY_STAY, "v1.46.0")]


def test_a_thread_that_cannot_start_does_not_raise(plugin, monkeypatch):
    class UnstartableThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(
        plugin_module, "threading", SimpleNamespace(Thread=UnstartableThread)
    )

    plugin._check_for_updates_on_launch(None)

    assert plugin._launch_check_started


# --- gate --------------------------------------------------------------------


@pytest.mark.parametrize("state", [DEVELOPMENT, NO_GIT])
def test_an_unmanaged_checkout_is_not_fetched(plugin, monkeypatch, fetches, state):
    _checkout(monkeypatch, state, skip_variable_set=False)

    plugin._run_launch_check(POLICY_LATEST, "")

    assert fetches == []


def test_a_checkout_with_the_skip_variable_set_is_not_fetched(
    plugin, monkeypatch, fetches
):
    _checkout(monkeypatch, MANAGED, skip_variable_set=True)

    plugin._run_launch_check(POLICY_LATEST, "")

    assert fetches == []


def test_a_managed_checkout_is_fetched(plugin, monkeypatch, fetches):
    _checkout(monkeypatch, MANAGED, skip_variable_set=False)

    plugin._run_launch_check(POLICY_LATEST, "")

    assert len(fetches) == 1
