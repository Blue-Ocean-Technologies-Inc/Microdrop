# system imports.
import json
import os
import dramatiq
from PySide6.QtCore import QTimer

# Hardware backend: same env as plugin_consts; determines which status dock pane to show.
_HW_BACKEND = (os.environ.get("MICRODROP_HW_BACKEND") or "dropbot").strip().lower()
_STATUS_DOCK_PANE_ID = "opendrop_status.dock_pane" if _HW_BACKEND == "opendrop" else "dropbot_status.dock_pane"

# Enthought library imports.
from pyface.tasks.action.api import SMenu, SMenuBar, TaskToggleGroup
from pyface.tasks.api import PaneItem, Task, TaskLayout, HSplitter, VSplitter
from pyface.api import GUI
from traits.api import Instance, provides

# Local imports.
from .consts import PKG
from dropbot_controller.consts import TestEvent

from microdrop_utils.pyface_helpers import StatusBarManager
from microdrop_utils.dramatiq_controller_base import (generate_class_method_dramatiq_listener_actor,
                                                      basic_listener_actor_routine)
from microdrop_application.views.microdrop_pane import MicrodropCentralCanvas
from microdrop_utils.i_dramatiq_controller_base import IDramatiqControllerBase

from dropbot_tools_menu.self_test_dialogs import WaitForTestDialogAction

from logger.logger_service import get_logger
logger = get_logger(__name__)


@provides(IDramatiqControllerBase)
class MicrodropTask(Task):
    ##########################################################
    # 'IDramatiqControllerBase' interface.
    ##########################################################

    # Child window should be an instance of Dialog Action
    wait_for_test_dialog = Instance(WaitForTestDialogAction)
    dramatiq_listener_actor = Instance(dramatiq.Actor)

    listener_name = f"{PKG}_listener"

    #### 'MicrodropTask' interface #########################

    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    def traits_init(self):
        """
        This function needs to be here to let the listener be initialized to the default value automatically.
        We just do it manually here to make the code clearer.
        We can also do other initialization routines here if needed.

        This is equivalent to doing:

        def __init__(self, **traits):
            super().__init__(**traits)

        """

        logger.info("Starting Microdrop listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=self.listener_name,
            class_method=self.listener_actor_routine)

    #### 'Task' interface #####################################################

    id = f"{PKG}.task"
    name = PKG.title().replace("_", " ")

    menu_bar = SMenuBar(

        SMenu(id="File", name="&File"),

        SMenu(id="Edit", name="&Edit"),

        SMenu(id="Tools", name="&Tools"),

        SMenu(TaskToggleGroup(), id="View", name="&View")
    )

    def create_central_pane(self):
        """Create the central pane with the device viewer widget with a default view.
        """

        return MicrodropCentralCanvas()

    def create_dock_panes(self):
        """Create any dock panes needed for the task."""
        return [
        ]

    def activated(self):
        """Called when the task is activated."""
        logger.info("Microdrop task activated")
        if self.window.status_bar_manager is None:
            logger.info("Microdrop task: No status bar manager created: Adding now...")
            self._add_status_bar_to_window()

    def _add_status_bar_to_window(self):
        logger.info(f"Adding status bar to Microdrop Task window.")
        self.window.status_bar_manager = StatusBarManager(messages=["Free Mode"], size_grip=True)

        self.window.status_bar_manager.status_bar.setContentsMargins(30, 0, 30, 0)

    ###########################################################################
    # Protected interface.
    ###########################################################################

    # ------------------ Trait initializers ---------------------------------

    def _default_layout_default(self):

        top_right = HSplitter(
            PaneItem(_STATUS_DOCK_PANE_ID),
            PaneItem("manual_controls.dock_pane"),
        )

        right = VSplitter(
            top_right,
            PaneItem("protocol_grid.dock_pane", height=1000), # we want this to take up as much space as it can
        )

        return TaskLayout(
            right=right,
            left=PaneItem("device_viewer.dock_pane", width=1000), # we want this to take up as much space as it can
        )

    ##########################################################
    # Public interface.
    ##########################################################
    def show_help(self):
        """Show the help dialog."""
        logger.info("Showing help dialog.")

    ##########################################################
    # Including below function permanently this class, so no need to dynamically attach it in dropbot_tools_menu/plugin.py
    # This callback is registered in ACTOR_TOPIC_DICT of dropbot_tools_menu and does nothing if that plugin is not loaded
    # The relevant code has to be here since the dialogs need to be manipulated from the main task
    ###########################################################

    def _on_self_tests_progress_triggered(self, raw_message):
        try:
            data = json.loads(raw_message)
            event_type = data.get("type")
            payload = data.get("payload", {})
        except ValueError:
            return

        # 1. Dispatch based on Explicit Event Type
        if event_type == TestEvent.SESSION_START:
            self._handle_session_start(payload)

        elif event_type == TestEvent.PROGRESS:
            self._handle_progress(payload)

        elif event_type == TestEvent.SESSION_END:
            self._handle_session_end(payload)

    # --- Separated Logic Handlers ---

    def _handle_session_start(self, payload):
        self._total_tests = total = payload.get("total_tests", 0)

        def _show():
            self.wait_for_test_dialog = WaitForTestDialogAction()
            mode = "progress_bar" if total > 1 else "spinner"

            if total == 1:
                test = payload.get("tests")[0].replace("_", " ").title()
                test_name = f"Running Dropbot Self Test: {test}"
            else:
                test_name = "Running All Dropbot Self Tests..."

            self.wait_for_test_dialog.perform(
                self, test_name=test_name, mode=mode
            )

        GUI.invoke_later(_show)

    def _handle_progress(self, payload):
        # message sent right before test is run
        # So the last test was completed.
        name = payload.get("test_name", "")
        idx = int(payload.get("test_index", 0))
        def _update():
            if hasattr(self, "wait_for_test_dialog") and self.wait_for_test_dialog:
                # You might need to pass 'total' in payload or store it in self
                # For now assuming percentage is calculated here or passed
                self.wait_for_test_dialog.set_progress(int(idx * 100 / self._total_tests), name)

        GUI.invoke_later(_update)

    def _handle_session_end(self, payload):

        def _cleanup_reference():
            if hasattr(self, "wait_for_test_dialog") and self.wait_for_test_dialog:
                self.wait_for_test_dialog.close()
                self.wait_for_test_dialog = None  # Cleanup reference

        def _close():
                self.wait_for_test_dialog.set_progress_end("Dropbot Self Test(s) are Complete! \n\nReport will be opened shortly...")
                QTimer.singleShot(1200, _cleanup_reference)

        GUI.invoke_later(_close)
