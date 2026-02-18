import sys
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QProgressBar)
from PySide6.QtCore import QTimer, Qt

from microdrop_utils.pyside_helpers import PausableTimer


class TimerTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fixed Pausable Timer")
        self.resize(400, 200)

        # 1. Logic Timer
        self.timer = PausableTimer(self)
        self.timer.timeout.connect(self.on_finished)

        # 2. UI Update Timer (Ticks every 50ms to update progress bar)
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(50)
        self.ui_timer.timeout.connect(self.update_ui)

        # State tracking for the Progress Bar
        self.total_duration = 5000

        # UI Layout
        layout = QVBoxLayout()

        self.lbl_time = QLabel("Ready")
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_time.setStyleSheet("font-size: 24px;")
        layout.addWidget(self.lbl_time)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(1000)
        layout.addWidget(self.progress)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")

        self.btn_start.clicked.connect(self.do_start)
        self.btn_pause.clicked.connect(self.do_pause)
        self.btn_resume.clicked.connect(self.do_resume)

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_pause)
        btn_layout.addWidget(self.btn_resume)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def do_start(self):
        self.total_duration = 5000 # 5 seconds
        self.timer.start(self.total_duration)
        self.ui_timer.start()
        self.update_ui()

    def do_pause(self):
        self.timer.pause()
        self.update_ui() # Update one last time to show "paused" state

    def do_resume(self):
        self.timer.resume()
        self.update_ui()

    def on_finished(self):
        self.ui_timer.stop()
        self.lbl_time.setText("Done!")
        self.progress.setValue(0)

    def update_ui(self):
        # 1. Get how much time is left (whether running or paused)
        left = self.timer.remainingTime()

        # 2. Update Label
        self.lbl_time.setText(f"{left / 1000:.1f} s")

        # 3. Update Progress Bar
        # We calculate progress against the TOTAL duration (5000),
        # not whatever slice we just resumed.
        if self.total_duration > 0:
            ratio = left / self.total_duration
            self.progress.setValue(int(ratio * 1000))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TimerTestWindow()
    window.show()
    sys.exit(app.exec())