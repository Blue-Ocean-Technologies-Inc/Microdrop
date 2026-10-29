# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""View-menu actions to save the window layout as a named preset and to
re-apply a saved one from the Layout Presets submenu."""

# Standard library imports.
import pickle
import re

# Enthought library imports.
from pyface.action.api import Action, Group
from pyface.api import NO, YES
from pyface.qt import QtGui
from pyface.tasks.action.api import SGroup, SMenu, TaskAction
from traits.api import Instance, Str, observe

# Microdrop package imports.
from device_viewer.consts import KEYBOARD_SHORTCUTS
from microdrop_application.dialogs.pyface_wrapper import confirm, error, warning

# Microdrop utils imports.
from microdrop_utils.tasks_runtime_helpers import describe_dock_widgets

# Local imports.
from .consts import (
    APPLY_LAYOUT_PRESET_DIALOG_TITLE,
    DEVICE_VIEW_SHORTCUT_OWNER,
    LAYOUT_PRESETS_GROUP_ID,
    LAYOUT_PRESETS_ITEMS_GROUP_ID,
    LAYOUT_PRESETS_MENU_ID,
    LAYOUT_PRESETS_MENU_NAME,
    MANAGE_LAYOUT_PRESETS_ACTION_ID,
    MANAGE_LAYOUT_PRESETS_ACTION_NAME,
    MANAGE_LAYOUT_PRESETS_DIALOG_TITLE,
    NO_LAYOUT_PRESETS_LABEL,
    SAVE_LAYOUT_PRESET_ACTION_ID,
    SAVE_LAYOUT_PRESET_ACTION_NAME,
    SAVE_LAYOUT_PRESET_DIALOG_TITLE,
    UNNAMED_SHORTCUT_OWNER,
)
from .models.preset_name_model import PresetName, preset_shortcut_owner
from .models.preset_store import PresetStore
from .models.preset_table_model import PresetTable
from .views.preset_name_view import preset_name_view
from .views.preset_table_view import preset_table_view

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _event_window(action, event):
    """Return the task window an action was triggered from, or None."""
    # The menu-bar rebuild on plugin hot-load clears ``task`` on shared action
    # instances, so the click event's task is the reliable source.
    task = getattr(event, "task", None) or action.task

    return task.window if task is not None else None


def preset_menu_label(preset_name):
    """Return the submenu label for a preset."""
    # A literal "&" in a preset name must not become a menu mnemonic.
    return preset_name.replace("&", "&&")


def used_shortcuts(window, store, include_presets=True):
    """Return ``{key sequence: what uses it}`` for the shortcuts a preset
    could collide with, keyed in Qt's portable text like the dialogs'.

    ``include_presets=False`` leaves the presets' own shortcuts out, for a
    dialog that checks them against each other itself.
    """
    # A preset's own submenu entry carries its shortcut too; it is listed
    # below as the preset, not under its bare menu label.
    preset_menu_entries = {
        (preset_menu_label(name), shortcut)
        for name, shortcut in store.shortcuts.items()
    }
    owners = {}

    for action in window.control.findChildren(QtGui.QAction):
        for sequence in action.shortcuts():
            shortcut = sequence.toString()

            if shortcut and (action.text(), shortcut) not in preset_menu_entries:
                owners.setdefault(shortcut, re.sub("&(.)", r"\1", action.text()))

    for qt_shortcut in window.control.findChildren(QtGui.QShortcut):
        shortcut = qt_shortcut.key().toString()

        if shortcut:
            owners.setdefault(
                shortcut, qt_shortcut.objectName() or UNNAMED_SHORTCUT_OWNER
            )

    # The device view dispatches these from key events, not QActions, and a
    # menu shortcut takes the key before the view sees it.
    for sequence, _, description, _ in KEYBOARD_SHORTCUTS:
        owners.setdefault(
            QtGui.QKeySequence(sequence).toString(),
            f"{DEVICE_VIEW_SHORTCUT_OWNER} ({description})",
        )

    if include_presets:
        for name, shortcut in store.shortcuts.items():
            owners.setdefault(shortcut, preset_shortcut_owner(name))

    return owners


def apply_preset_table_changes(store, deleted_names, changed_shortcuts):
    """Apply the Manage Layout Presets dialog's changes to ``store``."""
    for name in deleted_names:
        store.delete(name)

    for name, shortcut in changed_shortcuts.items():
        store.set_shortcut(name, shortcut)


class SaveLayoutPresetAction(TaskAction):
    """Name the window's current layout and save it as a preset."""

    id = SAVE_LAYOUT_PRESET_ACTION_ID
    name = SAVE_LAYOUT_PRESET_ACTION_NAME
    tooltip = "Save the current arrangement of the window as a named preset"

    #: Where the preset is saved.
    store = Instance(PresetStore)

    def perform(self, event=None):
        window = _event_window(self, event)

        if window is None:
            logger.warning("Save Current Layout: no task window to save")

            return

        # Captured before the naming dialog so an arrangement pyface cannot
        # express is reported before the user types a name for it.
        try:
            layout = window.get_window_layout()
        except RuntimeError as capture_error:
            logger.warning(
                f"Could not capture the window layout for a preset: "
                f"{capture_error}\n{describe_dock_widgets(window.control)}"
            )
            warning(
                window.control,
                "The current arrangement of the dock panes cannot be saved as "
                "a layout preset. Re-dock the floating or unusually split panes "
                "and try again.",
                title=SAVE_LAYOUT_PRESET_DIALOG_TITLE,
                cancel=False,
            )

            return

        model = self._ask_preset_details(window)

        if model is None:
            return

        preset_name = model.name.strip()

        try:
            self.store.save(
                preset_name,
                layout,
                window.application.layout_save_protocol,
                shortcut=model.shortcut,
            )
        except (OSError, pickle.PicklingError) as save_error:
            logger.error(f"Could not save layout preset '{preset_name}': {save_error}")
            error(
                window.control,
                f"The layout preset '{preset_name}' could not be saved.",
                title=SAVE_LAYOUT_PRESET_DIALOG_TITLE,
                detail=f"{save_error}",
            )

    def _ask_preset_details(self, window):
        """Return the confirmed dialog model, or None when the user cancels."""
        model = PresetName(
            name=self.store.next_default_name(),
            shortcut=self.store.next_default_shortcut(),
            used_shortcuts=used_shortcuts(window, self.store),
        )

        while True:
            ui = model.edit_traits(view=preset_name_view, parent=window.control)

            if not ui.result:
                return None

            preset_name = model.name.strip()

            if not self.store.has_preset(preset_name):
                return model

            answer = confirm(
                window.control,
                f"A layout preset named '{preset_name}' already exists. "
                f"Replace it with the current layout?",
                title=SAVE_LAYOUT_PRESET_DIALOG_TITLE,
                yes_label="Replace",
                no_label="Rename",
            )

            # "Rename" reopens the naming dialog; closing the prompt cancels.
            if answer == YES:
                return model

            if answer != NO:
                return None


class ApplyLayoutPresetAction(TaskAction):
    """Re-apply one saved preset to the window it is clicked in."""

    tooltip = "Arrange the window as saved in this preset"

    #: The preset this action applies.
    preset_name = Str()

    #: Where the preset is read from.
    store = Instance(PresetStore)

    def _name_default(self):
        return preset_menu_label(self.preset_name)

    def perform(self, event=None):
        window = _event_window(self, event)

        if window is None:
            logger.warning(f"Layout preset '{self.preset_name}': no task window")

            return

        layout = self.store.load(self.preset_name)

        if layout is None:
            warning(
                window.control,
                f"The layout preset '{self.preset_name}' could not be read and "
                f"was removed from the menu.",
                title=APPLY_LAYOUT_PRESET_DIALOG_TITLE,
                cancel=False,
            )
            self.store.refresh()

            return

        window_task_ids = {task.id for task in window.tasks}
        missing_task_ids = [
            task_id for task_id in layout.get_tasks() if task_id not in window_task_ids
        ]

        # Mirrors envisage's _create_windows: a layout naming a task this
        # window lacks is refused whole rather than half-applied.
        if missing_task_ids:
            logger.warning(
                f"Layout preset '{self.preset_name}' references tasks "
                f"{missing_task_ids} this window does not have; not applied"
            )
            warning(
                window.control,
                f"The layout preset '{self.preset_name}' was saved for a "
                f"different set of views and cannot be applied.",
                title=APPLY_LAYOUT_PRESET_DIALOG_TITLE,
                cancel=False,
            )

            return

        # Pyface re-docks the panes without touching their floating flag, so
        # an undocked pane would otherwise stay a free-floating window.
        for pane in window.dock_panes:
            pane.floating = False

        window.set_window_layout(layout)
        logger.info(f"Applied layout preset '{self.preset_name}'")


class ManageLayoutPresetsAction(TaskAction):
    """List the saved presets to edit their shortcuts or delete them."""

    id = MANAGE_LAYOUT_PRESETS_ACTION_ID
    name = MANAGE_LAYOUT_PRESETS_ACTION_NAME
    tooltip = "View, delete, and change the shortcuts of the layout presets"

    #: The presets being managed.
    store = Instance(PresetStore)

    def perform(self, event=None):
        window = _event_window(self, event)

        if window is None:
            logger.warning("Manage Layout Presets: no task window")

            return

        self.store.refresh()
        table = PresetTable.from_store(
            self.store, used_shortcuts(window, self.store, include_presets=False)
        )
        ui = table.edit_traits(view=preset_table_view, parent=window.control)

        if not ui.result:
            return

        deleted_names, changed_shortcuts = table.changes()

        # Asked once the table dialog has closed, so it never runs inside a
        # TableEditor commit.
        if deleted_names and not self._confirm_deletion(window, deleted_names):
            deleted_names = []

        try:
            apply_preset_table_changes(self.store, deleted_names, changed_shortcuts)
        except OSError as apply_error:
            logger.error(f"Could not update the layout presets: {apply_error}")
            error(
                window.control,
                "The layout presets could not all be updated.",
                title=MANAGE_LAYOUT_PRESETS_DIALOG_TITLE,
                detail=f"{apply_error}",
            )

    def _confirm_deletion(self, window, deleted_names):
        """Return whether the user confirms deleting ``deleted_names``."""
        listed_names = ", ".join(f"'{name}'" for name in deleted_names)
        answer = confirm(
            window.control,
            f"Delete the layout presets {listed_names}? This cannot be undone.",
            title=MANAGE_LAYOUT_PRESETS_DIALOG_TITLE,
            yes_label="Delete",
            no_label="Keep",
        )

        return answer == YES


class LayoutPresetsGroup(Group):
    """The Layout Presets submenu's items: one apply action per saved preset,
    rebuilt whenever the store's list changes (TaskToggleGroup's idiom)."""

    id = LAYOUT_PRESETS_ITEMS_GROUP_ID

    #: The presets the items mirror; None once the menu is discarded.
    store = Instance(PresetStore)

    @observe(["store.presets", "store.shortcuts"])
    def _rebuild_preset_actions(self, event):
        for item in self.items:
            item.destroy()

        self.clear()

        if self.store is None:
            return

        for preset_name in self.store.presets:
            self.append(
                ApplyLayoutPresetAction(
                    preset_name=preset_name,
                    store=self.store,
                    accelerator=self.store.shortcut_for(preset_name),
                )
            )

        if not self.store.presets:
            self.append(Action(name=NO_LAYOUT_PRESETS_LABEL, enabled=False))

        # Construction fills the group before it joins a menu; afterwards the
        # owning menu must re-render to show the new list.
        if self.parent is not None:
            self.parent.changed = True

    def destroy(self):
        # Releasing the store also drops this group's observer on it, so a
        # discarded menu bar leaves no listener behind.
        self.store = None


def view_menu_group(store):
    """Return the View-menu group: Save Current Layout..., the presets
    submenu, and Manage Layout Presets..."""
    return SGroup(
        SaveLayoutPresetAction(store=store),
        SMenu(
            LayoutPresetsGroup(store=store),
            id=LAYOUT_PRESETS_MENU_ID,
            name=LAYOUT_PRESETS_MENU_NAME,
        ),
        ManageLayoutPresetsAction(store=store),
        id=LAYOUT_PRESETS_GROUP_ID,
    )
