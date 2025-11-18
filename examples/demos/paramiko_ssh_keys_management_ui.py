import sys
import os
import warnings
from dataclasses import dataclass
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QGroupBox, QFormLayout,
    QLineEdit, QPushButton, QMessageBox, QLabel, QStatusBar,
    QMainWindow
)
from PySide6.QtCore import QThread, QObject, Signal, Slot

from dotenv import load_dotenv
from paramiko import AuthenticationException

load_dotenv()

from microdrop_utils import paramiko_helpers


@dataclass
class SshKeyModel:
    """A dataclass to hold the application's state."""
    host: str = os.getenv("REMOTE_HOST_IP_ADDRESS")
    port: int = os.getenv("REMOTE_SSH_PORT")
    username: str = os.getenv("REMOTE_HOST_USERNAME")
    password: str = os.getenv("REMOTE_PASSWORD")
    key_name: str = "id_rsa_new"
    generated_pub_key: str = ""
    generated_pub_key_path: str = ""


class SshKeyController(QObject):
    """
    A QObject-based worker that runs in a separate QThread.
    It handles all blocking network (paramiko) operations.
    Its signals are connected to the ViewModel.
    """

    # --- Signals for the ViewModel ---
    status_update = Signal(str)
    key_gen_success = Signal(str, str, str)  # pub_key, priv_path, pub_path
    key_gen_failure = Signal(str)  # error_message
    key_upload_success = Signal(str)  # success_message
    key_upload_failure = Signal(str, str)  # title, error_message
    warning = Signal(str, str)

    def __init__(self):
        super().__init__()

    @Slot(str, str)
    def generate_keypair(self, key_name, ssh_dir):
        """
        Generates a new RSA key pair or reads an existing one.
        If a .pub file with 'key_name' already exists, it reads it.
        Otherwise, it generates a new pair.
        """

        # Key does not exist, generate it
        self.status_update.emit("Generating 4096-bit RSA key...")

        try:
            with warnings.catch_warnings(record=True) as captured_warnings:
                pub_key_data, priv_key_path, pub_key_path = paramiko_helpers.generate_ssh_keypair(key_name, ssh_dir)

                self.key_gen_success.emit(pub_key_data, priv_key_path, pub_key_path)

                if captured_warnings:
                    self.warning.emit(captured_warnings[0].category.__name__, str(captured_warnings[0].message))
                    print(captured_warnings[0].message)


        except FileNotFoundError as e:
            self.key_gen_failure.emit(f"Public key exists, but private key is missing.\n Error: {e}")

        except OSError as e:
            self.key_gen_failure.emit(f"Failed to read/write public key.\nError: {e}")

        except ValueError as e:  # Catch invalid key names, etc.
            self.key_gen_failure.emit(f"Bad Key name. Error: {e}")

        except Exception as e:
            self.key_gen_failure.emit(f"Failed to generate public key.\nError: {e}")

    @Slot(dict)
    def perform_key_upload(self, config):
        """
        Uploads the public key to the server using password auth.
        'config' is a dict from the ViewModel's model.
        """
        pub_key = config.get("generated_pub_key")
        if not pub_key:
            self.key_upload_failure.emit("Error", "No key has been generated or read yet.")
            return

        self.status_update.emit("Validating input...")

        if not all([config["host"], config["port"], config["username"], config["password"]]):
            self.key_upload_failure.emit("Error", "All connection fields are required.")
            return

        ssh_client = None
        try:
            self.status_update.emit(f"Connecting to {config['host']} to upload key...")

            # Use the helper function to connect
            ssh_client = paramiko_helpers.get_password_authenticated_client(
                host=config["host"],
                port=config["port"],
                username=config["username"],
                password=config['password']
            )

            self.status_update.emit("Connected. Adding key to authorized_keys...")

            # Use the helper function to upload
            exit_status = paramiko_helpers.upload_public_key(ssh_client, pub_key)

            if exit_status == 0:
                self.key_upload_success.emit(
                    f"Public key authorized on {config['host']}.\nYou can now try connecting with your private key.")
            else:
                self.key_upload_failure.emit("Server Error",
                                             "The server failed to add the key. Check permissions or see server logs.")

        except AuthenticationException:
            self.key_upload_failure.emit("Error", "Authentication Failed. Please check your username and password.")
        except Exception as e:
            self.key_upload_failure.emit("Error", f"An unexpected error occurred: {e}")
        finally:
            if ssh_client:
                ssh_client.close()


class SshKeyViewModel(QObject):
    """
    The ViewModel. It owns the Model and mediates between the
    View (GUI) and the Controller (worker).
    """

    # --- Signals for the View (UI Updates) ---
    status_text_changed = Signal(str)
    key_gen_status_text_changed = Signal(str)
    key_upload_status_text_changed = Signal(str)
    show_message_box = Signal(str, str, str)  # type, title, text
    enable_gen_button = Signal(bool)
    enable_upload_button = Signal(bool)

    # --- Signals for the Controller (Commands) ---
    _generate_key_command = Signal(str, str)  # key_name, ssh_dir
    _upload_key_command = Signal(dict)  # config

    def __init__(self, model: SshKeyModel):
        super().__init__()
        self.model = model

    # --- Slots for the View (User Commands) ---
    @Slot()
    def generate_key_command(self):
        """Called when user clicks 'Generate Key' button."""
        if not self.model.key_name:
            self.show_message_box.emit("error", "Error", "Key Name cannot be empty.")
            return

        self.enable_gen_button.emit(False)
        self.key_gen_status_text_changed.emit("Starting key generation/reading...")
        self.status_text_changed.emit("Generating/reading key...")
        ssh_dir = os.path.expanduser("~/.ssh")
        self._generate_key_command.emit(self.model.key_name, ssh_dir)

    @Slot()
    def upload_key_command(self):
        """Called when user clicks 'Upload Key' button."""
        self.enable_upload_button.emit(False)
        self.key_upload_status_text_changed.emit("Starting key upload...")
        self.status_text_changed.emit("Uploading key...")

        # Validation logic lives in the ViewModel
        if not self.model.generated_pub_key:
            self.show_message_box.emit("error", "Error",
                                       "No key has been generated or read yet. Click 'Generate Key' first.")
            self.enable_upload_button.emit(True)
            return

        if not all([self.model.host, self.model.port, self.model.username, self.model.password]):
            self.show_message_box.emit("error", "Error", "All connection fields are required.")
            self.enable_upload_button.emit(True)
            return

        # Pass a copy of the model's state to the controller
        self._upload_key_command.emit(self.model.__dict__)

    # --- Slots for the View (Data Binding) ---
    @Slot(str)
    def set_host(self, text):
        self.model.host = text

    @Slot(str)
    def set_port_str(self, text):
        try:
            self.model.port = int(text)
        except ValueError:
            self.status_text_changed.emit("Error: Port must be a number.")
            if not text:
                self.model.port = 0  # or some invalid state

    @Slot(str)
    def set_username(self, text):
        self.model.username = text

    @Slot(str)
    def set_password(self, text):
        self.model.password = text

    @Slot(str)
    def set_key_name(self, text):
        self.model.key_name = text.strip()

    # --- Slots for the Controller (Results) ---
    @Slot(str)
    def on_status_update(self, text):
        self.status_text_changed.emit(text)

    @Slot(str, str, str)
    def on_key_gen_success(self, pub_key, priv_path, pub_path):
        self.model.generated_pub_key = pub_key
        self.model.generated_pub_key_path = pub_path
        self.key_gen_status_text_changed.emit(f"Success! Using key from:\n{pub_path}\nPrivate key at:\n{priv_path}")
        self.key_upload_status_text_changed.emit("Ready to upload generated/found key.")
        self.status_text_changed.emit("Key generation/reading successful.")
        self.enable_gen_button.emit(True)

    @Slot(str)
    def on_key_gen_failure(self, error):
        self.key_gen_status_text_changed.emit(f"Error: {error}")
        self.status_text_changed.emit("Key generation/reading failed.")
        self.enable_gen_button.emit(True)

    @Slot(str)
    def on_key_upload_success(self, message):
        self.key_upload_status_text_changed.emit(f"Success: {message}")
        self.status_text_changed.emit("Key upload successful.")
        self.show_message_box.emit("info", "Success", message)
        self.enable_upload_button.emit(True)

    @Slot(str, str)
    def on_key_upload_failure(self, title, error):
        self.key_upload_status_text_changed.emit(f"Error: {error}")
        self.status_text_changed.emit("Key upload failed.")
        self.show_message_box.emit("error", title, error)
        self.enable_upload_button.emit(True)

    @Slot(str, str)
    def on_warning(self, title, text):
        self.show_message_box.emit("warning", title, text)


class SshKeyUploaderApp(QMainWindow):
    """
    Main application window (View).
    It sets up the GUI, creates the ViewModel, and connects all signals.
    """

    def __init__(self):
        super().__init__()
        self.title = "SSH Key Portal"
        self.setWindowTitle(self.title)
        self.setGeometry(100, 100, 480, 500)

        # Create Model and ViewModel
        self.model = SshKeyModel()
        self.view_model = SshKeyViewModel(self.model)

        self.init_controller_thread()
        self.create_widgets()
        self.connect_signals()

    def init_controller_thread(self):
        """Initializes the QThread and Controller (Worker)."""
        self.thread = QThread()
        self.controller = SshKeyController()
        self.controller.moveToThread(self.thread)
        self.thread.start()

    def create_widgets(self):
        """Creates and lays out all the GUI elements."""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # --- Connection Details ---
        conn_group = QGroupBox("1. Connection Details (for key upload)")
        conn_layout = QFormLayout()

        # UPDATED: Initialize QLineEdits with model's default values
        self.host_entry = QLineEdit(self.model.host)
        self.port_entry = QLineEdit(str(self.model.port))
        self.user_entry = QLineEdit(self.model.username)
        self.pass_entry = QLineEdit(self.model.password)
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
        self.key_name_entry = QLineEdit(self.model.key_name)
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

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready.")

    def connect_signals(self):
        """Connects all signals and slots between View, ViewModel, and Controller."""

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
        self.view_model.status_text_changed.connect(self.status_bar.showMessage)
        self.view_model.key_gen_status_text_changed.connect(self.key_gen_status_label.setText)
        self.view_model.key_upload_status_text_changed.connect(self.key_upload_status_label.setText)
        self.view_model.show_message_box.connect(self.show_message_box)
        self.view_model.enable_gen_button.connect(self.generate_key_button.setEnabled)
        self.view_model.enable_upload_button.connect(self.upload_key_button.setEnabled)

        # 4. ViewModel -> Controller (Commands)
        self.view_model._generate_key_command.connect(self.controller.generate_keypair)
        self.view_model._upload_key_command.connect(self.controller.perform_key_upload)

        # 5. Controller -> ViewModel (Results)
        self.controller.status_update.connect(self.view_model.on_status_update)
        self.controller.key_gen_success.connect(self.view_model.on_key_gen_success)
        self.controller.key_gen_failure.connect(self.view_model.on_key_gen_failure)
        self.controller.key_upload_success.connect(self.view_model.on_key_upload_success)
        self.controller.key_upload_failure.connect(self.view_model.on_key_upload_failure)
        self.controller.warning.connect(self.view_model.on_warning)

    @Slot(str, str, str)
    def show_message_box(self, msg_type, title, text):
        """A slot to show a message box from the ViewModel."""
        if msg_type == "error":
            QMessageBox.critical(self, title, text)
        elif msg_type == "info":
            QMessageBox.information(self, title, text)
        else:
            QMessageBox.warning(self, title, text)

    def closeEvent(self, event):
        """Cleanly shut down the worker thread."""
        self.thread.quit()
        if not self.thread.wait(5000):
            self.thread.terminate()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SshKeyUploaderApp()
    window.show()
    sys.exit(app.exec())