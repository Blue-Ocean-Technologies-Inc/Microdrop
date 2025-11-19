from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox, QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLineEdit, QPushButton, QLabel


class SSHControlView(QWidget):
    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        layout = QVBoxLayout(self)

        # --- Connection Details ---
        conn_group = QGroupBox("1. Connection Details (for key upload)")
        conn_layout = QFormLayout()

        # UPDATED: Initialize QLineEdits with model's default values
        self.host_entry = QLineEdit()
        self.port_entry = QLineEdit()
        self.user_entry = QLineEdit()
        self.pass_entry = QLineEdit()
        self.pass_entry.setEchoMode(QLineEdit.Password)

        conn_layout.addRow("Host:", self.host_entry)
        conn_layout.addRow("Port:", self.port_entry)
        conn_layout.addRow("Username:", self.user_entry)
        conn_layout.addRow("Password:", self.pass_entry)

        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # --- Key Generation ---
        gen_group = QGroupBox("2. Generate or Read Key Pair")
        gen_layout = QFormLayout()

        # This was already correct
        self.key_name_entry = QLineEdit()
        gen_layout.addRow("Local Key Name:", self.key_name_entry)

        self.generate_key_button = QPushButton("Generate / Read Key")
        self.generate_key_button.setMinimumHeight(30)
        gen_layout.addRow(self.generate_key_button)

        self.key_gen_status_label = QLabel("Status: Ready to generate or read key.")
        self.key_gen_status_label.setWordWrap(True)
        gen_layout.addRow(self.key_gen_status_label)

        gen_group.setLayout(gen_layout)
        layout.addWidget(gen_group)

        # --- Key Upload ---
        upload_group = QGroupBox("3. Upload Public Key to Server")
        upload_layout = QVBoxLayout()

        self.upload_key_button = QPushButton("Upload Generated / Read Public Key")
        self.upload_key_button.setMinimumHeight(40)
        upload_layout.addWidget(self.upload_key_button)

        self.key_upload_status_label = QLabel("Status: Waiting for key generation or reading.")
        self.key_upload_status_label.setWordWrap(True)
        upload_layout.addWidget(self.key_upload_status_label)

        upload_group.setLayout(upload_layout)
        layout.addWidget(upload_group)

        layout.addStretch()

        self.connect_signals()

    def connect_signals(self):
        """Connects all signals and slots between View, ViewModel, and Controller."""

        view_model_signals = self.view_model.view_signals

        # 1. View -> ViewModel (Data Binding)
        self.host_entry.textChanged.connect(self.view_model.set_host)
        self.port_entry.textChanged.connect(self.view_model.set_port_str)
        self.user_entry.textChanged.connect(self.view_model.set_username)
        self.pass_entry.textChanged.connect(self.view_model.set_password)
        self.key_name_entry.textChanged.connect(self.view_model.set_key_name)

        # 2. View -> ViewModel (Commands)
        self.generate_key_button.clicked.connect(self.view_model.generate_key_command)
        self.upload_key_button.clicked.connect(self.view_model.upload_key_command)

        # 3. ViewModel -> View (UI Updates)

        view_model_signals.key_gen_status_text_changed.connect(self.key_gen_status_label.setText)
        view_model_signals.key_upload_status_text_changed.connect(self.key_upload_status_label.setText)
        view_model_signals.show_message_box.connect(self.show_message_box)
        view_model_signals.enable_gen_button.connect(self.generate_key_button.setEnabled)
        view_model_signals.enable_upload_button.connect(self.upload_key_button.setEnabled)


    @Slot(str, str, str)
    def show_message_box(self, msg_type, title, text):
        """A slot to show a message box from the ViewModel."""
        if msg_type == "error":
            QMessageBox.critical(self, title, text)
        elif msg_type == "info":
            QMessageBox.information(self, title, text)
        else:
            QMessageBox.warning(self, title, text)


