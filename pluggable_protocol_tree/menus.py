# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""DockPaneAction factories for the pluggable protocol tree's File
submenus: ``&Experiments`` (New Experiment / Open Experiment Folder) and
``&Protocol`` (New / Load / Import Legacy / Save / Save As).

Each action targets a method on ``PluggableProtocolDockPane`` which
delegates to the hosted ``ProtocolTreePane``.
"""

# Enthought library imports.
from pyface.action.api import Action
from pyface.tasks.action.api import DockPaneAction, SGroup, SMenu
from traits.api import Str

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import warning
from microdrop_application.helpers import get_current_experiment_directory
from pluggable_protocol_tree.consts import EXPERIMENTS_MENU_ID, PKG, PROTOCOL_MENU_ID

# Microdrop utils imports.
from microdrop_utils.file_handler import open_file

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

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


class OpenExperimentFolderAction(Action):
    """Show the current experiment's folder in the system file browser."""

    name = Str("&Open Experiment Folder")

    tooltip = Str("Show the current experiment's folder in the system file browser")

    description = Str("Show the current experiment's folder in the system file browser")

    def perform(self, event):
        try:
            directory = get_current_experiment_directory()
        except Exception as e:
            logger.warning(f"Could not resolve the current experiment folder: {e}")
            warning(
                None,
                "The current experiment folder is unavailable.",
                title="Open Experiment Folder",
                cancel=False,
            )
            return

        if not directory.is_dir():
            warning(
                None,
                f"Experiment folder not found: {directory}",
                title="Open Experiment Folder",
                cancel=False,
            )
            return

        open_file(str(directory))
        logger.info(f"Opened experiment folder {directory}")


def experiments_menu_factory():
    # A group of its own keeps New Experiment above the actions other
    # plugins add; a bare action would sink into the trailing default group.
    return SMenu(
        SGroup(new_experiment_factory(), OpenExperimentFolderAction()),
        id=EXPERIMENTS_MENU_ID,
        name="&Experiments",
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
        id=PROTOCOL_MENU_ID,
        name="&Protocol",
    )
