# enthought imports
from pyface.action.schema.schema_addition import SchemaAddition
from traits.api import List, Str
from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.api import TaskExtension

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from .consts import ACTOR_TOPIC_DICT, PKG, PKG_name


class ManualControlsPlugin(Plugin):
    """ Contributes UI actions on top of the IPython Kernel Plugin. """

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

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .DockPane import ManualControlsDockPane
        from .menus import menu_factory

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[ManualControlsDockPane],
                actions=[
                    SchemaAddition(
                        factory=menu_factory,
                        before="TaskToggleGroup",
                        path='MenuBar/View',
                    )

                ]
            )
        ]
