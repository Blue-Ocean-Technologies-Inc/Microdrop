import dramatiq
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QMessageBox, QPushButton
from PySide6.QtCore import Signal
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from logger.logger_service import get_logger
logger = get_logger(__name__)


class MainWindow(QWidget):
    show_popup_signal = Signal(str)
    def __init__(self):
        super().__init__()

        self.label = QLabel("Waiting for messages...")
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.publish_button = QPushButton("Publish message")
        self.publish_button.clicked.connect(self.publish_button_clicked)
        layout.addWidget(self.publish_button)
        self.show_popup_signal.connect(self.show_popup)

    def show_popup(self, message):
        self.label.setText(f"Received message: {message}")
        msg_box = QMessageBox()
        msg_box.setText(f"Received message: {message}")
        msg_box.exec()

    @staticmethod
    def publish_button_clicked():
        logger.info("GUI: Publishing message...")

        topic = "ui/event/publish_button/clicked"

        message = "Hello world!"
        publish_message(message, topic)


class MainWindowController:
    """
    Controller class for handling the main window logic.
    """

    topics_of_interest = ["ui/+/popup"]

    def __init__(self, window):
        """
        Initialize the MainWindowController with the given window.

        Parameters:
        window (QMainWindow): The main window instance.
        """
        self.window = window
        self.on_publish_button_clicked_actor = MainWindow.publish_button_clicked

        self.ui_listener_actor = self.create_ui_listener_actor()

    def create_ui_listener_actor(self):
        """
        Create a Dramatiq actor for listening to UI-related messages.

        Returns:
        dramatiq.Actor: The created Dramatiq actor.
        """

        @dramatiq.actor
        def ui_listener_actor(message, topic):
            """
            A Dramatiq actor that listens to UI-related messages.

            Parameters:
            message (str): The received message.
            topic (str): The topic of the message.
            """
            logger.info(f"UI_LISTENER: Received message: {message} from topic: {topic}")

            if "popup" in topic:
                self.window.show_popup_signal.emit(message)

        return ui_listener_actor


