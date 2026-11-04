# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""LayoutPresetsPlugin — save the window layout under a name and re-apply
it later from the View menu."""

# Standard library imports.
from pathlib import Path

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.tasks.action.api import SchemaAddition
from traits.api import Instance, List, Str, observe
from traits.observation.api import trait

# Microdrop package imports.
from microdrop_application.consts import PKG as microdrop_application_PKG

# Local imports.
from .consts import (
    LAYOUT_PRESETS_GROUP_ID,
    PKG,
    PRESETS_DIRNAME,
    VIEW_MENU_LAYOUT_GROUP_ID,
    VIEW_MENU_PATH,
    PKG_name,
)
from .models.preset_store import PresetStore, task_layout_for


class LayoutPresetsPlugin(Plugin):
    """Contributes the View-menu layout-preset actions."""

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"

    #: The plugin name (suitable for displaying to the user).
    name = f"{PKG_name} Plugin"

    #: The task whose View menu the actions are added to.
    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #### 'LayoutPresetsPlugin' interface ######################################

    #: The saved presets, shared by every menu bar built for the task.
    store = Instance(PresetStore)

    def start(self):
        """Point the store at the application's state folder and scan it."""
        super().start()

        self.store = PresetStore(
            directory=str(Path(self.application.state_location) / PRESETS_DIRNAME)
        )
        self.store.refresh()

    def stop(self):
        """Hand Reset Layout back the task's built-in default layout."""
        self.store = None

        super().stop()

    #### Trait change handlers ################################################

    # Fires on the store too, so a hot-load start and stop resync windows.
    @observe("store.default_preset")
    def _apply_default_preset_to_open_windows(self, event):
        for window in getattr(self.application, "windows", []):
            self._apply_default_preset(window)

    @observe(trait("application", notify=False).trait("window_opened", optional=True))
    def _apply_default_preset_to_new_window(self, event):
        self._apply_default_preset(event.new.window)

    def _apply_default_preset(self, window):
        """Make the window's Reset Layout restore the default preset's pane
        arrangement, or the task's built-in one when there is none."""
        task = next(
            (
                task
                for task in window.tasks
                if task.id == self.task_id_to_contribute_view
            ),
            None,
        )

        if task is None:
            return

        default_preset = self.store.default_preset if self.store is not None else ""
        window_layout = self.store.load(default_preset) if default_preset else None
        task_layout = (
            task_layout_for(window_layout, task.id)
            if window_layout is not None
            else None
        )

        if task_layout is None:
            # Deleting the override brings back the task's _default_layout_default.
            task.reset_traits(["default_layout"])

            return

        task.default_layout = task_layout.clone_traits()

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        id=LAYOUT_PRESETS_GROUP_ID,
                        factory=self._view_menu_group,
                        path=VIEW_MENU_PATH,
                        after=VIEW_MENU_LAYOUT_GROUP_ID,
                    ),
                ],
            )
        ]

    def _view_menu_group(self):
        # Bound method, not the bare factory: the store only exists once the
        # plugin has started, and the menu bar is built after that.
        from .menus import view_menu_group

        return view_menu_group(self.store)
