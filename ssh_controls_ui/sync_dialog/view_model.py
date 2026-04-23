"""ViewModel for the Sync Remote Experiments dialog.

Mediates between the Qt View (widget.py) and the Dramatiq response
listener. Responsible for:
  - validating pre-publish conditions (identity file exists, fields
    non-empty),
  - publishing the sync request via the typed publisher,
  - managing a 60s timeout QTimer that surfaces a "Keep Waiting / Quit"
    prompt to the user,
  - dispatching Dramatiq-delivered ``started`` / ``success`` / ``error``
    topics onto Qt signals the View binds to.
"""
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from pydantic import ValidationError
from traits.api import HasTraits, Instance, Str

from logger.logger_service import get_logger
from ssh_controls.consts import experiments_sync_publisher
from .model import SyncDialogModel

logger = get_logger(__name__)

# Timeout (ms) before showing the "Keep Waiting / Quit" prompt.
TIMEOUT_MS = 60_000


class SyncDialogViewModelSignals(QObject):
    """Qt signals the View binds to for UI updates."""
    status_changed      = Signal(str)
    enable_sync_button  = Signal(bool)
    show_in_progress    = Signal(bool)          # spinner visibility
    show_timeout_warning = Signal()             # triggers Keep-Waiting/Quit dialog
    show_message_box    = Signal(str, str, str) # msg_type, title, text
    close_dialog        = Signal()


class SyncDialogViewModel(HasTraits):
    """ViewModel for the Sync Remote Experiments dialog."""
    model = Instance(SyncDialogModel)
    view_signals = Instance(SyncDialogViewModelSignals)
    name = Str("Sync Dialog View Model")

    # QTimer is owned by Qt; assigned in traits_init rather than declared
    # as a Trait so it stays tied to the Qt event loop.
    _timeout_timer = None

    def traits_init(self):
        self._timeout_timer = QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval(TIMEOUT_MS)
        self._timeout_timer.timeout.connect(self._on_timeout_fired)

    # ---- View -> ViewModel (commands) ------------------------------------
    @Slot()
    def sync_command(self):
        """Called when the user clicks the Sync button."""
        if not all([self.model.host, self.model.username, self.model.port]):
            self.view_signals.show_message_box.emit(
                "error", "Missing fields",
                "Host, username and port are required."
            )
            return

        identity_path = self.model.resolve_identity_path()
        if not Path(identity_path).exists():
            self.view_signals.show_message_box.emit(
                "error", "SSH key missing",
                f"Expected {identity_path} to exist. "
                "Generate + upload it via the SSH Key Portal first."
            )
            return

        dest = self.model._default_dest()
        os.makedirs(dest, exist_ok=True)

        src = self.model.resolve_src()

        self.model.in_progress = True
        self.view_signals.enable_sync_button.emit(False)
        self.view_signals.show_in_progress.emit(True)
        self.view_signals.status_changed.emit(
            "Request sent, waiting for backend..."
        )

        try:
            experiments_sync_publisher.publish(
                host=self.model.host,
                port=int(self.model.port),
                username=self.model.username,
                identity_path=identity_path,
                src=src,
                dest=dest,
            )
        except ValidationError as e:
            self._reset_ui_state()
            self.view_signals.show_message_box.emit(
                "error", "Invalid sync request", str(e),
            )
            return

        self._timeout_timer.start()

    @Slot()
    def quit_command(self):
        """Frontend-only dismiss — backend rsync keeps running (v1 behavior)."""
        self._timeout_timer.stop()
        self.model.in_progress = False
        self.view_signals.close_dialog.emit()

    @Slot()
    def keep_waiting_command(self):
        """User chose to keep waiting after the timeout warning."""
        self._timeout_timer.start()
        self.view_signals.status_changed.emit("Still syncing...")

    # ---- Data binding slots ---------------------------------------------
    @Slot(str)
    def set_host(self, text):
        self.model.host = text

    @Slot(str)
    def set_port_str(self, text):
        try:
            self.model.port = int(text)
        except ValueError:
            if not text:
                self.model.port = 0

    @Slot(str)
    def set_username(self, text):
        self.model.username = text

    @Slot(str)
    def set_key_name(self, text):
        self.model.key_name = text.strip()

    @Slot(str)
    def set_remote_path(self, text):
        self.model.remote_experiments_path = text

    # ---- Dramatiq-triggered handlers ------------------------------------
    def _on_sync_experiments_started_triggered(self, message):
        if not self.model.in_progress:
            logger.info("sync started received after quit; ignoring")
            return
        self._timeout_timer.start()
        self.view_signals.status_changed.emit("Backend acknowledged, syncing...")

    def _on_sync_experiments_success_triggered(self, message):
        if not self.model.in_progress:
            logger.info("sync success received after quit; logged only: %s", message)
            return
        self._timeout_timer.stop()
        try:
            payload = json.loads(message)
            text = payload.get("message", "Sync complete.")
        except Exception:
            text = "Sync complete."
        self._reset_ui_state()
        self.view_signals.show_message_box.emit("info", "Sync complete", text)
        self.view_signals.close_dialog.emit()

    def _on_sync_experiments_error_triggered(self, message):
        if not self.model.in_progress:
            logger.error("sync error received after quit; logged only: %s", message)
            return
        self._timeout_timer.stop()
        try:
            payload = json.loads(message)
            title = payload.get("title", "Sync failed")
            text = payload.get("text", message)
        except Exception:
            title, text = "Sync failed", message
        self._reset_ui_state()
        self.view_signals.show_message_box.emit("error", title, text)

    # ---- Internal helpers ------------------------------------------------
    def _on_timeout_fired(self):
        self.view_signals.show_timeout_warning.emit()

    def _reset_ui_state(self):
        self.model.in_progress = False
        self.view_signals.show_in_progress.emit(False)
        self.view_signals.enable_sync_button.emit(True)
