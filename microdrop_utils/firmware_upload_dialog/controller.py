"""Device-agnostic controller for the shared firmware-upload dialog.

Pure frontend: Upload publishes a validated upload request via the injected
publisher; the backend's started / log / finished signals arrive through the
owning plugin's message handler, which ferries them into the injected
``live_state.firmware_upload_message`` — the dispatch="ui" observer below
applies them to the model on the GUI thread (the model is only ever mutated
there).

A concrete plugin wires one of these up with its device-specific bits: the
live_state singleton (carrying ``firmware_upload_message`` /
``board_device_id`` / ``board_port``), the upload publisher, the cancel and
signal topics, and the firmware-dir / default-device-id values.
"""

import json

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QFileDialog, QSizePolicy

from traits.api import Any, HasTraits, Instance, Str, observe
from apptools.preferences.api import PreferencesHelper

from microdrop_application.dialogs.base_message_dialog import BaseMessageDialog
from microdrop_application.dialogs.pyface_wrapper import YES, confirm, error
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.traitsui_qt_helpers import stretch_group_layouts_horizontally

from .consts import DEVICE_ID_PLACEHOLDER
from .model import FirmwareUploadModel
from .view import build_panel_stylesheet, firmware_upload_view

from logger.logger_service import get_logger
logger = get_logger(__name__)


class FirmwareUploadDialogController(HasTraits):
    """Builds the styled dialog, publishes upload/cancel requests to the
    backend, and applies the backend's firmware-upload signals to the model
    on the GUI thread via a dispatch="ui" observer on live_state.

    Reopen-safe: keep one instance alive (the menu action does) and call
    ``open()`` again — a visible dialog is raised instead of duplicated, a
    closed one is rebuilt around the same model, so the log history and
    options survive reopens.
    """

    # ---- device-specific wiring (set by the plugin) ----------------------
    #: HasTraits carrying firmware_upload_message / board_device_id /
    #: board_port (the plugin's live_state singleton).
    live_state = Instance(HasTraits)
    #: A peripheral_device_controller_base UploadFirmwarePublisher instance.
    upload_publisher = Any()
    cancel_topic = Str()
    started_topic = Str()
    log_topic = Str()
    finished_topic = Str()
    default_firmware_dir = Str()
    default_device_id = Str()
    dialog_title = Str("Upload Firmware")

    model = Instance(FirmwareUploadModel)
    preferences = Instance(PreferencesHelper)

    dialog = Any()
    traits_ui = Any()

    def _model_default(self):
        return FirmwareUploadModel(
            default_device_id=self.default_device_id,
            preferences=self.preferences,
        )

    # ---- dialog assembly -------------------------------------------------

    def open(self):
        if self.dialog is not None and self.dialog.isVisible():
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        self.dialog = BaseMessageDialog(
            title=self.dialog_title,
            message="Flash the MicroPython firmware to a connected Pico "
                    "board. Configure the source, port, and options below, "
                    "then press Upload.",
            dialog_type=BaseMessageDialog.TYPE_QUESTION,
            buttons={
                "Close": {"action": self._request_close, "role": "exit"},
                "Upload": {"action": self._start_upload},
            },
            resizable=True,
        )
        # Wide two-pane layout: give the config column and the log console
        # room side by side (the base dialog would otherwise cap at 1000x800
        # and open much narrower).
        self.dialog.setMinimumSize(QSize(980, 620))
        self.dialog.setMaximumSize(QSize(1700, 1200))
        # Keep the intro message compact so the config panel gets the space.
        self.dialog.message_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.traits_ui = self.model.edit_traits(
            view=firmware_upload_view, kind="subpanel", parent=self.dialog)
        # The built control is the HSplit's QSplitter; the left column's own
        # QScrollArea is made transparent by the panel stylesheet.
        panel = self.traits_ui.control
        panel.setObjectName("firmwareUploadPanel")
        panel.setStyleSheet(build_panel_stylesheet(self.dialog))
        stretch_group_layouts_horizontally(panel)
        self.dialog.add_content_widget(panel)

        # Reflect the connected board's identity into the read-only device id,
        # and point the port combo at its auto-detected port (a board may have
        # connected before the dialog was opened). Shows the placeholder until
        # a whoami has actually been received.
        self.model.device_id = (
            self.live_state.board_device_id or DEVICE_ID_PLACEHOLDER)
        self.model.sync_selected_port(self.live_state.board_port)

        self.dialog.finished.connect(self._on_dialog_closed)
        self.dialog.show()
        # The base dialog queues a fit-to-message adjustSize() at singleShot(0)
        # which would shrink the dialog back to its size hint — queue the
        # opening size after it so it wins.
        QTimer.singleShot(0, lambda: self.dialog.resize(1120, 700))

    def _request_close(self):
        if self.model.uploading:
            if confirm(self.dialog,
                       "An upload is still running — abort it and close?",
                       title="Upload in progress") != YES:
                return
            publish_message(message="", topic=self.cancel_topic)
        self.dialog.close_with_result(BaseMessageDialog.RESULT_CANCEL)

    def _on_dialog_closed(self, *args):
        if self.traits_ui is not None:
            self.traits_ui.dispose()
            self.traits_ui = None

    @observe("model:browse_firmware_zip")
    def _on_browse_firmware_zip(self, event):
        """Zip-browse button: pick a .zip and set it as the firmware source
        (the Directory field's own Browse handles folders)."""
        path, _ = QFileDialog.getOpenFileName(
            self.dialog, "Select firmware zip bundle", "",
            "Zip archives (*.zip);;All files (*)")
        if path:
            self.model.firmware_source = path

    # ---- upload run ------------------------------------------------------

    def _start_upload(self):
        if self.model.uploading:
            return
        problems = self.model.validation_problems()
        if problems:
            error(self.dialog,
                  "Fix the following before uploading:",
                  title="Cannot upload",
                  detail="\n".join(problems), detail_collapsible=False)
            return
        # Optimistically lock the controls; the backend's STARTED/FINISHED
        # signals confirm and release.
        self.model.uploading = True
        try:
            self.upload_publisher.publish(**self.model.upload_request_kwargs())
        except Exception as e:
            logger.warning(f"Failed to publish upload request: {e}")
            self.model.upload_log += f"Failed to publish upload request: {e}\n"
            self.model.uploading = False

    @observe("live_state:firmware_upload_message", dispatch="ui")
    def _apply_backend_message(self, event):
        """Apply one backend publish to the model (GUI thread)."""
        topic, message = event.new
        if topic == self.log_topic:
            self.model.upload_log += f"{message}\n"
        elif topic == self.started_topic:
            self.model.uploading = True
            self.model.upload_log += f"{message}\n"
        elif topic == self.finished_topic:
            self.model.uploading = False
            self.model.upload_log += f"{self._finished_verdict(message)}\n"

    @staticmethod
    def _finished_verdict(message):
        """Human-readable verdict from a firmware_upload_finished payload."""
        try:
            payload = json.loads(message)
        except Exception:
            logger.error(f"Unparseable upload-finished payload: {message!r}")
            return f"\nUpload finished (unparseable result: {message!r})."
        if "error" in payload:
            return f"\nUpload CRASHED: {payload['error']}"
        return ("\nUpload finished successfully." if payload.get("success")
                else "\nUpload FAILED (see the log above).")

    @observe("live_state:board_device_id", dispatch="ui")
    def _on_board_device_id_changed(self, event):
        """The board's whoami id arrived (or cleared on disconnect) — mirror
        it into the read-only Device ID field, falling back to the
        placeholder so the field only shows a real id while a whoami is
        currently backing it (GUI thread)."""
        self.model.device_id = event.new or DEVICE_ID_PLACEHOLDER

    @observe("live_state:board_port", dispatch="ui")
    def _on_board_port_changed(self, event):
        """The auto-detected port changed — keep the port combo in sync
        (GUI thread)."""
        self.model.sync_selected_port(event.new)

    @observe("model:uploading")
    def _on_uploading_changed(self, event):
        upload_button = self.dialog.get_button("Upload") if self.dialog else None
        if upload_button is not None:
            upload_button.setEnabled(not event.new)
