from pathlib import Path
import sys

from pyface.action.api import Action
from pyface.qt.QtWidgets import (QDialog, QVBoxLayout, QLabel, 
                                 QDialogButtonBox, QProgressBar,
                                 QPushButton, QTextBrowser)
from pyface.qt.QtCore import Qt, Slot, Signal, QSize, QTimer
from pyface.qt.QtGui import QPixmap, QMovie

from traits.api import Str
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from dropbot_controller.consts import SELF_TEST_CANCEL
from logger.logger_service import get_logger
logger = get_logger(__name__)


class SelfTestIntroDialog(QDialog):
    def __init__(self, parent=None, image_dir=None, image_count=5, interval=1000):
        super().__init__(parent)

        self.setWindowTitle("DropBot Self-Test: Prepare Device")
        self.setModal(True)

        if image_dir is None:
            self.image_dir = Path(__file__).parent / "resources" / "self_test_images"
        else:
            self.image_dir = Path(image_dir)
        self.image_count = image_count
        self.interval = interval
        self.current_index = 0
        self.images = []
        self.timer = None

        # Main layout
        self.layout = QVBoxLayout(self)
        self.build_window()

        self.load_images()
        self.image_update()

        self.setLayout(self.layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.image_update)
        self.timer.start(self.interval)

    def build_window(self):
        # instruction label
        instruction_label = QLabel(
            "<b>Please insert the DropBot test board, for more info see </b>"
            '<a href="https://github.com/sci-bots/dropbot-v3/wiki/DropBot-Test-Board#loading-dropbot-test-board">'
            '<span style="text-decoration: underline; color:#2980b9;">DropBot Test Board documentation</span>'
            "</a>"
        )
        instruction_label.setWordWrap(True)
        instruction_label.setOpenExternalLinks(True)
        instruction_label.setAlignment(Qt.AlignLeft)
        self.layout.addWidget(instruction_label)

        # Image Display
        self.image_label = QLabel()
        pixmap = QPixmap(400, 400)
        pixmap.fill(Qt.gray)
        self.image_label.setPixmap(pixmap)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.image_label)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setCenterButtons(False)
        self.layout.addWidget(button_box, alignment=Qt.AlignCenter)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def load_images(self):
        image_paths = sorted(self.image_dir.glob("*.png"))
        self.images = [
            QPixmap(str(p)).scaled(
                400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            for p in image_paths
        ]

    @Slot()
    def image_update(self):
        if not self.images:
            return
        pixmap = self.images[self.current_index]
        self.image_label.setPixmap(pixmap)
        self.current_index = (self.current_index + 1) % self.image_count

    def closeEvent(self, event):
        if self.timer is not None and self.timer.isActive():
            self.timer.stop()
        super().closeEvent(event)


class ShowSelfTestIntroDialogAction(Action):
    name = Str("Self Test Intro Dialog")

    def perform(self, event):
        # The dialog is a child window of the Task Action, so the parent is coming from the event.task.window.control
        dialog = SelfTestIntroDialog(parent=event.task.window.control)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            return True
        return False

    def close(self):
        self.dialog.close()
        self.dialog = None


# ---------------------------------------------------------
# Helper: Robust Resource Path (Works for Dev & PyInstaller)
# ---------------------------------------------------------
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent
    return base_path / "resources" / relative_path


# ---------------------------------------------------------
# Dialog Class
# ---------------------------------------------------------
class WaitForTestDialog(QDialog):
    cancel_requested = Signal()

    def __init__(self, parent=None, test_name="Test", mode="spinner"):
        super().__init__(parent)
        self.setWindowTitle(test_name)
        self.setModal(True)

        # UI State placeholders
        self.mode = mode
        self.spinner = None
        self.movie = None
        self.progress_bar = None
        self.current_test_label = None

        # Window Flags: Customize to remove Close 'X' button if desired
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowTitleHint
            | Qt.CustomizeWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setWindowFlag(
            Qt.WindowCloseButtonHint, False
        )  # Explicitly disable X button

        _width = 450
        self.setMinimumWidth(_width)
        # self.setMinimumHeight(int(_width/1.618))

        # Main Layout
        layout = QVBoxLayout(self)

        # Header Label
        self.label = QLabel(f"{test_name} in progress...")
        self.label.setAlignment(Qt.AlignCenter)
        # Allow text to wrap to multiple lines
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        # --- Spinner Setup ---
        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignCenter)
        gif_path = get_resource_path("spinner.gif")

        if gif_path.exists():
            self.movie = QMovie(str(gif_path))
            self.movie.setScaledSize(QSize(100, 100))  # Scale the internal frames
            self.spinner.setMovie(self.movie)
            self.spinner.setFixedSize(100, 100)  # Scale the label container
        else:
            self.spinner.setText("[Loading...]")  # Fallback if GIF missing

        layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        # --- Progress Bar Setup ---
        self.current_test_label = QLabel()
        self.current_test_label.setAlignment(Qt.AlignCenter)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        layout.addWidget(self.current_test_label)
        layout.addWidget(self.progress_bar)

        # --- Cancel UI ---
        self.cancelling_label = QLabel("Cancelling...")
        self.cancelling_label.setAlignment(Qt.AlignCenter)
        # Allow text to wrap to multiple lines
        self.cancelling_label.setWordWrap(True)
        self.cancelling_label.setVisible(False)
        self.cancelling_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.cancelling_label)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.on_cancel)
        layout.addWidget(self.cancel_button)

        # Initialize View State
        self._update_mode_visibility()

    def _update_mode_visibility(self):
        """Internal helper to set visibility based on mode."""
        if self.mode == "spinner":
            self.spinner.setVisible(True)
            if self.movie:
                self.movie.start()

            self.current_test_label.setVisible(False)
            self.progress_bar.setVisible(False)

        elif self.mode == "progress_bar":
            self.spinner.setVisible(False)
            if self.movie:
                self.movie.stop()

            self.current_test_label.setVisible(True)
            self.current_test_label.setText("Starting Tests...\n\n")
            self.label.setVisible(False)
            self.progress_bar.setVisible(True)

    def set_progress(self, value, test_name):
        """Update the progress bar if in progress mode."""
        if self.mode == "progress_bar" and self.progress_bar:
            self.progress_bar.setValue(value)

            if test_name:
                display_name = (
                    test_name.replace("test_", "").replace("_", " ").capitalize()
                )
            else:
                display_name = "Processing..."

            if self.current_test_label.isVisible():
                self.current_test_label.setText(f"Testing: {display_name}\n\n")

    def set_progress_end(self, msg="Tests Completed!"):
        """Update the progress bar if in progress mode."""
        if self.mode == "progress_bar" and self.progress_bar:
            self.progress_bar.setValue(100)
            if self.current_test_label.isVisible():
                self.current_test_label.setText(msg)

    @Slot()
    def on_cancel(self):
        """Handle user clicking cancel."""
        self.cancel_requested.emit()

        # Update UI to show cancellation state
        self.cancelling_label.setVisible(True)
        self.cancel_button.setVisible(False)  # Prevent double clicking
        self.cancel_button.setEnabled(False)
        self.label.setText("Stopping processes...")

        # Switch to spinner to indicate 'working on cancelling'
        self.mode = "spinner"
        self._update_mode_visibility()

        self.setWindowTitle("Cancelling Self-test")

    def finish_cancel(self):
        """
        Called by the Action/Controller when cancellation is technically complete.
        This closes the dialog.
        """
        self.accept()  # or self.close()


# ---------------------------------------------------------
# Action Class (Controller)
# ---------------------------------------------------------
# Assuming 'Action' and 'Instance' come from a library like 'traits' or 'enaml'.
# If standard PyQt, this would just be a normal class or QObject.


class WaitForTestDialogAction:
    def __init__(self):
        self.name = "Wait for Test Dialog"
        self.dialog = None

    def perform(self, parent, test_name=None, mode="spinner"):
        # Ensure we don't open multiple dialogs
        if self.dialog is not None:
            return

        # Use the parent's window/control if available
        gui_parent = (
            getattr(parent.window, "control", None)
            if hasattr(parent, "window")
            else None
        )

        self.dialog = WaitForTestDialog(
            parent=gui_parent, test_name=test_name, mode=mode
        )

        self.dialog.cancel_requested.connect(self.publish_cancel_message)

        # show() is non-blocking. If your test runs in the main thread,
        # the spinner will freeze. Ideally, tests run in a background thread.
        self.dialog.show()

    def finish_cancel(self):
        """Triggered when the backend confirms cancellation is done."""
        if self.dialog:
            self.dialog.finish_cancel()
            self.dialog = None

    def set_progress(self, value, test_name):
        if self.dialog:
            self.dialog.set_progress(value, test_name)

    def set_progress_end(self, msg):
        if self.dialog:
            self.dialog.set_progress_end(msg)

    def publish_cancel_message(self):
        """Publish a cancel message to the dropbot controller."""
        publish_message(topic=SELF_TEST_CANCEL, message="")

    def close(self):
        if self.dialog:
            self.dialog.close()
            self.dialog = None


class ResultsDialog(QDialog):
    def __init__(self, parent=None, title="Test Results", plot_data=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 400)

        layout = QVBoxLayout(self)

        # Matplotlib canvas
        if plot_data is not None:
            fig = plot_data[-1]
            fig.tight_layout()
        else:
            fig = Figure(figsize=(5, 3))
        self.canvas = FigureCanvas(fig)
        layout.addWidget(self.canvas)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.clicked.connect(self.close)
        layout.addWidget(button_box, alignment=Qt.AlignCenter)


class ResultsDialogAction(Action):
    name = Str("Results Dialog")

    def perform(self, parent=None, title="Test Results", plot_data=None):
        # The dialong is a child window of non UI class
        dialog = ResultsDialog(parent=parent, title=title, plot_data=plot_data)
        # use exec_() to block the main thread until the dialog is closed otherwise the window is garbage collected
        dialog.exec_()

    def close(self):
        self.dialog.close()
        self.dialog = None


class DropbotDisconnectedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dropbot Disconnected")
        self.setModal(True)
        self.setFixedSize(400, 300)

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        img_path = (
            Path(__file__).parent.parent
            / "dropbot_status"
            / "images"
            / "dropbot-power-usb.png"
        )

        html_content = f"""
        <html>
        <head></head>
        <body>
            <h3>DropBot is not connected.</h3>
            <strong>Plug in the DropBot USB cable and power supply.<br></strong>
            <img src='{img_path.as_posix()}' width="104" height="90">
            <strong><br>Click "OK" after connecting the DropBot and try again.</strong>
        </body>
        </html>
        """

        # Rich text browser for HTML
        browser = QTextBrowser()
        browser.setHtml(html_content)
        browser.setOpenExternalLinks(True)
        browser.setAlignment(Qt.AlignCenter)
        layout.addWidget(browser)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept)
        layout.addWidget(ok_button)


class DropbotDisconnectedDialogAction(Action):
    name = Str("Dropbot Disconnected Dialog")

    def perform(self, event):
        # The dialog is a child window of the Task Action, so the parent is coming from the event.task.window.control
        dialog = DropbotDisconnectedDialog(parent=event.task.window.control)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            return True
        return False

    def close(self):
        self.dialog.close()
        self.dialog = None
