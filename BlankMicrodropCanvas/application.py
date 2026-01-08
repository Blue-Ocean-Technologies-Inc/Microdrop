import os

from pyface.image_resource import ImageResource
from traits.api import observe

from envisage.ui.tasks.tasks_application import TasksApplication

from dropbot_controller.consts import START_DEVICE_MONITORING
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message


class MicrodropCanvasTaskApplication(TasksApplication):
    """Device Viewer application based on enthought envisage's The chaotic attractors Tasks application."""

    #### 'IApplication' interface #############################################

    # The application's globally unique identifier.
    id = "microdrop_canvas.app"

    # The application's user-visible name.
    name = "Microdrop Canvas"

    # branding
    icon = ImageResource(f'{os.path.dirname(__file__)}{os.sep}microdrop.ico')

    start_device_monitoring_on_init = False

    @observe('application_initialized')
    def _on_application_started(self, event):
        if self.start_device_monitoring_on_init:
            publish_message(message="", topic=START_DEVICE_MONITORING)
