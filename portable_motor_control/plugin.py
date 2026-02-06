# enthought imports
from envisage.ids import TASK_EXTENSIONS
from traits.api import Str, List
from envisage.api import Plugin
from envisage.ui.tasks.api import TaskExtension

from microdrop_application.consts import PKG as microdrop_application_PKG

from .consts import PKG, PKG_name


class MotorControlsPlugin(Plugin):
    """ Contributes UI actions on top of the IPython Kernel Plugin. """

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = "motor_controls.plugin"

    #: The plugin name (suitable for displaying to the user).
    name = f"Motor Controls Plugin"

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    #### Contributions to extension points made by this plugin ################

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    #### Trait initializers ###################################################

    def _contributed_task_extensions_default(self):
        from .DockPane import MotorControlDockPane

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[MotorControlDockPane],
            )
        ]
