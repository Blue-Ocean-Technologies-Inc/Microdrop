from pyface.tasks.action.api import DockPaneAction, SMenu
from .consts import PKG


def load_dialog_menu_factory():
    """
    Create a menu item that makes the viewer generate the electrode view from an SVG file
    """

    return DockPaneAction(
        id=PKG + ".load_protocol_dialog",
        dock_pane_id=PKG + ".dock_pane",
        name="Load",
        method="load_protocol_dialog",
    )


def save_dialogue_menu_factory():
    """
    Create a menu item to save current protocol in place
    """

    return DockPaneAction(
        id=PKG + ".save_as_protocol_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name="Save As",
        method="save_protocol_dialog",
    )


def save_as_dialogue_menu_factory():
    """
    Create a menu item to save current protocol as another file.
    """

    return DockPaneAction(
        id=PKG + ".save_as_protocol_dialogue",
        dock_pane_id=PKG + ".dock_pane",
        name="Save as",
        method="save_as_protocol_dialog",
    )

def new_experiment_factory():
    """
    Increment experiment ID with new timestamp, and create new exp directory.
    """

    return DockPaneAction(
        id=PKG + ".create_new_experiment",
        dock_pane_id=PKG + ".dock_pane",
        name="New Experiment",
        method="setup_new_experiment",
    )


def tools_menu_factory():
    return SMenu(

        load_dialog_menu_factory(),
        save_as_dialogue_menu_factory(),

        id="protocol_tools", name="Protocol"

    )