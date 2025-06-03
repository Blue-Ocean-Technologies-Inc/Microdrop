from pathlib import Path

from pyface.action.api import Action
from pyface.qt.QtWidgets import (QDialog, QVBoxLayout, QLabel, 
                                 QDialogButtonBox, QProgressBar,
                                 QPushButton, QTextBrowser)
from pyface.qt.QtCore import Qt, Slot, QTimer, Signal
from pyface.qt.QtGui import QPixmap, QMovie

from traits.api import Str, Instance
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from dropbot_controller.interfaces.i_dropbot_control_mixin_service import IDropbotControlMixinService
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

from dropbot_controller.consts import SELF_TEST_CANCEL

from microdrop_utils._logger import get_logger
logger = get_logger(__name__, level="DEBUG")


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
            '<b>Please insert the DropBot test board, for more info see </b>'
            '<a href="https://github.com/sci-bots/dropbot-v3/wiki/DropBot-Test-Board#loading-dropbot-test-board">'
            '<span style="text-decoration: underline; color:#2980b9;">DropBot Test Board documentation</span>'
            '</a>'
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
        self.images = [QPixmap(str(p)).scaled(400, 400, 
                                              Qt.KeepAspectRatio, 
                                              Qt.SmoothTransformation) for p in image_paths]
    
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


class WaitForTestDialog(QDialog):
    cancel_requested = Signal()
    def __init__(self, parent=None, test_name=None, mode="spinner"):
        super().__init__(parent)
        self.setWindowTitle("Testing in Progress")
        self.setModal(True) 
        # Only title bar, no buttons
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint |
                            Qt.WindowTitleHint | Qt.WindowStaysOnTopHint)
        
        # Set minimum width
        self.setMinimumSize(400, 150) # width, height
        
        layout = QVBoxLayout(self)
        self.label = QLabel(f"{test_name} in progress...\nPlease wait")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.spinner = None
        self.progress_bar = None
        self.mode = mode
        
        # Loading spinner GIF (place your spinner.gif in resources)
        self.spinner = QLabel()
        self.movie = QMovie(str(Path(__file__).parent / "resources" / "spinner.gif"))
        self.spinner.setMovie(self.movie)
        # set the size of the spinner to 100x100 and resize the video to the size of the spinner
        self.spinner.setFixedSize(100, 100)
        self.movie.setScaledSize(self.spinner.size())
        self.spinner.setVisible(False)
        layout.addWidget(self.spinner, alignment=Qt.AlignCenter)
        
        if self.mode == "spinner":
            self.spinner.setVisible(True)
            self.movie.start()
        elif self.mode == "progress_bar":
            self.current_test_label = QLabel(f"Running: ")
            self.progress_bar = QProgressBar()
            self.progress_bar.setMinimum(0)
            self.progress_bar.setMaximum(100)
            self.progress_bar.setValue(0)
            layout.addWidget(self.current_test_label, alignment=Qt.AlignCenter)
            layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)

        # "Cancelling..." label
        self.cancelling_label = QLabel("Cancelling...")
        self.cancelling_label.setAlignment(Qt.AlignCenter)
        self.cancelling_label.setVisible(False)
        layout.addWidget(self.cancelling_label)
    
        # adding cancel button, remove if unnecessary
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.on_cancel)
        layout.addWidget(self.cancel_button)

    def set_progress(self, value, test_name):
        """Update the progress bar if in progress mode."""
        if self.mode == "progress_bar" and self.progress_bar is not None:
            self.progress_bar.setValue(value)
            if test_name is not None:
                test_name = test_name.replace("test_", "").replace("_", " ").capitalize()
            else:
                test_name = "Done!"
            self.current_test_label.setText(f"Testing: {test_name}")
  
    @Slot()
    def on_cancel(self):
        self.cancel_requested.emit()
        logger.debug("Cancel requested from UI, Dialog closed successfully.")
      
        self.cancelling_label.setVisible(True)
        self.cancel_button.setVisible(False)
        self.label.setVisible(False)
        if self.mode == "progress_bar" and self.progress_bar is not None:
            self.progress_bar.setVisible(False)
            self.current_test_label.setVisible(False)
            self.spinner.setVisible(True)
            self.movie.start()
        self.setWindowTitle("Cancelling Self-test")


class WaitForTestDialogAction(Action):
    name = Str("Wait for Test  Dialog")
    dialog = Instance(WaitForTestDialog)
    
    def perform(self, parent, test_name=None, mode="spinner"):
        # The dialog is a child window of the Task, so the parent is self.window.control
        self.dialog = WaitForTestDialog(parent=parent.window.control,
                                        test_name=test_name,
                                        mode=mode)

        self.dialog.cancel_requested.connect(self.publish_cancel_message)
       
        self.dialog.show()

    def finish_cancel(self):
        if self.dialog:
            self.dialog.finish_cancel()
    
    def set_progress(self, value, test_name):
        self.dialog.set_progress(value, test_name)

    def publish_cancel_message(self):
        """Publish a cancel message to the dropbot controller."""
        publish_message(topic=SELF_TEST_CANCEL, message=None)
    
    def close(self):
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
        self.setFixedSize(400,300)  

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        img_path = Path(__file__).parent.parent / "dropbot_status" / "images" / "dropbot-power-usb.png"

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