# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Managed plugin groups stay out of the static startup plugin lists.

The plugin-group manager loads a managed group at launch; listing one of its
plugins statically as well double-loads it (duplicate service offers and
panes) and leaves its Manage Plugins checkbox unable to keep it off.

plugin_consts is read as source rather than imported: importing it pulls in
every plugin, and doing so after PySide6 is loaded trips a pydantic circular
import, which would make this test depend on collection order.
"""

# Standard library imports.
import ast
from pathlib import Path

# Microdrop package imports.
from plugin_management.consts import BUILTIN_PLUGIN_GROUPS

PLUGIN_CONSTS_PATH = Path(__file__).parents[1] / "plugin_consts.py"


def _static_plugin_list_names():
    """Every name listed in a module-level list literal of plugin_consts."""
    tree = ast.parse(PLUGIN_CONSTS_PATH.read_text(encoding="utf-8"))
    names = set()

    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            names.update(
                item.id for item in node.value.elts if isinstance(item, ast.Name)
            )

    return names


def test_battery_plugin_is_in_no_static_list():
    assert "RpiBatteryStatusPlugin" not in _static_plugin_list_names()


def test_no_builtin_group_plugin_is_in_a_static_list():
    builtin_class_names = {
        plugin_spec.partition(":")[2]
        for spec in BUILTIN_PLUGIN_GROUPS
        for plugin_spec in spec["plugin_specs"]
    }

    assert not _static_plugin_list_names() & builtin_class_names
