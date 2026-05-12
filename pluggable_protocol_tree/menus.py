"""DockPaneAction factories for the pluggable protocol tree's
``&Protocol`` file menu (New / Load / Save / Save As).

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


def load_dialog_factory():
    return DockPaneAction(
        id=f"{PKG}.load_protocol_dialog",
        dock_pane_id=_DOCK_PANE_ID,
        name="&Load",
        method="load_protocol_dialog",
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
        save_dialog_factory(),
        save_as_dialog_factory(),
        id=f"{PKG}.protocol_menu",
        name="&Protocol",
    )
