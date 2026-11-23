# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The Updates panel loads with every frontend, whatever plugin list a
launcher saved before the panel existed."""

# Microdrop package imports.
from examples.plugin_consts import (
    BACKEND_PLUGINS,
    DROPBOT_BACKEND_PLUGINS,
    FRONTEND_PLUGINS,
    REQUIRED_PLUGINS,
    AppUpdatesPlugin,
    MicrodropPlugin,
    PluginManagementPlugin,
    with_updates_panel,
)

#: A frontend selection saved before the panel existed.
SAVED_FRONTEND = [
    *REQUIRED_PLUGINS,
    *(plugin for plugin in FRONTEND_PLUGINS if plugin is not AppUpdatesPlugin),
]


def test_a_frontend_without_the_panel_gets_it_once_after_plugin_management():
    plugins = with_updates_panel(SAVED_FRONTEND)
    position = plugins.index(PluginManagementPlugin) + 1

    assert plugins.count(AppUpdatesPlugin) == 1
    assert plugins[position] is AppUpdatesPlugin
    assert [p for p in plugins if p is not AppUpdatesPlugin] == SAVED_FRONTEND


def test_without_plugin_management_the_panel_goes_last():
    saved = [*REQUIRED_PLUGINS, MicrodropPlugin]

    assert with_updates_panel(saved) == [*saved, AppUpdatesPlugin]


def test_a_list_with_the_panel_is_unchanged():
    plugins = [*REQUIRED_PLUGINS, *FRONTEND_PLUGINS]

    assert with_updates_panel(plugins) == plugins


def test_a_backend_only_list_is_unchanged():
    plugins = [*REQUIRED_PLUGINS, *BACKEND_PLUGINS, *DROPBOT_BACKEND_PLUGINS]

    assert with_updates_panel(plugins) == plugins


def test_the_given_list_is_not_modified():
    saved = list(SAVED_FRONTEND)

    with_updates_panel(saved)

    assert saved == SAVED_FRONTEND
