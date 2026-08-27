# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""DockPaneAction factories for the pluggable protocol tree's
``&Protocol`` file menu (New / Load / Import Legacy / Save / Save As).

Each action targets a method on ``PluggableProtocolDockPane`` which
delegates to the hosted ``ProtocolTreePane``.
"""

from pyface.tasks.action.api import DockPaneAction, SMenu

from pluggable_protocol_tree.consts import PKG


_DOCK_PANE_ID = f"{PKG}.dock_pane"


def new_protocol_factory():
    return DockPaneAction(
        id=f"{PKG}.new_protocol",
        dock_pane_id=_DOCK_PANE_ID,
        name="&Create New",
        method="new_protocol",
    )


def new_experiment_factory():
    return DockPaneAction(
        id=f"{PKG}.create_new_experiment",
        dock_pane_id=_DOCK_PANE_ID,
        name="New &Experiment",
        method="setup_new_experiment",
    )


def load_dialog_factory():
    return DockPaneAction(
        id=f"{PKG}.load_protocol_dialog",
        dock_pane_id=_DOCK_PANE_ID,
        name="&Load",
        method="load_protocol_dialog",
    )


def import_legacy_dialog_factory():
    return DockPaneAction(
        id=f"{PKG}.import_legacy_protocol_dialog",
        dock_pane_id=_DOCK_PANE_ID,
        name="&Import Legacy Protocol...",
        method="import_legacy_protocol_dialog",
    )


def save_dialog_factory():
    return DockPaneAction(
        id=f"{PKG}.save_protocol_dialog",
        dock_pane_id=_DOCK_PANE_ID,
        name="&Save",
        method="save_protocol_dialog",
    )


def save_as_dialog_factory():
    return DockPaneAction(
        id=f"{PKG}.save_as_protocol_dialog",
        dock_pane_id=_DOCK_PANE_ID,
        name="Save &as",
        method="save_as_protocol_dialog",
    )


def protocol_menu_factory():
    return SMenu(
        new_protocol_factory(),
        load_dialog_factory(),
        import_legacy_dialog_factory(),
        save_dialog_factory(),
        save_as_dialog_factory(),
        id=f"{PKG}.protocol_menu",
        name="&Protocol",
    )
