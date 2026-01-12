import sys
from pathlib import Path

from message_router.plugin import MessageRouterPlugin
from microdrop_utils.broker_server_helpers import dramatiq_workers_context
from pluggable_protocol_tree.views.column.column import BaseColumnHandler

sys.path.insert(
    0, str(Path(__file__).parent.parent.parent)
)  # include microdrop package directory

from traits.api import List
from envisage.api import CorePlugin, Plugin
from envisage.ui.tasks.api import TasksPlugin

from pluggable_protocol_tree.consts import PROTOCOL_COLUMNS
from pluggable_protocol_tree.interfaces.i_column import IColumn
from pluggable_protocol_tree.views.column.helpers import (
    get_int_spinner_column,
    get_double_spinner_column,
    get_checkbox_column,
    get_string_editor_column,
)


def main(args):
    """Run the application."""

    from BlankMicrodropCanvas.plugin import BlankMicrodropCanvasPlugin
    from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin

    from BlankMicrodropCanvas.application import MicrodropCanvasTaskApplication

    class ExtraColumnsPlugin(Plugin):
        id = "extra_columns.plugin"

        contributions = List(IColumn, contributes_to=PROTOCOL_COLUMNS)

        def _contributions_default(self):

            int_col = get_int_spinner_column(
                name="int_spinner", id="int_spinner", low=0, high=1000
            )
            double_col = get_double_spinner_column(
                name="double_spinner",
                id="double_spinner",
                low=1.5,
                high=200.5,
                decimals=2,
                single_step=0.5,
            )
            check_col = get_checkbox_column(
                name="checkbox_column", id="checkbox_column"
            )
            str_edit_col = get_string_editor_column(
                name="string_editor_column", id="string_editor_column"
            )

            class AwaitHandler(BaseColumnHandler):
                def on_run_step(self, row, context=None):
                    """
                    The main hook. Called when the row is the active step.

                    Args:
                        row: The row object (HasTraits)
                        context: A shared dictionary for passing data between steps
                    """
                    return None


            col_with_response = get_int_spinner_column(
                name="Await Reply", id="await_reply_dramatiq", low=0, high=1000, handler=AwaitHandler()
            )


            return [int_col, double_col, check_col, str_edit_col, col_with_response]

    plugins = [
        CorePlugin(),
        TasksPlugin(),
        BlankMicrodropCanvasPlugin(),
        PluggableProtocolTreePlugin(task_id_to_contribute_view="microdrop_canvas.task"),
        ExtraColumnsPlugin(),
        MessageRouterPlugin()
    ]

    app = MicrodropCanvasTaskApplication(plugins=plugins)

    with dramatiq_workers_context():
        app.run()


if __name__ == "__main__":
    main(sys.argv)
