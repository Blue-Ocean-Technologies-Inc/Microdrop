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

# Enthought library imports.
from pyface.action.api import Action, Group
from pyface.api import NO, YES
from pyface.tasks.action.api import SGroup, SMenu, TaskAction
from traits.api import Instance, Str, observe

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import confirm, error, warning

# Microdrop utils imports.
from microdrop_utils.tasks_runtime_helpers import describe_dock_widgets

# Local imports.
from .consts import (
    APPLY_LAYOUT_PRESET_DIALOG_TITLE,
    LAYOUT_PRESETS_GROUP_ID,
    LAYOUT_PRESETS_ITEMS_GROUP_ID,
    LAYOUT_PRESETS_MENU_ID,
    LAYOUT_PRESETS_MENU_NAME,
    NO_LAYOUT_PRESETS_LABEL,
    SAVE_LAYOUT_PRESET_ACTION_ID,
    SAVE_LAYOUT_PRESET_ACTION_NAME,
    SAVE_LAYOUT_PRESET_DIALOG_TITLE,
)
from .models.preset_name_model import PresetName
from .models.preset_store import PresetStore
from .views.preset_name_view import preset_name_view

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def _event_window(action, event):
    """Return the task window an action was triggered from, or None."""
    # The menu-bar rebuild on plugin hot-load clears ``task`` on shared action
    # instances, so the click event's task is the reliable source.
    task = getattr(event, "task", None) or action.task

    return task.window if task is not None else None


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

        preset_name = self._ask_preset_name(window)

        if preset_name is None:
            return

        try:
            self.store.save(
                preset_name, layout, window.application.layout_save_protocol
            )
        except (OSError, pickle.PicklingError) as save_error:
            logger.error(f"Could not save layout preset '{preset_name}': {save_error}")
            error(
                window.control,
                f"The layout preset '{preset_name}' could not be saved.",
                title=SAVE_LAYOUT_PRESET_DIALOG_TITLE,
                detail=f"{save_error}",
            )

    def _ask_preset_name(self, window):
        """Return the name to save under, or None when the user cancels."""
        model = PresetName(name=self.store.next_default_name())

        while True:
            ui = model.edit_traits(view=preset_name_view, parent=window.control)

            if not ui.result:
                return None

            preset_name = model.name.strip()

            if not self.store.has_preset(preset_name):
                return preset_name

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
                return preset_name

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
        # A literal "&" in a preset name must not become a menu mnemonic.
        return self.preset_name.replace("&", "&&")

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


class LayoutPresetsGroup(Group):
    """The Layout Presets submenu's items: one apply action per saved preset,
    rebuilt whenever the store's list changes (TaskToggleGroup's idiom)."""

    id = LAYOUT_PRESETS_ITEMS_GROUP_ID

    #: The presets the items mirror; None once the menu is discarded.
    store = Instance(PresetStore)

    @observe("store.presets")
    def _rebuild_preset_actions(self, event):
        for item in self.items:
            item.destroy()

        self.clear()

        if self.store is None:
            return

        for preset_name in self.store.presets:
            self.append(
                ApplyLayoutPresetAction(preset_name=preset_name, store=self.store)
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
    """Return the View-menu group: Save Current Layout... and the submenu."""
    return SGroup(
        SaveLayoutPresetAction(store=store),
        SMenu(
            LayoutPresetsGroup(store=store),
            id=LAYOUT_PRESETS_MENU_ID,
            name=LAYOUT_PRESETS_MENU_NAME,
        ),
        id=LAYOUT_PRESETS_GROUP_ID,
    )
