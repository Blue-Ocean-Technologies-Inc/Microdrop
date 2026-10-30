# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The built-in plugin groups registered in BUILTIN_PLUGIN_GROUPS."""

# Third-party imports.
import pytest

# Enthought library imports.
from envisage.api import Plugin

# Microdrop package imports.
from plugin_management import group_manager
from plugin_management.consts import BUILTIN_PLUGIN_GROUPS
from plugin_management.group_manager import PluginGroup, PluginGroupManager

# Microdrop utils imports.
from microdrop_utils.system_config import is_rpi


@pytest.mark.parametrize("spec", BUILTIN_PLUGIN_GROUPS, ids=lambda s: s["name"])
def test_builtin_spec_builds_a_group_of_importable_plugins(spec):
    group = PluginGroup(**spec)

    assert group.name and group.enabled_key and group.plugin_specs

    for plugin_spec in group.plugin_specs:
        plugin_class = group_manager._resolve_plugin_class(plugin_spec)
        assert issubclass(plugin_class, Plugin), plugin_spec


def test_battery_group_is_on_by_default_only_on_the_pi():
    specs = {spec["name"]: spec for spec in BUILTIN_PLUGIN_GROUPS}

    assert specs["rpi_battery_ui"]["default_enabled"] is is_rpi()


def test_builtin_groups_register_but_never_list_as_installed(monkeypatch):
    monkeypatch.setattr(
        group_manager.entry_point_discovery,
        "discover_entry_point_manifests",
        lambda: [],
    )
    manager = PluginGroupManager()

    assert {spec["name"] for spec in BUILTIN_PLUGIN_GROUPS} <= set(manager.groups)
    assert manager.installed_plugins() == []
