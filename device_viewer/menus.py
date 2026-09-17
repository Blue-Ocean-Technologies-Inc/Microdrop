# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Enthought library imports.
from pyface.action.api import Separator
from pyface.tasks.action.api import DockPaneAction, SGroup, SMenu

# Local imports.
from .consts import PKG


def load_svg_dialog_menu_factory():
    """Create the menu item that loads a device SVG file into the viewer."""

    return DockPaneAction(
        id=PKG + ".load_svg_file_dialog",
        dock_pane_id=PKG + ".dock_pane",
        name="&Load",
        method="load_svg_dialog",
    )


def save_svg_dialogue_menu_factory():
    """Create the menu item that saves the device back to its SVG file."""

    return DockPaneAction(
        id=PKG + ".save_svg_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name="&Save",
        method="save_svg",
    )


def save_as_svg_dialogue_menu_factory():
    """Create the menu item that saves the device to a new SVG file."""

    return DockPaneAction(
        id=PKG + ".save_as_svg_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name="Save &As",
        method="save_as_svg_dialog",
    )


def generate_svg_connections_menu_factory():
    """Create the menu item that generates the connections between
    neighbouring electrodes."""

    return DockPaneAction(
        id=PKG + ".generate_svg_connections",
        dock_pane_id=PKG + ".dock_pane",
        name="&Generate Connections",
        method="generate_svg_connections",
    )


def edit_svg_connections_menu_factory():
    """Create the menu item that opens the Edit Connections dialog, to add
    and delete connections by hand."""

    return DockPaneAction(
        id=PKG + ".edit_svg_connections",
        dock_pane_id=PKG + ".dock_pane",
        name="&Edit Connections",
        method="edit_svg_connections",
    )


def tools_menu_factory():
    return SMenu(
        SGroup(
            load_svg_dialog_menu_factory(),
            save_svg_dialogue_menu_factory(),
            save_as_svg_dialogue_menu_factory(),
        ),
        Separator(),
        generate_svg_connections_menu_factory(),
        edit_svg_connections_menu_factory(),
        id="device_svg_tools",
        name="&Device",
    )
