import json
import os

from PySide6.QtCore import Signal, QObject, Slot

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ssh_controls.consts import GENERATE_KEYPAIR, KEY_UPLOAD
from .model import SSHControlModel
from traits.api import HasTraits, Instance, Str

class SSHControlViewModelSignals(QObject):
    """
    The ViewModel. It owns the Model and mediates between the
    View (GUI) and the Controller (worker).
    """

    # --- Signals for the View (UI Updates) ---
    key_gen_status_text_changed = Signal(str)
    key_upload_status_text_changed = Signal(str)
    show_message_box = Signal(str, str, str)  # type, title, text
    enable_gen_button = Signal(bool)
    enable_upload_button = Signal(bool)

class SSHControlViewModel(HasTraits):
    """
    The ViewModel. It owns the Model and mediates between the
    View (GUI) and the Controller (worker).
    """

    model = Instance(SSHControlModel)
    view_signals = Instance(SSHControlViewModelSignals)
    name = "SSH Control View Model"

    # --- Slots for the View (User Commands) ---
    @Slot()
    def generate_key_command(self):
        """Called when user clicks 'Generate Key' button."""
        if not self.model.key_name:
            self.view_signals.show_message_box.emit("error", "Error", "Key Name cannot be empty.")
            return

        self.view_signals.enable_gen_button.emit(False)
        self.view_signals.key_gen_status_text_changed.emit("Starting key generation/reading...")
        ssh_dir = os.path.expanduser("~/.ssh")

        message = json.dumps({"key_name": self.model.key_name, "ssh_dir": ssh_dir})
        publish_message(message, GENERATE_KEYPAIR)

    @Slot()
    def upload_key_command(self):
        """Called when user clicks 'Upload Key' button."""
        self.view_signals.enable_upload_button.emit(False)
        self.view_signals.key_upload_status_text_changed.emit("Starting key upload...")

        # Validation logic lives in the ViewModel
        if not self.model.generated_pub_key:
            self.view_signals.show_message_box.emit("error", "Error",
                                       "No key has been generated or read yet. Click 'Generate Key' first.")
            self.view_signals.enable_upload_button.emit(True)
            return

        if not all([self.model.host, self.model.port, self.model.username, self.model.password]):
            self.view_signals.show_message_box.emit("error", "Error", "All connection fields are required.")
            self.view_signals.enable_upload_button.emit(True)
            return

        # Pass a copy of the model's state to the controller
        publish_message(json.dumps(self.model.__dict__), KEY_UPLOAD)

     # --- Slots for the View (Data Binding) ---
    @Slot(str)
    def set_host(self, text):
        self.model.host = text

    @Slot(str)
    def set_port_str(self, text):
        try:
            self.model.port = int(text)
        except ValueError:
            self.view_signals.show_message_box.emit("error", "Error", "Port must be an integer.")
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

    # --- Slots for the Dramatiq Controller (Results) ---

    ###################### Key Gen Service ######################
    def _on_ssh_keygen_success_triggered(self, message):
        message = json.loads(message)
        pub_path = message.get("pub_key_path")
        priv_path = message.get("priv_key_path")
        pub_key = message.get("pub_key_data")
        self.model.generated_pub_key = pub_key
        self.model.generated_pub_key_path = pub_path
        self.view_signals.key_gen_status_text_changed.emit(f"Success! Using key from:\n{pub_path}\nPrivate key at:\n{priv_path}")
        self.view_signals.key_upload_status_text_changed.emit("Ready to upload generated/found key.")
        self.view_signals.enable_gen_button.emit(True)

    def _on_ssh_keygen_error_triggered(self, message):
        message = json.loads(message)
        title, text = message.get("title"), message.get("text")
        self.view_signals.key_gen_status_text_changed.emit(f"Error: {text}")
        self.view_signals.show_message_box.emit("error", title, text)
        self.view_signals.enable_gen_button.emit(True)

    def _on_ssh_keygen_warning_triggered(self, message):
        message = json.loads(message)
        title, text = message.get("title"), message.get("text")
        self.view_signals.show_message_box.emit("warning", title, text)

    ##################### Key Upload Service #########################
    def _on_ssh_key_upload_success_triggered(self, message):
        self.view_signals.key_upload_status_text_changed.emit(f"Success: {message}")
        self.view_signals.show_message_box.emit("info", "Success", message)
        self.view_signals.enable_upload_button.emit(True)

    def _on_ssh_key_upload_error_triggered(self, message):
        message = json.loads(message)
        title, text = message.get("title"), message.get("text")
        self.view_signals.key_upload_status_text_changed.emit(f"Error: {text}")
        self.view_signals.show_message_box.emit("error", title, text)
        self.view_signals.enable_upload_button.emit(True)
