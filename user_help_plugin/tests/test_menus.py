# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Unit tests for the Help menu and its Tutorials extension point."""

# Standard library imports.
from pathlib import Path

# Third-party imports.
import pytest

# Enthought library imports.
from apptools.preferences import package_globals
from envisage.api import Application, Plugin
from traits.api import List

# Local imports.
from ..consts import TUTORIALS, TutorialEntry
from ..menus import (
    OpenWebViewDialogAction,
    TutorialCatalog,
    TutorialsMenuManager,
    menu_factory,
)
from ..plugin import UserHelpPlugin

PAGE = Path(__file__).resolve()


class TutorialContributingPlugin(Plugin):
    id = "test.tutorial_contributor"

    tutorials = List(contributes_to=TUTORIALS)

    def _tutorials_default(self):
        return [
            TutorialEntry(title="Zebra Tutorial", path=PAGE),
            TutorialEntry(title="Heater & Magnet Tutorial", path=PAGE),
        ]


def _tutorial_titles(menu):
    return [
        item.action.window_title
        for group in menu.groups
        for item in group.items
        if isinstance(item.action, OpenWebViewDialogAction)
    ]


@pytest.fixture
def help_plugin(monkeypatch):
    """A started Help plugin in an otherwise empty application."""
    # An envisage Application installs its preferences as the process-wide
    # default node; restore it so later PreferencesHelper tests don't share it.
    monkeypatch.setattr(package_globals, "_default_preferences", None)

    plugin = UserHelpPlugin()
    application = Application(plugins=[plugin])
    application.start()

    yield plugin

    application.stop()


def test_help_group_holds_the_tutorials_submenu():
    catalog = TutorialCatalog(entries=[TutorialEntry(title="A", path=PAGE)])
    submenus = [
        item
        for item in menu_factory(tutorial_catalog=catalog).items
        if isinstance(item, TutorialsMenuManager)
    ]

    assert len(submenus) == 1
    assert submenus[0].name == "&Tutorials"
    assert _tutorial_titles(submenus[0]) == ["A"]


def test_submenu_follows_the_catalog():
    catalog = TutorialCatalog()
    menu = TutorialsMenuManager(catalog=catalog)

    assert _tutorial_titles(menu) == []
    assert not menu.enabled

    catalog.entries = [TutorialEntry(title="Heater & Magnet Tutorial", path=PAGE)]
    action = menu.groups[0].items[0].action

    assert menu.enabled
    assert action.name == "Heater && Magnet Tutorial..."
    assert action.source == PAGE


def test_a_plugin_loaded_at_runtime_adds_its_tutorials(help_plugin):
    contributor = TutorialContributingPlugin()
    menu = TutorialsMenuManager(catalog=help_plugin.tutorial_catalog)

    help_plugin.application.add_plugin(contributor)

    assert _tutorial_titles(menu) == ["Heater & Magnet Tutorial", "Zebra Tutorial"]

    help_plugin.application.remove_plugin(contributor)

    assert _tutorial_titles(menu) == []
