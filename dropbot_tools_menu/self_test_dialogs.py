import os
from PySide6 import QtGui, QtCore
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QScrollArea, QDialogButtonBox, QWidget
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class SelfTestIntroDialog(QDialog):
    def __init__(self, parent=None, image_dir=None, image_count=5, interval=1000):
        super().__init__(parent)
        self.setWindowTitle("DropBot Self-Test: Prepare Device")
        self.setModal(True)
        self.image_dir = image_dir or os.path.join(os.path.dirname(__file__), "../device_viewer/resources/self_test_images")
        self.image_count = image_count
        self.interval = interval  # milliseconds
        self.current_index = 0

        # Main layout
        self.layout = QVBoxLayout(self)

        # Text
        instruction_label = QLabel(
            "<b>Please insert the DropBot test board, for more info see the</b>"
        )
        instruction_label.setAlignment(QtCore.Qt.AlignLeft)
        self.layout.addWidget(instruction_label)

        # Hyperlink
        doc_link = QLabel(
            '<a href="https://github.com/sci-bots/dropbot-v3/wiki/DropBot-Test-Board#loading-dropbot-test-board">'
            '<span style="text-decoration: underline; color:#2980b9;">DropBot Test Board documentation</span>'
            '</a>'
        )
        doc_link.setOpenExternalLinks(True)
        doc_link.setAlignment(QtCore.Qt.AlignLeft)
        self.layout.addWidget(doc_link)

        # Image Display
        self.image_label = QLabel()
        self.image_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.image_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.setCenterButtons(False)
        self.layout.addWidget(button_box, alignment=QtCore.Qt.AlignRight)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # Load Images
        self.images = []
        for i in range(1, self.image_count + 1):
            image_path = os.path.abspath(os.path.join(self.image_dir, f"image{i}.png"))
            pixmap = QtGui.QPixmap(image_path)
            if pixmap.isNull():
                pixmap = QtGui.QPixmap(200, 200)
                pixmap.fill(QtCore.Qt.gray)
            self.images.append(pixmap)

        # Timer for image loop
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.next_image)
        self.timer.start(self.interval)
        self.next_image()

    def next_image(self):
        if not self.images:
            return
        pixmap = self.images[self.current_index]
        self.image_label.setPixmap(pixmap.scaled(400, 400, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        self.current_index = (self.current_index + 1) % self.image_count

    def accept(self):
        self.timer.stop()
        super().accept()

    def reject(self):
        self.timer.stop()
        super().reject()

class ResultsDialog(QDialog):
    """
    A custom dialog to display test results (text and a plot).
    """
    def __init__(self, parent=None, table_data=None, rms_error=None, plot_data=None):
        super().__init__(parent)

        self.setWindowTitle("Test Results")
        self.resize(600, 400)

        # Create layout
        layout = QVBoxLayout()

        # Add RMS error
        if rms_error:
            rms_label = QLabel(f"Root-Mean-Squared (RMS) Error: {rms_error}")
            rms_label.setWordWrap(True)
            layout.addWidget(rms_label)

        # Add table
        if table_data:
            table_label = QLabel("Results (Target vs. Measured):")
            table_label.setWordWrap(True)
            layout.addWidget(table_label)

            for row in table_data:
                row_label = QLabel('   '.join(map(str, row)))
                row_label.setWordWrap(True)
                layout.addWidget(row_label)

        # Add plot
        if plot_data:
            canvas = FigureCanvas(Figure(figsize=(5, 3)))
            layout.addWidget(canvas)

            # Create the plot
            ax = canvas.figure.add_subplot(111)
            ax.plot(plot_data['x'], plot_data['y'], 'o-', label="Measured vs Target")
            ax.plot(plot_data['x'], plot_data['x'], 'k--', label="Ideal")
            ax.set_title("Measured vs Target")
            ax.set_xlabel("Target")
            ax.set_ylabel("Measured")
            ax.legend()

        
        self.setLayout(layout)

class ScanTestBoardResultsDialog(QDialog):
    def __init__(self, parent=None, description_text="", images=None):
        super().__init__(parent)
        self.setWindowTitle("Scan Test Board Results")
        layout = QVBoxLayout()

        if description_text:
            layout.addWidget(QLabel(description_text))

        if images:
            for img_path in images:
                if os.path.exists(img_path):
                    pixmap = QtGui.QPixmap(img_path)
                    img_label = QLabel()
                    img_label.setPixmap(pixmap)
                    img_label.setScaledContents(True)
                    img_label.setMaximumHeight(400)
                    layout.addWidget(img_label)
                else:
                    layout.addWidget(QLabel(f"(Image not found: {img_path})"))

        # Scroll area for overflow ???
        scroll = QScrollArea()
        container = QWidget()
        container.setLayout(layout)
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        dialog_layout = QVBoxLayout()
        dialog_layout.addWidget(scroll)
        self.setLayout(dialog_layout)

