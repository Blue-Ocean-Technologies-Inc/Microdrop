# Standard library imports.
import logging

# Enthought library imports.
from envisage.api import Plugin
from envisage.ids import PREFERENCES_PANES, TASK_EXTENSIONS
from envisage.ui.tasks.task_extension import TaskExtension
from traits.api import List
from traits.trait_types import Str

from microdrop_application.consts import PKG as microdrop_application_PKG

from .consts import PKG, PKG_name


class LoggerUIPlugin(Plugin):
    """Logger UI plugin."""

    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = PKG + ".plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG_name + " Plugin"

    #: The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    #### Contributions to extension points made by this plugin ################
    # views = List(contributes_to=VIEWS)
    preferences_panes = List(contributes_to=PREFERENCES_PANES)
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    ###########################################################################
    # Protected interface.
    ###########################################################################

    def _preferences_panes_default(self):
        from .preferences import LoggerPreferencesPane
        return [LoggerPreferencesPane]

    def _contributed_task_extensions_default(self):

        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,  # specify which task id it has to add on to
                dock_pane_factories=[self._dock_pane_factory],
            )
        ]

    # #### Plugin interface #####################################################
    #
    def start(self):
        """Starts the plugin."""
        from .model import LogModel, EnvisageLogHandler

        self._logger_model = LogModel()
        _handler = EnvisageLogHandler(_log_model_instance=self._logger_model)

        root_logger = logging.getLogger()
        root_logger.addHandler(_handler)

    def _dock_pane_factory(self, *args, **kwargs):
        from .dock_pane import LogPane

        return LogPane(model=self._logger_model)
