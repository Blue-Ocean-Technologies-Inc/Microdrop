# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The launch check's start, gate and failed fetch: it starts once, never
raises into startup, touches git only on a managed checkout without the skip
variable, and still decides when the fetch fails. The plugin belongs to a
TasksApplication that is built but never started; the application's own
preferences are in memory, the update settings in a temporary file."""

# Standard library imports.
import logging
from types import SimpleNamespace

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences import package_globals
from apptools.preferences.api import Preferences
from envisage.ui.tasks.api import TasksApplication

# Microdrop utils imports.
from microdrop_utils.source_update_startup import (
    AUTO_UPDATE_PREFERENCE_PATH,
    LAST_ANNOUNCED_PREFERENCE_PATH,
)
from microdrop_utils.source_version import (
    DEVELOPMENT,
    HAS_PANEL,
    MANAGED,
    NO_GIT,
    ReleaseTag,
    SourceVersionError,
)

# Local imports.
from .. import plugin as plugin_module
from ..consts import POLICY_LATEST, POLICY_STAY
from ..plugin import AppUpdatesPlugin


@pytest.fixture
def plugin(monkeypatch):
    """The plugin of an application whose own preferences are in memory; the
    update settings are in the conftest's temporary file."""
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


def test_the_check_starts_once_with_the_saved_preferences(
    plugin, started_checks, preferences
):
    preferences.set(AUTO_UPDATE_PREFERENCE_PATH, "False")
    preferences.set(LAST_ANNOUNCED_PREFERENCE_PATH, "v1.46.0")
    preferences.flush()

    plugin._check_for_updates_on_launch(None)
    plugin._check_for_updates_on_launch(None)

    assert started_checks == [(POLICY_STAY, "v1.46.0")]


def test_an_announced_release_is_saved_in_the_updates_file(
    plugin, preferences, monkeypatch
):
    questions = []

    monkeypatch.setattr(
        plugin_module, "confirm", lambda *args, **kwargs: questions.append(args)
    )

    plugin._remember_and_offer_release("v1.47.0")

    saved = Preferences(filename=preferences.filename)

    assert len(questions) == 1
    assert saved.get(LAST_ANNOUNCED_PREFERENCE_PATH) == "v1.47.0"
    # Never the application's preferences, which every process saves at exit.
    assert plugin.application.preferences.get(LAST_ANNOUNCED_PREFERENCE_PATH) is None


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


# --- a failed fetch ------------------------------------------------------------


@pytest.fixture
def offline_with_a_new_release(monkeypatch):
    """A managed checkout on v1.46.0 whose fetch fails, with v1.47.0 already
    present locally; return the calls handed to the GUI thread."""
    invoked = []

    def fail_fetch(repo_root):
        raise SourceVersionError(
            "`git fetch` exited with code 128", "fatal: unable to access origin"
        )

    _checkout(monkeypatch, MANAGED, skip_variable_set=False)
    monkeypatch.setattr(plugin_module, "fetch_tags", fail_fetch)
    monkeypatch.setattr(
        plugin_module,
        "list_release_tags",
        lambda root: [ReleaseTag("v1.47.0", (1, 47, 0), "2026-11-20", HAS_PANEL)],
    )
    monkeypatch.setattr(plugin_module, "current_release", lambda root: "v1.46.0")
    monkeypatch.setattr(
        plugin_module,
        "GUI",
        SimpleNamespace(invoke_later=lambda *args: invoked.append(args)),
    )

    return invoked


def test_a_failed_fetch_is_a_warning_and_the_check_still_logs(
    plugin, offline_with_a_new_release, caplog
):
    with caplog.at_level(logging.INFO, logger=plugin_module.__name__):
        plugin._run_launch_check(POLICY_LATEST, "")

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]

    assert len(warnings) == 1
    assert "fatal: unable to access origin" in warnings[0].getMessage()
    assert "MicroDrop v1.47.0 downloaded" in caplog.text


def test_a_failed_fetch_still_announces_a_local_release(
    plugin, offline_with_a_new_release
):
    plugin._run_launch_check(POLICY_STAY, "")

    assert offline_with_a_new_release == [(plugin._announce_release, "v1.47.0")]
