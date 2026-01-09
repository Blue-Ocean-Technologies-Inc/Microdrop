import sys
import os

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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def main(args):
    """Run the application."""

    from BlankMicrodropCanvas.plugin import BlankMicrodropCanvasPlugin
    from pluggable_protocol_tree.plugin import PluggableProtocolTreePlugin

    from BlankMicrodropCanvas.application import MicrodropCanvasTaskApplication

    class ExtraColumnsPlugin(Plugin):
        id = "extra_columns.plugin"

        contributions = List(IColumn, contributes_to=PROTOCOL_COLUMNS)

        def _contributions_default(self):

            int_col = get_int_spinner_column(name='int_spinner', id='int_spinner', low=0, high=1000)
            double_col = get_double_spinner_column(name='double_spinner', id='double_spinner', low=1.5, high=200.5, decimals=2)
            check_col = get_checkbox_column(name='checkbox_column', id='checkbox_column')
            str_edit_col = get_string_editor_column(name='string_editor_column', id='string_editor_column')

            return [int_col, double_col, check_col, str_edit_col]

    plugins = [
        CorePlugin(),
        TasksPlugin(),
        BlankMicrodropCanvasPlugin(),
        PluggableProtocolTreePlugin(task_id_to_contribute_view="microdrop_canvas.task"),
        ExtraColumnsPlugin(),
    ]

    app = MicrodropCanvasTaskApplication(plugins=plugins)

    app.run()


if __name__ == "__main__":
    main(sys.argv)
