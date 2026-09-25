# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Show the self-test progress and results dialogs from backend signals."""

# Standard library imports.
import json

# Enthought library imports.
from envisage.api import IApplication
from pyface.api import GUI
from pyface.qt.QtCore import QTimer
from traits.api import HasTraits, Instance, Int

# Microdrop package imports.
from dropbot_controller.consts import SelfTestResultsSignal, TestEvent

# Local imports.
from .self_test_dialogs import ResultsDialogAction, WaitForTestDialogAction

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class SelfTestDialogsController(HasTraits):
    """Translate SELF_TESTS_PROGRESS / SELF_TESTS_RESULTS into dialogs.

    Handlers run on a dramatiq worker thread, so every dialog change is
    marshalled onto the GUI thread with ``GUI.invoke_later``.
    """

    #: The application whose active task window parents the dialogs.
    application = Instance(IApplication)

    #: The open progress dialog of the running self-test session, if any.
    wait_for_test_dialog = Instance(WaitForTestDialogAction)

    #: The most recent results dialog; kept so it is not garbage collected.
    results_dialog = Instance(ResultsDialogAction)

    #: Number of tests in the running session, for the progress percentage.
    total_tests = Int(0)

    def on_self_tests_progress(self, raw_message):
        """Dispatch a progress message on its explicit event type."""
        try:
            data = json.loads(raw_message)
            event_type = data.get("type")
            payload = data.get("payload", {})
        except ValueError:
            return

        if event_type == TestEvent.SESSION_START:
            self._handle_session_start(payload)

        elif event_type == TestEvent.PROGRESS:
            self._handle_progress(payload)

        elif event_type == TestEvent.SESSION_END:
            self._handle_session_end(payload)

    def on_self_tests_results(self, message):
        """Present a single self-test's results dialog (#611).

        The backend writes the raw test results to a JSON file and publishes
        its path; the dialog loads and plots the file interactively.
        """
        signal = SelfTestResultsSignal.model_validate_json(message)

        def _show():
            self.results_dialog = ResultsDialogAction()
            self.results_dialog.perform(
                self._dialog_parent(),
                title=signal.title,
                test_name=signal.test_name,
                results_path=signal.results_path,
                failed_channels=signal.failed_channels,
            )

        GUI.invoke_later(_show)

    # ------------------ Protected interface ---------------------------------

    def _dialog_parent(self):
        """Return the active task, whose window parents the dialogs."""
        window = self.application.active_window if self.application else None

        return window.active_task if window else None

    def _handle_session_start(self, payload):
        self.total_tests = total = payload.get("total_tests", 0)

        def _show():
            self.wait_for_test_dialog = WaitForTestDialogAction()
            mode = "progress_bar" if total > 1 else "spinner"

            if total == 1:
                test = payload.get("tests")[0].replace("_", " ").title()
                test_name = f"Running Dropbot Self Test: {test}"
            else:
                test_name = "Running All Dropbot Self Tests..."

            self.wait_for_test_dialog.perform(
                self._dialog_parent(), test_name=test_name, mode=mode
            )

        GUI.invoke_later(_show)

    def _handle_progress(self, payload):
        # Sent right before a test runs, so the previous test has completed.
        name = payload.get("test_name", "")
        idx = int(payload.get("test_index", 0))

        def _update():
            if self.wait_for_test_dialog and self.total_tests:
                self.wait_for_test_dialog.set_progress(
                    int(idx * 100 / self.total_tests), name
                )

        GUI.invoke_later(_update)

    def _handle_session_end(self, payload):

        def _cleanup_reference():
            if self.wait_for_test_dialog:
                self.wait_for_test_dialog.close()
                self.wait_for_test_dialog = None

        def _close():
            if self.wait_for_test_dialog is None:
                return

            self.wait_for_test_dialog.set_progress_end(
                "Dropbot Self Test(s) are Complete! \n\n"
                "Report will be opened shortly..."
            )
            QTimer.singleShot(1200, _cleanup_reference)

        GUI.invoke_later(_close)
