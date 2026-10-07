# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
from functools import partial

# Enthought library imports.
from envisage.api import TASK_EXTENSIONS, ExtensionPoint, Plugin
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.api import SchemaAddition
from traits.api import Instance, List, Str, on_trait_change

# Microdrop package imports.
from microdrop_application.consts import PKG as microdrop_application_PKG

# Local imports.
from .consts import PKG, TUTORIALS, PKG_name, TutorialEntry
from .menus import TutorialCatalog

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class UserHelpPlugin(Plugin):
    """The Help menu, and the TUTORIALS extension point behind its submenu."""

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"

    #: The plugin name (suitable for displaying to the user).
    name = f"{PKG_name} Plugin"

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    #### Extension points offered by this plugin ##############################

    #: Help > Tutorials entries, contributed by sibling plugins with
    #: ``List(contributes_to=TUTORIALS)``; followed while the app runs.
    tutorials = ExtensionPoint(
        List(Instance(TutorialEntry)),
        id=TUTORIALS,
        desc="Tutorial pages listed under Help > Tutorials",
    )

    #: What the Tutorials submenu shows: the contributions, sorted by title.
    tutorial_catalog = Instance(TutorialCatalog, ())

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def start(self):
        """Fill the catalog and follow tutorial contributions from now on."""
        super().start()

        # The ``_items`` handler below fires only once this connects it.
        self.connect_extension_point_traits()
        self._update_catalog()

    @on_trait_change("tutorials_items")
    def _on_tutorials_changed(self, event):
        """A plugin contributing tutorials was loaded or unloaded at runtime.

        The synthetic ``_items`` event needs ``on_trait_change``: observe()
        rejects the name, as no such trait exists.
        """
        logger.info(f"Tutorials changed: +{len(event.added)} -{len(event.removed)}")
        self._update_catalog()

    def _update_catalog(self):
        self.tutorial_catalog.entries = sorted(
            self.tutorials, key=lambda entry: entry.title.casefold()
        )

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .menus import launcher_menu_factory, menu_factory

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        factory=partial(
                            menu_factory, tutorial_catalog=self.tutorial_catalog
                        ),
                        path="MenuBar/Help",
                    ),
                    SchemaAddition(
                        factory=launcher_menu_factory,
                        path="MenuBar/Help",
                        absolute_position="last",
                    ),
                ],
            )
        ]
