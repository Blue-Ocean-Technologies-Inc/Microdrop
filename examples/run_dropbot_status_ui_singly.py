import sys
import os

from envisage.api import CorePlugin
from envisage.ui.tasks.api import TasksPlugin

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from microdrop_utils.broker_server_helpers import dramatiq_workers_context, redis_server_context


def main(args):
    """Run the application."""

    # from dropbot_status_and_controls.plugin import DropbotStatusPlugin
    from dropbot_status_and_controls.plugin import DropbotStatusAndControlsPlugin
    from message_router.plugin import MessageRouterPlugin
    from BlankMicrodropCanvas.plugin import BlankMicrodropCanvasPlugin

    from BlankMicrodropCanvas.application import MicrodropCanvasTaskApplication

    plugins = [
        CorePlugin(),
        TasksPlugin(),
        BlankMicrodropCanvasPlugin(),
        # DropbotStatusPlotPlugin(task_id_to_contribute_view="microdrop_canvas.task"),
        # DropbotStatusPlugin(task_id_to_contribute_view="microdrop_canvas.task"),
        DropbotStatusAndControlsPlugin(task_id_to_contribute_view="microdrop_canvas.task"),
        MessageRouterPlugin(),
    ]

    app = MicrodropCanvasTaskApplication(plugins=plugins)

    with dramatiq_workers_context():
        app.run()


if __name__ == "__main__":
    with redis_server_context():
        main(sys.argv)
