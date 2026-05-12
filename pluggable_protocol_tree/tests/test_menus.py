"""Tests for the &Protocol menu factories.

Verifies the SMenu/DockPaneAction wiring without standing up the full
Pyface task framework.
"""

from pyface.tasks.action.api import DockPaneAction, SMenu

from pluggable_protocol_tree.consts import PKG
from pluggable_protocol_tree.menus import (
    load_dialog_factory,
    new_protocol_factory,
    protocol_menu_factory,
    save_as_dialog_factory,
    save_dialog_factory,
)


_DOCK_PANE_ID = f"{PKG}.dock_pane"


def test_protocol_menu_factory_returns_smenu_with_four_items():
    menu = protocol_menu_factory()
    assert isinstance(menu, SMenu)
    assert menu.name == "&Protocol"
    items = list(menu.items)
    assert len(items) == 4
    assert all(isinstance(item, DockPaneAction) for item in items)


def test_each_action_targets_pluggable_dock_pane():
    for factory in (new_protocol_factory, load_dialog_factory,
                    save_dialog_factory, save_as_dialog_factory):
        action = factory()
        assert action.dock_pane_id == _DOCK_PANE_ID


def test_action_method_and_name_pairs():
    expected = {
        "new_protocol": "&Create New",
        "load_protocol_dialog": "&Load",
        "save_protocol_dialog": "&Save",
        "save_as_protocol_dialog": "Save &as",
    }
    for action in protocol_menu_factory().items:
        assert action.name == expected[action.method]


def test_action_ids_are_pkg_namespaced():
    for action in protocol_menu_factory().items:
        assert action.id.startswith(f"{PKG}.")
