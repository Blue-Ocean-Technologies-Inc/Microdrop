# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The hub's plugin-lifetime listener: validates the backend's self-test
signals and hands them to the hub model on the GUI thread."""

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from pyface.api import GUI
from traits.api import Instance, Str

# Microdrop package imports.
from template_status_and_controls.base_message_handler import BaseMessageHandler

# Local imports.
from ..consts import (
    SELF_TEST_LISTENER,
    SelfTestCalibrationSaved,
    SelfTestFinished,
    SelfTestPreflight,
    SelfTestProgress,
    SelfTestResult,
)
from ..models.self_tests_model import SelfTestHubModel

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class SelfTestsMessageHandler(BaseMessageHandler):
    """Feeds the self-test signals to the plugin's SelfTestHubModel, which
    outlives the panel. The model filters by run_id."""

    model = Instance(SelfTestHubModel)

    name = Str(SELF_TEST_LISTENER)

    def _on_self_test_preflight_updated_triggered(self, body):
        self._apply_on_gui_thread(SelfTestPreflight, body, self.model.apply_preflight)

    def _on_self_test_progress_triggered(self, body):
        self._apply_on_gui_thread(SelfTestProgress, body, self.model.apply_progress)

    def _on_self_test_result_triggered(self, body):
        self._apply_on_gui_thread(SelfTestResult, body, self.model.apply_result)

    def _on_self_test_finished_triggered(self, body):
        self._apply_on_gui_thread(SelfTestFinished, body, self.model.apply_finished)

    def _on_self_test_calibration_saved_triggered(self, body):
        self._apply_on_gui_thread(
            SelfTestCalibrationSaved, body, self.model.apply_calibration_saved
        )

    @staticmethod
    def _apply_on_gui_thread(message_class, body, apply):
        try:
            message = message_class.model_validate_json(str(body))

        except ValidationError as exc:
            logger.error(f"Dropped a malformed {message_class.__name__}: {exc}")

            return

        # Handlers run on the Dramatiq worker thread; the model's observers
        # update an open panel, so they must run on the GUI one.
        GUI.invoke_later(apply, message)
