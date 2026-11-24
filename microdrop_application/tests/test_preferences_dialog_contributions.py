# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Preferences dialog is a cached service, yet each open shows the panes
of the plugins loaded at that moment (#1062)."""

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences import package_globals
from apptools.preferences.api import PreferencesHelper
from envisage.api import (
    PREFERENCES_CATEGORIES,
    PREFERENCES_PANES,
    CorePlugin,
    Plugin,
)
from envisage.ui.tasks.api import (
    PreferencesCategory,
    PreferencesPane,
    TasksApplication,
)
from envisage.ui.tasks.preferences_dialog import (
    PreferencesDialog as EnvisagePreferencesDialog,
)
from envisage.ui.tasks.tasks_plugin import TasksPlugin
from traits.api import HasTraits, Instance, List, Str
from traitsui.api import Item, View

# Local imports.
from ..plugin import MicrodropPlugin
from ..preferences_dialog import PreferencesDialog

LATE_TAB_NAME = "Late Plugin"


class _TasksApplication(TasksApplication):
    #: MicrodropPlugin observes this; None leaves Touch mode off.
    touch_mode_controller = Instance(HasTraits)


class _LatePreferences(PreferencesHelper):
    preferences_path = "test.late"

    note = Str()


class _LatePreferencesPane(PreferencesPane):
    id = "test.late.pane"
    category = "test.late"
    model_factory = _LatePreferences
    view = View(Item("note"))


class LatePreferencesPlugin(Plugin):
    """A plugin loaded after the dialog was first opened."""

    id = "test.late_preferences"

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    def _preferences_panes_default(self):
        return [_LatePreferencesPane]

    def _preferences_categories_default(self):
        return [PreferencesCategory(id="test.late", name=LATE_TAB_NAME)]


@pytest.fixture
def application(monkeypatch, tmp_path, qapp):
    """A started app with the Microdrop and Tasks preferences dialog offers,
    Microdrop's first, as in the run scripts."""
    # An envisage Application installs its preferences as the process-wide
    # default node; restore it so later PreferencesHelper tests don't share it.
    monkeypatch.setattr(package_globals, "_default_preferences", None)

    application = _TasksApplication(
        home=str(tmp_path),
        plugins=[CorePlugin(), MicrodropPlugin(), TasksPlugin()],
    )
    application.start()

    yield application

    application.stop()


def _open_and_close(dialog):
    """Open the dialog as the Preferences action does (non-modal here), and
    return its tab names."""
    ui = dialog.edit_traits(kind="live")
    names = [tab.name for tab in dialog._tabs]
    ui.dispose()

    return names


def test_the_microdrop_dialog_wins_the_service_lookup(application):
    dialog = application.get_service(EnvisagePreferencesDialog)

    assert isinstance(dialog, PreferencesDialog)
    assert application.get_service(EnvisagePreferencesDialog) is dialog


def test_panes_of_a_plugin_loaded_after_the_first_open_appear(application):
    dialog = application.get_service(EnvisagePreferencesDialog)

    assert LATE_TAB_NAME not in _open_and_close(dialog)

    application.add_plugin(LatePreferencesPlugin())

    assert LATE_TAB_NAME in _open_and_close(dialog)


def test_a_plugin_loaded_while_the_dialog_is_open_waits_for_the_next_open(
    application,
):
    dialog = application.get_service(EnvisagePreferencesDialog)
    ui = dialog.edit_traits(kind="live")
    tabs = list(dialog._tabs)

    application.add_plugin(LatePreferencesPlugin())

    assert dialog._tabs == tabs

    ui.dispose()

    assert LATE_TAB_NAME in _open_and_close(dialog)


def test_panes_of_a_removed_plugin_are_gone(application):
    late_plugin = LatePreferencesPlugin()
    application.add_plugin(late_plugin)
    dialog = application.get_service(EnvisagePreferencesDialog)

    assert LATE_TAB_NAME in _open_and_close(dialog)

    application.remove_plugin(late_plugin)

    assert LATE_TAB_NAME not in _open_and_close(dialog)


def test_unchanged_contributions_keep_their_panes(application):
    dialog = application.get_service(EnvisagePreferencesDialog)
    _open_and_close(dialog)
    panes = list(dialog.panes)

    _open_and_close(dialog)

    assert dialog.panes == panes
