"""Qt widget for the Sync Remote Experiments dialog."""
from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QPushButton, QLabel, QProgressBar, QMessageBox,
)


class SyncDialogView(QWidget):
    """Qt View for the Sync Remote Experiments dialog."""

    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.view_model = view_model

        layout = QVBoxLayout(self)

        # --- Connection fields ---
        conn_group = QGroupBox("1. Remote Host")
        conn_layout = QFormLayout()
        self.host_entry = QLineEdit()
        self.port_entry = QLineEdit()
        self.user_entry = QLineEdit()
        self.key_name_entry = QLineEdit()
        conn_layout.addRow("Host:", self.host_entry)
        conn_layout.addRow("Port:", self.port_entry)
        conn_layout.addRow("Username:", self.user_entry)
        conn_layout.addRow("Key Name:", self.key_name_entry)
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # --- Paths ---
        paths_group = QGroupBox("2. Paths")
        paths_layout = QFormLayout()
        self.device_id_entry = QLineEdit()
        self.remote_path_entry = QLineEdit()
        self.local_dest_label = QLabel()
        self.local_dest_label.setWordWrap(True)
        paths_layout.addRow("Device ID:", self.device_id_entry)
        paths_layout.addRow("Remote source:", self.remote_path_entry)
        paths_layout.addRow("Local destination:", self.local_dest_label)
        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)

        # --- Sync action ---
        action_group = QGroupBox("3. Sync")
        action_layout = QVBoxLayout()
        self.sync_button = QPushButton("Sync Remote Experiments")
        self.sync_button.setMinimumHeight(40)
        action_layout.addWidget(self.sync_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setVisible(False)
        action_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Status: Idle")
        self.status_label.setWordWrap(True)
        action_layout.addWidget(self.status_label)

        action_group.setLayout(action_layout)
        layout.addWidget(action_group)
        layout.addStretch()

    def initialize_field_values(self, host="", port=22, username="",
                                key_name="", remote_path="",
                                local_dest="", device_id=""):
        self.host_entry.setText(host)
        self.port_entry.setText(str(port))
        self.user_entry.setText(username)
        self.key_name_entry.setText(key_name)
        self.device_id_entry.setText(device_id)
        self.remote_path_entry.setText(remote_path)
        self.local_dest_label.setText(local_dest)

    def connect_signals(self):
        vm = self.view_model
        s = vm.view_signals

        # View -> ViewModel (bindings)
        self.host_entry.textChanged.connect(vm.set_host)
        self.port_entry.textChanged.connect(vm.set_port_str)
        self.user_entry.textChanged.connect(vm.set_username)
        self.key_name_entry.textChanged.connect(vm.set_key_name)
        self.remote_path_entry.textChanged.connect(vm.set_remote_path)
        self.device_id_entry.textChanged.connect(vm.set_device_id)

        # View -> ViewModel (commands)
        self.sync_button.clicked.connect(vm.sync_command)

        # ViewModel -> View (UI updates)
        s.status_changed.connect(
            lambda text: self.status_label.setText(f"Status: {text}")
        )
        s.enable_sync_button.connect(self.sync_button.setEnabled)
        s.show_in_progress.connect(self.progress_bar.setVisible)
        s.show_message_box.connect(self.show_message_box)
        s.show_timeout_warning.connect(self.show_timeout_warning)
        s.close_dialog.connect(self._close_parent_window)

        # The ViewModel's prefs observer emits these when auto-derivation
        # updates device_id (e.g., host changed) — keep the widget fields
        # in sync without echoing through the editingFinished loop.
        s.device_id_changed.connect(self._on_device_id_changed)
        s.local_dest_changed.connect(self.local_dest_label.setText)

    @Slot(str)
    def _on_device_id_changed(self, new_id):
        """Set entry text without re-emitting textChanged for the same value."""
        if self.device_id_entry.text() != new_id:
            # blockSignals avoids a feedback loop back into vm.set_device_id
            self.device_id_entry.blockSignals(True)
            try:
                self.device_id_entry.setText(new_id)
            finally:
                self.device_id_entry.blockSignals(False)

    @Slot(str, str, str)
    def show_message_box(self, msg_type, title, text):
        if msg_type == "error":
            QMessageBox.critical(self, title, text)
        elif msg_type == "info":
            QMessageBox.information(self, title, text)
        else:
            QMessageBox.warning(self, title, text)

    @Slot()
    def show_timeout_warning(self):
        """Prompt the user when the sync takes longer than expected."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Still syncing")
        box.setText(
            "The remote sync is taking longer than expected. "
            "Keep waiting, or quit and let it finish in the background?"
        )
        keep_btn = box.addButton("Keep Waiting", QMessageBox.AcceptRole)
        quit_btn = box.addButton("Quit", QMessageBox.RejectRole)
        box.exec()

        if box.clickedButton() is keep_btn:
            self.view_model.keep_waiting_command()
        else:
            self.view_model.quit_command()

    @Slot()
    def _close_parent_window(self):
        """Close the containing QMainWindow when the ViewModel asks to."""
        window = self.window()
        if window is not None:
            window.close()
