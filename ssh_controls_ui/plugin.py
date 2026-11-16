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
from envisage.api import (
    PREFERENCES_CATEGORIES,
    PREFERENCES_PANES,
    TASK_EXTENSIONS,
    Plugin,
)
from envisage.ui.tasks.api import TaskExtension
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import List, Str

# Microdrop package imports.
from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG
from user_help_plugin.consts import TUTORIAL_ORDER_MANAGEMENT, TUTORIALS, TutorialEntry

# Local imports.
from .consts import (
    ACTOR_TOPIC_DICT,
    PKG,
    SSH_REMOTE_BACKEND_TUTORIAL_HTML_PATH,
    PKG_name,
)


class SSHUIPlugin(Plugin):
    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"

    #: The plugin name (suitable for displaying to the user).
    name = f"{PKG_name} Plugin"

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    preferences_categories = List(contributes_to=PREFERENCES_CATEGORIES)

    #: Help > Tutorials entry for the Remote Controls dialogs.
    tutorials = List(contributes_to=TUTORIALS)

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .menus import menu_factory

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                actions=[
                    SchemaAddition(
                        factory=menu_factory,
                        path="MenuBar/Tools",
                    )
                ],
            )
        ]

    def _preferences_panes_default(self):
        from .preferences import SSHControlPreferencesPane

        return [SSHControlPreferencesPane]

    def _preferences_categories_default(self):
        from .preferences import ssh_controls_tab

        return [ssh_controls_tab]

    def _tutorials_default(self):
        # After Plugin Management (+0) and Preferences (+10) in its section.
        return [
            TutorialEntry(
                title="SSH & Remote Backend Tutorial",
                path=SSH_REMOTE_BACKEND_TUTORIAL_HTML_PATH,
                order=TUTORIAL_ORDER_MANAGEMENT + 20,
            ),
        ]
