# system imports.
import json
import dramatiq
from PySide6.QtCore import QTimer
from apptools.preferences.preferences_helper import PreferencesHelper

# Enthought library imports.
from pyface.tasks.action.api import SMenu, SMenuBar, TaskToggleGroup
from pyface.tasks.api import PaneItem, Task, TaskLayout, HSplitter, VSplitter
from pyface.api import GUI
from traits.api import Instance, provides

from electrode_controller.consts import electrode_disable_request_publisher, disabled_channels_changed_publisher
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
from .dialogs.pyface_wrapper import information, confirm, YES
from .menus import AdvancedModeAction
from .preferences import MicrodropPreferences

logger = get_logger(__name__)


@provides(IDramatiqControllerBase)
class MicrodropTask(Task):
    ##########################################################
    # 'IDramatiqControllerBase' interface.
    ##########################################################

    # Child window should be an instance of Dialog Action
    wait_for_test_dialog = Instance(WaitForTestDialogAction)
    dramatiq_listener_actor = Instance(dramatiq.Actor)
    microdrop_preferences = Instance(MicrodropPreferences)

    listener_name = f"{PKG}_listener"

    #### 'MicrodropTask' interface #########################

    def _microdrop_preferences_default(self):
        return MicrodropPreferences(preferences=self.window.application.preferences)

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

        SMenu(AdvancedModeAction(), id="Edit", name="&Edit"),

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

        right = VSplitter(
            PaneItem("dropbot_status_and_controls.dock_pane"),
            PaneItem("protocol_grid.dock_pane"), # we want this to take up as much space as it can
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

    def _on_shorts_detected_triggered(self, message):
        """
        Handle shorts-detected messages. Parse the shorted channels and emit
        a Qt signal so the UI thread can show a confirmation dialog.
        """
        data = json.loads(message)
        shorts = data.get("Shorts_detected", [])
        if shorts:
            logger.info(f"Shorts detected on channels: {shorts}")
        else:
            logger.info(f"No Shorts detected")

        GUI.invoke_later(lambda: self._handle_shorts_detected_dialog_user_input(self._on_shorts_detected_dialog(shorts), shorts))

    def _on_shorts_detected_dialog(self, shorted_channels: list):
        """Offer the user the option to disable shorted channels (runs in UI thread)."""

        if shorted_channels:
            channels_str = ", ".join(str(ch) for ch in shorted_channels)
            return confirm(
                parent=None,
                title="Shorts Detected",
                message=(
                    f"Shorts detected on channels: [{channels_str}].<br><br>"
                    "<b>[RISKY]</b> Would you like keep these channels enabled?"
                ),
            )

        else:
            if not self.microdrop_preferences.suppress_no_shorts_information:
                _, checked = information(None, title="No Shorts Detected", message="No shorts were detected.",
                                         checkbox_text="Do not show again (can be undone from preferences)")

                self.microdrop_preferences.suppress_no_shorts_information = checked

            return None

    @staticmethod
    def _handle_shorts_detected_dialog_user_input(result, shorts):
        if result == YES:
            # do nothing, user wants to keep shorted channels enabled
            logger.info(f"User chose to enable shorted channels: {shorts}")
        else:
            logger.info("User declined to enable shorted channels")
            # frontend disable
            disabled_channels_changed_publisher.publish(disabled_channels=shorts)