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
from traits.api import Instance, List, Str

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
from .models.preset_store import PresetStore


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
