import sys
from pathlib import Path

from envisage.ids import SERVICE_OFFERS
from envisage.service_offer import ServiceOffer

from message_router.plugin import MessageRouterPlugin
from microdrop_utils.broker_server_helpers import dramatiq_workers_context
from pluggable_protocol_tree.views.column.column import BaseColumnHandler

sys.path.insert(
    0, str(Path(__file__).parent.parent.parent)
)  # include microdrop package directory

from traits.api import List
from envisage.api import CorePlugin, Plugin
from envisage.ui.tasks.api import TasksPlugin

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

        # Change extension point from PROTOCOL_COLUMNS to SERVICE_OFFERS
        service_offers = List(contributes_to=SERVICE_OFFERS)

        def _service_offers_default(self):
            """Return the service offers."""
            return [
                # 1. Integer Spinner Column
                ServiceOffer(
                    protocol=IColumn,
                    factory=get_int_spinner_column,
                    properties={
                        "name": "int_spinner",
                        "id": "int_spinner",
                        "low": 0,
                        "high": 1000,
                    },
                ),
                # 2. Double Spinner Column
                ServiceOffer(
                    protocol=IColumn,
                    factory=get_double_spinner_column,
                    properties={
                        "name": "double_spinner",
                        "id": "double_spinner",
                        "low": 1.5,
                        "high": 200.5,
                        "decimals": 2,
                        "single_step": 0.5,
                    },
                ),
                # 3. Checkbox Column
                ServiceOffer(
                    protocol=IColumn,
                    factory=get_checkbox_column,
                    properties={
                        "name": "checkbox_column",
                        "id": "checkbox_column",
                    },
                ),
                # 4. String Editor Column
                ServiceOffer(
                    protocol=IColumn,
                    factory=get_string_editor_column,
                    properties={
                        "name": "string_editor_column",
                        "id": "string_editor_column",
                    },
                ),
                # 5. Await Reply Column (Uses a custom factory method)
                ServiceOffer(
                    protocol=IColumn,
                    factory=self._create_await_reply_column,
                    properties={
                        "name": "Await Reply",
                        "id": "await_reply_dramatiq",
                        "low": 0,
                        "high": 1000,
                    },
                ),
            ]

        def _create_await_reply_column(self, **properties):
            """
            Factory method to create the column with the custom AwaitHandler.
            This allows us to inject the handler object which cannot be
            easily defined in the properties dict.
            """

            class AwaitHandler(BaseColumnHandler):
                def on_run_step(self, row, context=None):
                    """
                    The main hook. Called when the row is the active step.
                    Args:
                        row: The row object (HasTraits)
                        context: A shared dictionary for passing data between steps
                    """
                    return None

            # Pass the handler and unpack the rest of the properties (name, id, low, high)
            return get_int_spinner_column(handler=AwaitHandler(), **properties)

    plugins = [
        CorePlugin(),
        TasksPlugin(),
        BlankMicrodropCanvasPlugin(),
        PluggableProtocolTreePlugin(task_id_to_contribute_view="microdrop_canvas.task"),
        ExtraColumnsPlugin(),
        MessageRouterPlugin(),
    ]

    app = MicrodropCanvasTaskApplication(plugins=plugins)

    with dramatiq_workers_context():
        app.run()


if __name__ == "__main__":
    main(sys.argv)
