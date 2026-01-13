from envisage.api import Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.task_extension import TaskExtension
from traits.api import List, Str, Any, Property

from message_router.consts import ACTOR_TOPIC_ROUTES
from microdrop_application.consts import PKG as microdrop_application_PKG
from .interfaces.i_column import IColumn
from .models.row import ActionRow

from .consts import PKG, PKG_name, ACTOR_TOPIC_DICT
from .views.column.default_columns import get_id_column, get_duration_column
from .views.column.helpers import get_string_editor_column
from .views.dock_pane import ProtocolPane


class PluggableProtocolTreePlugin(Plugin):
    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = f"{PKG}.plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG_name

    # This plugin contributes some actors that can be called using certain routing keys.
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    # The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    ## properties
    column_contributions = Property(observe='application')

    def _get_column_contributions(self):
        return self.application.get_services(protocol=IColumn)


    def _contributed_task_extensions_default(self):
        # We inject the actual columns found from extensions into the Pane
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[self.get_protocol_pane],
            )
        ]

    def get_protocol_pane(self, *args, **kwargs):
        pane = ProtocolPane(*args, **kwargs)

        pane.columns = self.columns

        return pane

    def start(self):
        super().start()

        default_columns = [
            get_id_column(),
            get_string_editor_column(name="Name", id="name"),
            get_duration_column(),
        ]

        self.columns = default_columns + self.column_contributions

        # Patch ActionRow dynamically based on contributions
        for col in self.column_contributions:
            attr = col.model.col_id
            default = col.model.default_value
            # Don't overwrite base traits
            ActionRow.add_class_trait(attr, Any(default))
