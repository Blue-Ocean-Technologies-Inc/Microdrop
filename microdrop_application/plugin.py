# Standard library imports.
import os.path

from traits.api import List
from message_router.consts import ACTOR_TOPIC_ROUTES

# Enthought library imports.
from envisage.api import Plugin, PREFERENCES, PREFERENCES_PANES, TASKS
from envisage.ui.tasks.api import TaskFactory

# local imports
from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class MicrodropPlugin(Plugin):
    """Microdrop plugin based on enthought envisage's The chaotic attractors plugin."""

    #### 'IPlugin' interface ##################################################

    # The plugin's unique identifier.
    id = PKG

    # The plugin's name (suitable for displaying to the user).
    name = "microdrop_main_app"

    #### Contributions to extension points made by this plugin ################

    preferences = List(contributes_to=PREFERENCES)
    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    tasks = List(contributes_to=TASKS)
    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    ###########################################################################
    # Protected interface.
    ###########################################################################

    def _preferences_default(self):
        filename = os.path.join(os.path.dirname(__file__), "preferences.ini")
        return ["file://" + filename]

    def _preferences_panes_default(self):
        from .preferences import MicrodropPreferencesPane

        return [MicrodropPreferencesPane]

    def _tasks_default(self):
        from .task import MicrodropTask

        return [
            TaskFactory(
                id=f"{PKG}.task",
                name=f"{PKG_name} Task",
                factory=MicrodropTask,
            )
        ]
