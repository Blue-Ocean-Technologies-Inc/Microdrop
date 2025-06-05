# sys imports
import os
from pathlib import Path

from envisage.ui.tasks.tasks_application import DEFAULT_STATE_FILENAME

from dropbot_controller.consts import START_DEVICE_MONITORING
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
# Local imports.
from .preferences import MicrodropPreferences

# Enthought library imports.
from envisage.ui.tasks.api import TasksApplication
from pyface.tasks.api import TaskWindowLayout
from traits.api import Bool, Instance, List, Property, observe, Directory
from pyface.image_resource import ImageResource
from pyface.splash_screen import SplashScreen

from PySide6.QtWidgets import QStatusBar

from microdrop_utils._logger import get_logger
logger = get_logger(__name__, level="DEBUG")


class MicrodropApplication(TasksApplication):
    """Device Viewer application based on enthought envisage's The chaotic attractors Tasks application."""

    #### 'IApplication' interface #############################################

    # The application's globally unique identifier.
    id = "microdrop.app"

    # The application's user-visible name.
    name = "Microdrop Next Gen"

    #### 'TasksApplication' interface #########################################

    #: The directory on the local file system used to persist window layout
    #: information.
    state_location = Path.home() / ".microdrop_next_gen"

    #: The filename that the application uses to persist window layout
    #: information.
    state_filename = DEFAULT_STATE_FILENAME

    # The default window-level layout for the application.
    default_layout = List(TaskWindowLayout)

    # Whether to restore the previous application-level layout when the applicaton is started.
    always_use_default_layout = Property(Bool)

    # what directory to use for the application generated folders/files
    app_data_dir = Property(Directory)
    # above two traits are gotten from the preferences file

    # branding
    icon = Instance(ImageResource)
    splash_screen = Instance(SplashScreen)

    def _icon_default(self):
        return ImageResource(f'{os.path.dirname(__file__)}{os.sep}microdrop.ico')

    def _splash_screen_default(self):
        return SplashScreen(
            image=ImageResource(f'{os.path.dirname(__file__)}{os.sep}scibots.jpg'),
            text="Microdrop-Next-Gen v.alpha"
        )

    #### 'Application' interface ####################################

    preferences_helper = Instance(MicrodropPreferences)

    ###########################################################################
    # Private interface.
    ###########################################################################

    #### Trait initializers ###################################################

    # note: The _default after a trait name to define a method is a convention to indicate that the trait is a
    # default value for another trait.

    def _default_layout_default(self):
        """
        Trait initializer for the default_layout task, which is the active task to be displayed. It is gotten from the
        preferences.

        """
        active_task = self.preferences_helper.default_task
        tasks = [factory.id for factory in self.task_factories]
        return [
            TaskWindowLayout(*tasks, active_task=active_task, size=(800, 600))
        ]

    def _preferences_helper_default(self):
        """
        Retireve the preferences from the preferences file using the DeviceViewerPreferences class.
        """
        return MicrodropPreferences(preferences=self.preferences)

    #### Trait property getter/setters ########################################

    # the _get and _set tags in the methods are used to define a getter and setter for a trait property.

    def _get_always_use_default_layout(self):
        return self.preferences_helper.always_use_default_layout

    def _get_app_data_dir(self):
        return self.preferences_helper.app_data_dir

    @observe('started')
    def _on_application_started(self, event):
        publish_message(message="", topic=START_DEVICE_MONITORING)

    #### Handler for Layout Restore Errors if any ##########################
    def start(self):
        try:
            logger.debug("Starting new Microdrop application instance.")
            return super().start()
        except Exception as e:
            
            import traceback
            logger.debug("Error restoring layout, falling back to default layout.")
            traceback.print_exc()
            
            self.preferences_helper.always_use_default_layout = True
            
            return super().start()

    # status bar at the bottom of the window 
    @observe('windows:items')
    def _on_windows_updated(self, event):
        for window in event.added:
            if hasattr(window, "control") and window.control is not None:
                if not hasattr(window.control, "_statusbar"):
                    status_bar = QStatusBar(window.control)
                    status_bar.setFixedHeight(30)
                    status_bar.showMessage("Ready", 10000)

                    window.control.setStatusBar(status_bar)
                    window.control._statusbar = status_bar