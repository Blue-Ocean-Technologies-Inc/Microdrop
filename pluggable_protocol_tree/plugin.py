from envisage.extension_point import ExtensionPoint
from envisage.ids import TASK_EXTENSIONS
from envisage.plugin import Plugin
from envisage.ui.tasks.task_extension import TaskExtension
from traits.trait_types import List, Str, Any

from microdrop_application.consts import PKG as microdrop_application_PKG
from .interfaces.i_column import IColumn
from .models.steps import ActionStep

from .consts import PKG, PKG_name, PROTOCOL_COLUMNS
from .views.column.default_column_views import get_id_column
from .views.column.helpers import get_string_editor_column
from .views.dock_pane import ProtocolPane


class PluggableProtocolTreePlugin(Plugin):
    #### 'IPlugin' interface ##################################################

    #: The plugin unique identifier.
    id = f"{PKG}.plugin"
    #: The plugin name (suitable for displaying to the user).
    name = PKG_name

    # Extension Point: Other plugins contribute columns here.
    # Envisage handles the aggregation; no manual flattening needed.
    columns = ExtensionPoint(List(IColumn), id=PROTOCOL_COLUMNS)

    # The task id to contribute task extension view to
    task_id_to_contribute_view = Str(default_value=f"{microdrop_application_PKG}.task")

    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

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

        # id and name columns first then contributed columns
        columns = [
            # 1. HIERARCHICAL ID COLUMN (Read-Only, Leftmost)
            get_id_column(),
            # 2. Standard Columns
            get_string_editor_column(name="Name", id="name"),
        ] + self.columns

        pane.columns = columns

        return pane

    def start(self):
        super().start()

        # Patch ActionStep dynamically based on contributions
        for col in self.columns:
            attr = col.model.col_id
            default = col.model.default_value
            # Don't overwrite base traits
            ActionStep.add_class_trait(attr, Any(default))
