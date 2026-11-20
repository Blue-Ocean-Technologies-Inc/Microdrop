# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The hub panel's controller: buttons to request topics, the two file /
flash saves behind their dialogs, and the preflight polling while the
pre-flight check shows. The replies come back through the plugin's
message handler into the same model.

The plugin keeps ONE controller for its lifetime and reopens the panel
through it, so the model's buttons have exactly one set of observers: a
controller per open would outlive its closed panel (the UIInfo cycle) and
fire every button twice after a reopen."""

# Standard library imports.
import time
from pathlib import Path

# Enthought library imports.
from pyface.api import YES, FileDialog
from pyface.timer.api import CallbackTimer
from traits.api import Float, Instance, Union, observe
from traitsui.api import Controller

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import confirm, file_dialog
from microdrop_application.helpers import get_current_experiment_directory
from portable_dropbot_controller.consts import LOCK_CHIP, move_tray_publisher

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..consts import (
    SELF_TEST_PREFLIGHT_READ,
    self_test_abort_publisher,
    self_test_run_publisher,
    self_test_save_calibration_publisher,
)
from ..models.consts import UNSAVED_PART_LABELS

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: Board-state refresh period (s) while the pre-flight check shows, as the
#: vendor's pre-flight dialog polls; a read goes out only once the previous
#: one was answered, or after PREFLIGHT_REPLY_TIMEOUT_S without a reply.
PREFLIGHT_POLL_S = 2.0
PREFLIGHT_REPLY_TIMEOUT_S = 5.0

#: Delay (s) of the state read after abandoning an unacknowledged run.
ABANDON_RESYNC_DELAY_S = 1.5

REPORT_WILDCARD = FileDialog.create_wildcard(
    "HTML report + raw data", "*.html"
) + FileDialog.create_wildcard("Markdown", "*.md")


class SelfTestHubController(Controller):
    """Buttons -> request topics. Opening the panel asks the backend for its
    state, so a reopened panel resyncs to a run in progress."""

    #: Polls the board state while the pre-flight check shows.
    preflight_timer = Instance(CallbackTimer)

    #: When the unanswered preflight read went out (time.monotonic());
    #: None once it was answered.
    preflight_read_sent_at = Union(None, Float)

    def is_panel_open(self):
        return (
            self.info is not None
            and self.info.ui is not None
            and self.info.ui.control is not None
        )

    def close_panel(self):
        if self.is_panel_open():
            self.info.ui.dispose()

    def init(self, info):
        self._read_preflight()
        self._poll_while_preflight_pending()

        return True

    def closed(self, info, is_ok):
        self._stop_polling()

    # ------------------------------------------------------------------ #
    # Run                                                                  #
    # ------------------------------------------------------------------ #

    @observe("model:run_selected_button")
    def _run_selected(self, event):
        self.model.request_preflight(self.model.selected_test_names())

    @observe("model:run_all_button")
    def _run_all(self, event):
        self.model.request_preflight(self.model.all_test_names())

    @observe("model:abort_button")
    def _abort(self, event):
        # An empty run_id stops whatever runs: the board's run is what the
        # operator sees, whichever run_id it carries.
        self_test_abort_publisher.publish({"run_id": ""})

        if self.model.mark_aborting():
            CallbackTimer.single_shot(
                interval=ABANDON_RESYNC_DELAY_S, callback=self._read_preflight
            )

    # ------------------------------------------------------------------ #
    # Pre-flight                                                           #
    # ------------------------------------------------------------------ #

    @observe("model:preflight_pending")
    def _on_preflight_pending_changed(self, event):
        self._poll_while_preflight_pending()

    @observe("model:preflight:replied")
    def _on_preflight_replied(self, event):
        self.preflight_read_sent_at = None

    @observe("model:preflight:refresh_button")
    def _refresh(self, event):
        self._read_preflight()

    @observe("model:preflight:tray_in_button")
    def _tray_in(self, event):
        move_tray_publisher.publish({"direction": "in", "actuate_pogos": False})

    @observe("model:preflight:tray_out_button")
    def _tray_out(self, event):
        move_tray_publisher.publish({"direction": "out", "actuate_pogos": False})

    @observe("model:preflight:pads_press_button")
    def _pads_press(self, event):
        publish_message(topic=LOCK_CHIP, message="True")

    @observe("model:preflight:pads_release_button")
    def _pads_release(self, event):
        publish_message(topic=LOCK_CHIP, message="False")

    @observe("model:preflight:start_button")
    def _start(self, event):
        if not self.model.preflight.can_start:
            return

        request = self.model.start_run()

        if request is not None:
            self_test_run_publisher.publish(request)

    @observe("model:preflight:cancel_button")
    def _cancel(self, event):
        self.model.cancel_preflight()

    # ------------------------------------------------------------------ #
    # Saves                                                                #
    # ------------------------------------------------------------------ #

    @observe("model:save_report_button")
    def _save_report(self, event):
        path = file_dialog(
            parent=self._parent_control(),
            action="save",
            default_path=str(_default_report_path()),
            wildcard=REPORT_WILDCARD,
        )

        if path:
            self.model.outputs.save_report(path)

    @observe("model:save_calibration_button")
    def _save_calibration(self, event):
        parts = " and the ".join(
            UNSAVED_PART_LABELS.get(p, p) for p in self.model.unsaved
        )
        answer = confirm(
            self._parent_control(),
            f"Save the {parts} from the last self-test to the signal board's "
            "flash now? It replaces the saved one.",
            title="Save calibration to flash",
        )

        if answer != YES:
            return

        self_test_save_calibration_publisher.publish(
            self.model.save_calibration_request()
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _read_preflight(self):
        self.preflight_read_sent_at = time.monotonic()
        publish_message(topic=SELF_TEST_PREFLIGHT_READ, message="")

    def _poll_preflight(self):
        """One poll tick: read again unless the last read is unanswered
        (and not yet timed out), or the board is disconnected."""

        if not self.is_panel_open() or not self.model.preflight_pending:
            self._stop_polling()

            return

        sent_at = self.preflight_read_sent_at
        waiting = (
            sent_at is not None
            and time.monotonic() - sent_at < PREFLIGHT_REPLY_TIMEOUT_S
        )

        if not waiting and self.model.preflight.board_connected:
            self._read_preflight()

    def _poll_while_preflight_pending(self):
        if not self.is_panel_open() or not self.model.preflight_pending:
            self._stop_polling()

            return

        if self.preflight_timer is None:
            self.preflight_timer = CallbackTimer(
                interval=PREFLIGHT_POLL_S, callback=self._poll_preflight
            )
            self.preflight_timer.start()

    def _stop_polling(self):
        if self.preflight_timer is not None:
            self.preflight_timer.stop()
            self.preflight_timer = None

    def _parent_control(self):
        return self.info.ui.control if self.info is not None and self.info.ui else None


def _default_report_path():
    """A time-stamped report name in the current experiment folder, or the
    home folder when that cannot be looked up (no Redis)."""
    name = time.strftime("self_test_report_%Y%m%d_%H%M%S.html")

    try:
        return get_current_experiment_directory() / name

    except Exception:
        logger.debug("No experiment directory; offering the home folder", exc_info=True)

        return Path.home() / name
