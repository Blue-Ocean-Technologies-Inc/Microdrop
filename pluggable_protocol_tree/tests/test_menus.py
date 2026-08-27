# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tests for the &Protocol menu factories.

Verifies the SMenu/DockPaneAction wiring without standing up the full
Pyface task framework.
"""

from pyface.tasks.action.api import DockPaneAction, SMenu

from pluggable_protocol_tree.consts import PKG
from pluggable_protocol_tree.menus import (
    import_legacy_dialog_factory,
    load_dialog_factory,
    new_protocol_factory,
    protocol_menu_factory,
    save_as_dialog_factory,
    save_dialog_factory,
)


_DOCK_PANE_ID = f"{PKG}.dock_pane"


def test_protocol_menu_factory_returns_smenu_with_five_items():
    menu = protocol_menu_factory()
    assert isinstance(menu, SMenu)
    assert menu.name == "&Protocol"
    items = list(menu.items)
    assert len(items) == 5
    assert all(isinstance(item, DockPaneAction) for item in items)


def test_each_action_targets_pluggable_dock_pane():
    for factory in (new_protocol_factory, load_dialog_factory,
                    import_legacy_dialog_factory, save_dialog_factory,
                    save_as_dialog_factory):
        action = factory()
        assert action.dock_pane_id == _DOCK_PANE_ID


def test_action_method_and_name_pairs():
    expected = {
        "new_protocol": "&Create New",
        "load_protocol_dialog": "&Load",
        "import_legacy_protocol_dialog": "&Import Legacy Protocol...",
        "save_protocol_dialog": "&Save",
        "save_as_protocol_dialog": "Save &as",
    }
    for action in protocol_menu_factory().items:
        assert action.name == expected[action.method]


def test_action_ids_are_pkg_namespaced():
    for action in protocol_menu_factory().items:
        assert action.id.startswith(f"{PKG}.")
