from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QVBoxLayout, QPushButton, QWidget

from microdrop_utils.pyside_helpers import LoadingOverlay


class MyWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.resize(400, 300)

        layout = QVBoxLayout(self)
        self.btn = QPushButton("Start Setup Task")
        self.btn.clicked.connect(self.start_setup)
        layout.addWidget(self.btn)

        # Initialize Overlay
        self.overlay = LoadingOverlay(self)

    def start_setup(self):
        # 1. Show Loading
        self.overlay.show_loading(duration_ms=10000)

        # 2. Disable interaction if needed (Overlay handles most clicks, but good practice)
        self.btn.setEnabled(False)

        # 3. Simulate a long task using QTimer (In real app, use QThread!)
        QTimer.singleShot(20000, self.finish_setup)

    def finish_setup(self):
        # 4. Hide Loading
        self.overlay.stop_loading()
        self.btn.setEnabled(True)
        self.btn.setText("Setup Complete!")


if __name__ == "__main__":
    app = QApplication([])
    w = MyWidget()
    w.show()
    app.exec()
