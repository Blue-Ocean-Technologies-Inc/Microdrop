"""Envisage plugin wiring for the pluggable protocol tree.

Registers the PROTOCOL_COLUMNS extension point; contributes a dock
pane via TASK_EXTENSIONS. Other plugins contribute IColumn instances
by declaring `List(contributes_to=PROTOCOL_COLUMNS)` in their own
plugin class."""

from envisage.api import ExtensionPoint, Plugin, TASK_EXTENSIONS
from envisage.ui.tasks.task_extension import TaskExtension
from traits.api import Instance, List, Str

from microdrop_application.consts import PKG as microdrop_application_PKG
from message_router.consts import ACTOR_TOPIC_ROUTES

from pluggable_protocol_tree.builtins.duration_column import make_duration_column
from pluggable_protocol_tree.builtins.id_column import make_id_column
from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.consts import (
    ACTOR_TOPIC_DICT, PKG, PKG_name, PROTOCOL_COLUMNS,
)
from pluggable_protocol_tree.interfaces.i_column import IColumn


class PluggableProtocolTreePlugin(Plugin):
    id = f"{PKG}.plugin"
    name = PKG_name

    #: Other plugins contribute IColumn instances here
    contributed_columns = ExtensionPoint(
        List(Instance(IColumn)), id=PROTOCOL_COLUMNS,
        desc="Columns contributed by other plugins",
    )

    # Standard plumbing
    actor_topic_routing = List([ACTOR_TOPIC_DICT], contributes_to=ACTOR_TOPIC_ROUTES)

    task_id_to_contribute_view = Str(f"{microdrop_application_PKG}.task")
    contributed_task_extensions = List(contributes_to=TASK_EXTENSIONS)

    def _contributed_task_extensions_default(self):
        return [
            TaskExtension(
                task_id=self.task_id_to_contribute_view,
                dock_pane_factories=[self._make_dock_pane],
            ),
        ]

    def _make_dock_pane(self, *args, **kwargs):
        from pluggable_protocol_tree.views.dock_pane import PluggableProtocolDockPane
        columns = self._assemble_columns()
        return PluggableProtocolDockPane(columns=columns, *args, **kwargs)

    def _assemble_columns(self):
        builtins = [
            make_type_column(),
            make_id_column(),
            make_name_column(),
            make_duration_column(),
        ]
        return builtins + list(self.contributed_columns)
